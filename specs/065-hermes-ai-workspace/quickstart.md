# Quickstart — Hermes

**Feature**: `065-hermes-ai-workspace` | **Written**: 2026-09-20 | **Config landed**: 2026-09-20

Deploy, verify, and run the drills that make the acceptance criteria real rather than assumed.

> Written before implementation. Every command here is a **claim to be checked**, not a recording of
> something that worked — unlike `064`'s quickstart, which was rewritten against a live deploy.
> Update it as you go, and treat a step that needed changing as information worth keeping.

## Status (2026-09-21) — deployed, serving, and drilled

Hermes is live at `https://hermes.hus-sky.no`, monitored, backed up, and its backup has been
restored from scratch. **62 of 90 tasks closed.** What follows is a record of what happened,
not a plan.

### Proven by drill, with evidence

| | result |
|---|---|
| **SC-002** every surface gated | chat, model list, knowledge, files, users and the programmatic endpoint all **401**; a real signup attempt **403**, no account created |
| **SC-003** tool use (T038) | `hermes-deep` called `market-model_list_stress_scenarios` + `list_calibrations` and answered from what came back — including relaying the calibration's own "placeholder, do not use in production" caveat |
| **SC-006** destroy and restore (T048) | CT destroyed, rebuilt from code, restored: conversations **2 -> 0 -> 2**, memories **1 -> 0 -> 1**, account and 345 config rows preserved, `integrity_check ok` |
| **US2** honest indicator (T034) | card probe went to 0 in **10s**, apex reported down (not a stale success), recovery in **20s**, and `HermesDown` went pending -> inactive **without firing** |
| **FR-013** config-only tool servers (T088) | a disabled placeholder added to `hermes_mcp_servers` reached the running system; removing it removed it again |

### Failed by drill — and left failed on purpose

| | result |
|---|---|
| **SC-005** fast failure (T050) | **hangs.** First request with the host away: no response at 90s against a 10s criterion. [backlog `075`](../../docs/backlog/075-first-request-hangs-when-inference-host-away.md) |
| **US-5** honest degradation (T089) | **worse.** Host lost mid-stream ends the stream in 0.1s with `finish_reason: "stop"` and `[DONE]` — 27% of an answer, presented as complete. [backlog `076`](../../docs/backlog/076-mid-stream-host-loss-looks-like-a-complete-answer.md) |
| **SC-004** alias change (T040) | diff is config-only as required, but the change is **inert**: `TASK_MODEL_EXTERNAL` is a PersistentConfig, so the compose says `hermes-balanced` while the database still says `hermes-fast` |

### Measured (T082) — and why nothing was resized

Idle, 15 minutes after a rebuild: **818 MB** of 6144 MB used (open-webui 647 MiB, searxng
93 MiB), **8.4 GB** of 32 GB disk (almost all Docker images — the data dir is 1.2 MB), load
0.17 on 4 cores. Host has no pressure: `local-lvm` at 12.7%, 746 GB free.

