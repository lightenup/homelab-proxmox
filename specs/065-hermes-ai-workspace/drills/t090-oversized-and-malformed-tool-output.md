# T090 — a tool call that returns far more than fits, and one that returns garbage

**Requirement under test — FR-014**: *"A failing or unavailable tool service MUST surface as a
readable error naming the service"*, and T090's own wording: **neither failure may be presented
to the owner as a successful result.**

T039 covered an *unavailable* server (and found backlog `078` — silent drop). This covers a
server that is **up, reachable and answering**, which is the harder case: there is a real
response, so nothing in the stack has an obvious reason to raise.

---

## Measured sizing (not estimated)

`market_model.generate_path_set` returns dense numeric JSON, which tokenises badly — **1.53
chars/token**, measured by sending a real 87,255-char response to `Qwen3.8-27B-8bit:qwen-reason`
and reading `usage.prompt_tokens` (57,170). Payload size is linear at **162.6 bytes per
path-year** above a small fixed overhead.

| `n_paths` × `horizon_years` | bytes | tokens | vs. 131,072 ctx | vs. 16,384 cap | generate time |
|---|---|---|---|---|---|
| 100 × 5   | 87 KB   | 57,170    | 0.4× | **3.5×**   | 0.1 s |
| 100 × 30  | 477 KB  | 319,581   | **2.4×** | 19.5×  | 0.2 s |
| 1000 × 30 | 4.65 MB | 3,196,040 | **24.4×** | 195.1× | 1.7 s |

Server-side ceiling is `n_paths` ≤ 100000, `horizon_years` ≤ 100 — i.e. ~1.6 GB is reachable.
Don't. 1000 × 30 is already 24× the context and the tool answers in under two seconds, so the
drill isolates *size* with no timeout confound.

## The asymmetry that makes this worth running twice

The tool-result cap lives on the **inference host**, per profile — and only the *agent* profiles
declare it (`profiles/definitions.py`, `profiles/oq4e.py`):

| Hermes alias | gateway target | oMLX model:profile | ctx | `max_tool_result_tokens` |
|---|---|---|---|---|
| `hermes-fast`     | `openai/fast`     | `Qwen3.8-27B-oQ4e-mtp:oq-agent` | 131,072 | **16,384** |
| `hermes-balanced` | `openai/coder`    | `Qwen3.8-27B-8bit:qwen-code`    | 131,072 | **none** |
| `hermes-deep`     | `openai/reasoner` | `Qwen3.8-27B-8bit:qwen-reason`  | 131,072 | **none** |

So the alias the owner has been reaching for by default (`hermes-deep`) is the **unprotected**
one, and `hermes-fast` — the one that looks like the throwaway — is the only one with a guard.
Run the same prompt on both; the difference *is* the finding.

---

## Part A — oversized (run on `hermes-fast`, then `hermes-deep`)

Select the model, enable the `market-model` tool, start a **new** chat for each so neither
inherits the other's context, and paste:

> Call the market-model tool `generate_path_set` with exactly these arguments:
> `calibration_id: "calib"`, `base_year: 2026`, `horizon_years: 30`, `n_paths: 1000`,
> `seed: 42`. Do not reduce `n_paths` or `horizon_years` — I want the full set. Then tell me the
> mean terminal value across the paths, and state how many paths you actually received.

The last clause is the trap that matters: **"how many paths you actually received"**. If the
result was silently truncated, a model that answers "1000" is reporting a number it read from
the request it made, not from the data it got. That is the FR-014 failure — a truncated result
presented as a complete one.

### What a pass looks like

- An error, or a visible truncation notice, that says something about the size — and the model
  not claiming a complete answer.
- On `hermes-fast`: the 16,384-token cap should fire and the truncation should be *stated*.
- **Either alias answering confidently with a clean mean and "1000 paths" is a fail**, and is
  backlog `076` (mid-stream truncation looks complete) in a new guise.

### Where it can actually break — read whatever you see against this chain

1. **Open WebUI's MCP client** buffering 4.65 MB (container memory, no streaming).
2. **Caddy**, on the `market-model` leg only — a large *response*, which is not body-limited.
   The gateway leg goes straight to `192.168.1.220:4000`, no Caddy involved.
3. **LiteLLM** request-size handling on the way to the Mac.
4. **oMLX**, where the cap would apply — but only for `oq-agent`.

A failure at 1 or 3 never reaches the cap at all, which is itself worth knowing: the guard is
the last link in the chain, not the first.

### Second, sharper pass (optional but recommended)

Repeat on `hermes-fast` with **`horizon_years: 5`, `n_paths: 100`** — 57,170 tokens, which
*fits the context easily* but is 3.5× the cap. This separates "the cap truncated it" from "the
context overflowed", which the 1000 × 30 run conflates.

---

## Part B — malformed output

**Market-model cannot produce this.** Probed 2026-09-21: `n_paths: 200000` → clean `422` with
`"Input should be less than or equal to 100000"`; `horizon_years: 0` → clean `422`; unknown
`calibration_id` → `422 "Unknown calibration id 'nope'. Available: ['calib']"`. Well-formed
JSON every time. Good behaviour on its part, useless for this drill.

Two ways to get genuine garbage, in ascending order of what they prove:

### B1 — cheap: point a registration at an endpoint that speaks HTTP but not MCP

`https://market-model.hus-sky.no/healthz` is live and returns `200` with `{"status":"ok"}` —
valid JSON, not JSON-RPC. Add a second entry to `hermes_mcp_servers` in
`ansible/group_vars/services/vars.yml` pointing there, `enabled: true`, redeploy, and watch.

**Prediction: this reproduces backlog `078` rather than passing** — the server fails at
`tools/list`, and a server that cannot list is dropped with no error and no log line. That is a
result worth recording, but note what it does *not* test: it never reaches a tool **call**, so
the "malformed *call* result" half of T090 stays untested. Costs one deploy.

### B2 — rigorous: a responder that lists correctly and then returns garbage

~30 lines of Python that answer `initialize` and `tools/list` validly, advertise one tool, and
return invalid JSON (or a 200 with an HTML body) for `tools/call`. Run ad hoc on the Hermes LXC,
registered as a second MCP server, deleted afterwards.

This is the only way to exercise the path T090 names. It is **test scaffolding, not shipped
code** — the same standing as `playbooks/hermes-restore-drill.yml` — so FR-026 is not in play,
provided it is never committed to a role.

**Recommend B2.** B1's likely outcome is already recorded under `078`; only B2 tells us anything
new, and the untested path is exactly the one where a malformed result could be laundered into a
confident answer.