**Deliberately not resized.** These are idle numbers, and the two heaviest features —
in-container Whisper STT and SpeechT5 TTS — have never run. Cutting memory on this evidence
would repeat the original sin of guessing, with extra steps. Hermes is nonetheless the
largest allocation in the fleet (6 GB vs immich's 4 GB) while among the lightest actual
users, so **re-measure after the voice drill (T071) and resize then**.

### Still blocked, and on what

- **Retrieval / state saving (US6)** — no embedding model exists on the inference host
  (T055/T056). Memory, Knowledge and document upload all embed, so all of them fail. A third
  prerequisite surfaced on 2026-09-21: the Mac's key is scoped to a `local` access group
  (`key not allowed to access model … models=['local']`), so a new embedding model must be
  added to that group as well as loaded and aliased.
- **Changing `hermes_embedding_alias` will also be inert** when that lands — same
  PersistentConfig trap as T040, now measured rather than predicted. Only
  `tool_server.connections` has a reconcile step today.
- **Phone drills** (SC-001, FR-005, SC-012) and anything needing a chat session.

## 0. Prerequisites

**On the inference host** — four session-scoped processes, plus two new models:

| | |
|---|---|
| Existing four | `064`'s [`mac-side.md`](../064-llm-router/mac-side.md) — nothing auto-starts |
| **New**: embedding model | loaded in oMLX, exposed through the Mac's gateway |
| **New**: reranker | same |

**In `064`** — the two new capability aliases exist and the Hermes client key's scope includes them.
See [contracts/gateway-usage.md](./contracts/gateway-usage.md).

**In the vault** — the gateway client key, the admin bootstrap credential, and any MCP credential.

## 1. Deploy

Through the pipeline, as every service is. Plan first.

## 2. Verify the deploy

- The stack is up and the published port answers from the LXC.
- The public hostname resolves, serves a certificate, and presents a **login** before anything else.
- `ENABLE_SIGNUP` is off — confirm by attempting to register, not by reading the config.

## 3. The drills

These are the acceptance criteria. Each maps to a success criterion in [spec.md](./spec.md).

| # | drill | proves |
|---|---|---|
| 1 | Sign in from a phone on mobile data; send a prompt; add to home screen | SC-001 |
| 2 | Request every surface unauthenticated — chat, model list, documents, **and the programmatic endpoint** | SC-002 |
| 3 | Ask a question only answerable through an MCP server | SC-003 |
| 4 | Change a capability alias in `group_vars`; redeploy; confirm no template or code changed | SC-004 |
| 5 | **Log the inference host out.** Send a prompt; time the error; confirm the UI still loads and history is readable | SC-005 |
| 6 | Destroy the LXC, rebuild from code, restore, confirm everything returns | SC-006 |
| 7 | Upload a document, ask about it, confirm the citation — and that nothing left the estate | SC-007 |
| 8 | One hour of representative use; read the request rate from gateway metrics | SC-008 |
| 9 | A prompt whose response takes 15 minutes | SC-009 |
| 10 | Schedule a run; let it fire while the inference host is away | SC-010 |
| 11 | Inspect the diff: no bespoke application source | SC-011 |
| 12 | Speak a question on a phone, hear the answer | SC-012 |
| 13 | Ask something requiring current information; confirm citations and that no commercial search provider was called | SC-013 |
| 14 | Call the programmatic endpoint from another homelab service | SC-014 |
| 15 | A scheduled prompt runs unattended and its output is waiting | SC-015 |

### Drill 5 is the one that matters

It is the difference between a service that degrades honestly and one that hangs. `064` has no
fallback tier, so the failure is unavoidable — the only question is whether it is **legible and
fast**. Read a hang as the failure, not the error.

**Run 2026-09-21. It hung. SC-005 fails** — see
[backlog `075`](../../docs/backlog/075-first-request-hangs-when-inference-host-away.md).
Measured against the gateway with the real Hermes client key, host taken away by stopping the
TLS terminator (port closed, so the Mac's stealth mode drops the SYN exactly as when asleep):

| condition | observed |
|---|---|
| baseline, host present | **200 in 0.91s** |
| first request, host away | **no response at 90.01s** (client aborted) |
| second request, host away | **no response at 30.00s** |
| later requests | **429 in 0.03s**, `cooldown_list=['fast-local']` |
| host restored | **200**, no administrative action |

The 10-second criterion is missed by at least an order of magnitude on the first request.
Everything after the first failure is correct and fast. Root cause: one per-deployment
`timeout` (1200s, needed so FR-021's 20-minute generation is not truncated) also governs
connect, and the cooldown cannot engage until that first failure completes.

The other half of the story passed: the **interface stayed up** (200 in 0.06s with the backend
gone) and **recovery needed no administrative action**.

### And the mid-stream case is worse (T089, backlog `076`)

Pulling the host away **during** a streaming answer is the more likely event in practice, and
it fails differently — not by hanging, but by lying:

| | |
|---|---|
| stream ended | **0.1s** after the host vanished |
| curl exit / terminal chunk | **0** / `finish_reason: "stop"` / `data: [DONE]` |
| error chunks | **0** |
| delivered | **322 words of ~1200 (27%)**, cut mid-sentence |

Open WebUI receives a well-formed *successful* stream, so it has nothing to detect: the
truncated answer is rendered and **saved to the conversation** as an ordinary turn. Weeks
later nothing distinguishes it from a complete one.

**If you see an answer that stops oddly mid-thought, suspect this before suspecting the
model.** Re-ask rather than trusting it.

### Drill 8 needs a definition before it is run

"Representative use" must be agreed in advance or the measurement means nothing. Decide what an
hour of real use looks like — how many conversations, whether documents are indexed — and record it
alongside the result.

## 4. Things that will probably bite

Collected from the research and from `064`'s scars.

- **Retrieval silently reaching for `api.openai.com`.** `RAG_OPENAI_API_BASE_URL` and
  `RAG_OPENAI_API_KEY` do not reliably inherit from `OPENAI_API_*` (upstream #22084). Left unset,
  retrieval is both broken and a breach of FR-008. Preflight asserts both.
- **The proxy truncating a long generation.** `proxy_timeout` must clear 20 minutes. The symptom
  looks like a model failure.
- **Housekeeping calls exhausting the request allowance** before the owner's own prompts do.
- **Monitoring deployed through the lab path**, which renders an empty configuration over the live
  one — [backlog `072`](../../docs/backlog/072-lab-monitoring-deploy-wipes-prod.md). Prod path only.
- **The inference host being asleep** during almost any drill, producing a failure that looks like a
  bug in Hermes. Check the host first.
- **Qwen answers in Chinese when the prompt gives it no language to follow.** Observed
  2026-09-21: an image plus the three words "Describe the picture" came back entirely in
  Chinese. Every alias is backed by Qwen3.8, so this is the model's native default asserting
  itself when the prompt carries almost no language signal — not a fault, and not specific
  to images.
  **Fix**: set a personal system prompt (Settings -> General -> System Prompt), e.g.
  *"Reply in the same language as my message. If the language is unclear, reply in English."*
  Phrased that way it still answers Norwegian in Norwegian.
  **This one cannot be managed as code.** Open WebUI has no env var for the chat system
  prompt (only task-specific templates), and oMLX profiles carry sampling and context fields
  only — no system prompt. So it is a UI setting, stored in `webui.db`, and it survives a
  rebuild only because the restore path works. Worth re-checking after any restore.
- **Vision works, and was never specified.** The same test showed `hermes-deep` describing a
  TOGAF diagram's structure and colours accurately. No FR asked for it and nothing was
  configured for it — it is a property of the Qwen3.8 checkpoints behind the aliases. Free
  capability, but do not build on it without checking it survives a model swap: the alias
  contract promises a capability tier, not a modality.
- **Retrieval is unavailable whenever the inference host sleeps, by design** (research R-002's
  accepted cost). A document question with no embedding model reachable must fail readably
  (US-6 AS-3, T063) — this is not a bug to chase, it is FR-009 extended to retrieval. An
  in-container CPU embedding model would have survived host absence; that trade was rejected
  for weaker retrieval quality (research.md).
