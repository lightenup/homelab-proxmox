# Quickstart / validation: Long-term memory for Hermes (097)

Runbook-style checks. Each maps to a spec success criterion.

- **Keys**: read them from the vault on `pve` or a laptop (constitution V). Never paste them into
  chat or logs. `$MEM` below means `https://memory-api.hus-sky.no/v1/default/banks`.
- **Synthetic data**: PROD checks use clearly synthetic facts ("my test parrot is called
  Probe-097") and remove them afterwards (§ 8).

## 0. Preconditions

- **NAS share** (T001): `homelab_memory` created on the Synology by the owner, 2026-10-31. The
  `pve` mount `/mnt/nas/homelab_memory` is written to `/etc/fstab` by `proxmox_mounts`
  (`ansible.posix.mount`, `state: mounted`) at the first deploy; on 2026-10-31 it had no fstab
  entry yet, as expected.
- **Address** (T001): `pct list` on `pve`, 2026-10-31: 12 containers (VMIDs 100–112, no
  `memory`), and no `/etc/pve/lxc/*.conf` uses `192.168.1.223`.

## 1. Harness gate on the dev Mac (FR-021: SC-001 to SC-005)

Run before the first PROD promotion that turns memory on, and again for every later change to
the provider, its version or mode, the policy module or an adapter.

```sh
cd docs/backlog/097-spike
./render-prod.sh                 # research R-017: renders server.env, clients.json, plugin config from Ansible
./run.sh prod-render             # pinned images + shim + rendered config, dataset.json
python3 llmproxy/portability.py --clients hermes,open-webui,claude-code   # SC-005 + scope checks
```

Expected:

| Criterion | Pass condition |
|---|---|
| SC-001 | `score.txt` ≥ 14/16, all 8 volume probes, strictly above the latest baseline (`results/none*`) |
| SC-002 | Both update probes current, the negative probe "don't know" |
| SC-003 | `calls.jsonl` shows 0 chat calls for the memory phase; embed and rerank calls only, under the memory key |
| SC-004 | No egress attempt in the proxy log beyond the gateway |
| SC-005 | 6/6 cross-client recalls; read-only retain refused (403); forged tag replaced |

Record the results under `results/<YYYY-MM-DD>-prod-render/` and link them in the PR.

**Run 2026-10-31** (T036, re-run after the PR #318 review fixes; fingerprint `5aef232f…`,
[`results/2026-10-31-prod-render/`](../../docs/backlog/097-spike/results/2026-10-31-prod-render/),
verdict in `gate.json`):

| Criterion | Result |
|---|---|
| Images | PASS: compose ran `hindsight:1.1.0-slim`, `pgvector:0.8.1-pg17`, `hermes-agent:v0.21.6`, as rendered from the PROD pins |
| SC-001 | PASS: 16/16, all 8 volume probes; best baseline 11/16. p16 judged by hand, bound to the answer's sha256 (`overrides.json`): it recalls "ask before suggesting network changes" and ends by asking which option the owner wants |
| SC-002 | PASS: both update probes current (p1, p4); the negative probe answers "no record of a cat" (p8) |
| SC-003 | PASS: the memory key made 79 embed and 33 rerank calls and 0 chat calls |
| SC-004 | PASS: no egress attempt in the compose log |
| Store | 34 documents, 34 units, every unit tagged `client:hermes`, 0 failed operations |
| Memory | agent 330 MiB, Hindsight 333 MiB, Postgres 92 MiB at the end of the run |

**Re-run 2026-10-31 15:45** for the US5 web UI policy (maintenance jobs and UI read views; fingerprint
`df080631…`, `results/2026-10-31-1545-prod-render/`): images, SC-001 (16/16, all 8 volume probes,
no hand judgement), SC-002, SC-003 (81 embed, 33 rerank, 0 chat) and SC-004 PASS.

**Runs 2026-10-31 17:30 and 18:15** for the read-view rule (fingerprint `833fa285…`): 17:30 FAILED
SC-001 (15/16): p16 listed router changes without mentioning the "ask first" preference (judged
fail, `results/2026-10-31-1730-prod-render/`, kept on record). The agreed single re-run at 18:15
PASSED: p16 recalls the preference and hands the choice back (judged pass by the same standard,
digest-bound), SC-002 to SC-004 and images pass (`results/2026-10-31-1815-prod-render/`). p16 is
the one probe that varies run to run; it has passed in 4 of 5 prod-render runs today.

**Runs 2026-10-31 19:20 and 19:40** for US2's Open WebUI filter (fingerprint `85ded065…`, the
first runs with the SC-005 leg): 19:20 FAILED SC-001 on p16 (six router changes, no mention of the
"ask first" preference; recall had returned it at rank 2, so model compliance, not retrieval;
kept on record in `results/2026-10-31-1920-prod-render/`). The agreed single re-run at 19:40
PASSED: SC-001 16/16 (p16 on its keywords; p15 judged pass, "melkefri" tripping the "melk"
keyword), SC-002 to SC-004, SC-005 6/6 cross-client recalls with per-client tags, the forged tag
replaced, the read-only retain refused (403) and webhooks refused for every key
(`results/2026-10-31-1940-prod-render/`).

SC-005 (cross-client) is US2's harness leg (T045, T046).

**Runs 2026-11-01** for the Hermes memory fix after § 8 (built-in notes off with a one-shot
import, owner profile kept, `SOUL.md` routing corrections and forgets to the memory tools, the
harness agent given the memory MCP server, tool loops hard-stopped; times are Oslo time):

- 11:35 FAILED SC-004: the harness agent had no memory MCP server, so the new `SOUL.md` sent it
  hunting for the tools (a blocked fetch, a browser download). The harness was aligned with PROD.
- 12:15 and 12:40 FAILED SC-001 on p16, judged fail by the 2026-10-31 standard. SC-001 was then
  amended (owner decision): a preference probe counts when its preference is in the top 3 recall
  results (`recall.jsonl`); the answer is recorded as `preference_answers`.
- 13:45 FAILED on p15 (cream and cheese for a lactose-intolerant owner) and one 30-minute tool
  loop; the owner profile was put back on. 14:20 was stopped in a 400-step loop on a malformed
  `tool_call`. 14:55 FAILED on p2 and p15 with the facts at recall rank 2 and in the profile.
  Two controls (15:30 without the `SOUL.md` paragraph, 16:10 without the MCP tools, stopped) did
  not separate a cause.
- Root cause, from the request bodies in the Mac LiteLLM's spend logs: the recall block was about
  13,000 characters (the plugin's default `recall_max_tokens`, 4,096), over Hermes's hook-output
  spill limit of 10,000, so the model saw only its head and tail and facts ranked 2 to 3 were cut.
  Fix: `recall_max_tokens: 2000` (the contract's figure) and `hooks.output_spill.max_chars: 16000`.
- 16:40 PASSED (fingerprint `75c651b6…`): SC-001 16/16 with all 8 volume probes (p3 judged pass,
  "nuts" in "free of nuts and dairy"; p16 counted on recall rank 2, its answer still ignoring the
  preference), SC-002 to SC-005 and images. LiteLLM logs: 0 of 60 recall-carrying requests cut.
  One malformed `tool_call` repeated 4 times before the model moved on
  (`results/2026-11-01-1640-prod-render/`).
- PR #340 review widened the fingerprint (the harness agent config), so the gate ran again. 17:16
  FAILED on p10 ("fyller 70. mars 2027" without the day; the prompt held "14 March" uncut, so
  model output). The agreed single re-run at 17:35 PASSED (fingerprint `a6486e98…`): SC-001 16/16
  (p15 judged pass, "nøtter"/"melkeprodukter" tripping the keywords; p16 on recall rank 2, its
  answer now naming the preference), SC-002 to SC-005 and images, 0 tool loops
  (`results/2026-11-01-1735-prod-render/`).
- PR #340's second review: the preference leg had queried the store after the probes, when their
  own answers were in it. It now reads the recall block injected into each probe's first request
  (`recall_from_injected.py`, `injected.jsonl`). 18:15 PASSED on that measure: p16's preference at
  rank 2 of an uncut block; SC-001 16/16 with p9 judged pass ("sjøbiolog" for marine biologist);
  SC-002 to SC-005 and images; 0 tool loops (`results/2026-11-01-1815-prod-render/`).
- T071, one document per turn (fingerprint `ba537d25…`, the policy module changed), with the new
  `durability` leg as gate criterion T071. 20:00 PASSED: T071 3/3 clients (a retired turn stays
  retired and an edit holds after the next turn, 3 per-turn documents with the client tag; for
  Hermes a full-session resend and a repeated turn add nothing); SC-005 6/6 with the tag check on
  per-turn documents; SC-001 15/16 with all 8 volume probes (p4, p6, p8 judged pass on keyword
  gaps: "flat white" as given up, "badstua", "ikke noen opplysninger"; p7 judged fail, the 03:00
  decision at ranks 1 and 2 of an uncut block and the model saying it does not know); p16's
  preference at rank 1; SC-002 to SC-004 and images; 0 tool loops
  (`results/2026-11-01-2000-prod-render/`).

Earlier runs the same day: an 11:00 pass (superseded when the fingerprint widened) and two
stopped and discarded runs: the first had no valid LiteLLM key and
showed that `PYTHONPATH` does not reach the gateway (fixed with a `.pth` file, research R-003);
the second showed the harness skipped the bank creation the memory deploy performs, so every
client retain was refused `scope readwrite may not create_bank` (fixed with
`runs/prod-render/after-up.sh`).

## 2. LAB rehearsal (SC-008)

Runs inside `Prod 1 - LXC Promote` for `memory`, then for `hermes`.

- **memory**:
  - The lab copy at `10.99.0.223` starts with no gateway, and `scripts/healthcheck/memory.sh`
    passes on `/health`.
  - The deploy probe (R-019) and the backup timer are listed in `reports/lab/skipped-checks.txt`.
  - Record the `/metrics` metric names for R-015:
    `curl -s http://10.99.0.223:8888/metrics | grep -E '^hindsight_' | cut -d'{' -f1 | sort -u`.
- **hermes**:
  - The agent's `/health` is healthy with memory unreachable.
  - One API-server turn returns the gateway's 429 without a crash (R-016).
  - The Open WebUI filter loads and fails open (R-007).
- **memory web UI**: the lab copy answers `GET http://10.99.0.223:9999/api/health` with 200 and
  serves `/login` without showing data. Record its resident memory for SC-007 (R-020).
- **Both**: the production fingerprint is unchanged, and no scrape target, probe or backup timer
  exists for a lab copy.

## 3. memory in PROD: deploy probe and auth (FR-010, FR-011, R-019)

Needs the `reverse_proxy` deploy after `memory` (plan step 6): `$MEM` goes through Caddy. Step 3
is the precondition for the `hermes` deploy.

1. The deploy log shows the `deploy-probe` retain, recall and delete passing.
2. Unauthenticated and wrong-key requests both return 401:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' "$MEM/owner/stats"
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer hmem_wrong' "$MEM/owner/stats"
   ```

3. `GET $MEM/owner/stats` with the Hermes key returns 200 over HTTPS through Caddy. Do not deploy
   `hermes` until this passes.
4. A `DELETE $MEM/owner/memories` (clear bank) with the Hermes key returns 403.
5. Creating a webhook (`POST $MEM/owner/webhooks`) and changing the bank config
   (`PATCH $MEM/owner/config`) both return 403 with the Hermes key, and also with the admin key
   for the webhook (research R-001: refused for every scope).

**Run 2026-10-31** (PROD):
- Step 1: the `memory` apply (run 41205103733) passed the deploy probe: retain, recall, count and
  delete.
- Steps 2–5 through `https://memory-api.hus-sky.no`: no key 401, wrong key 401, Hermes stats 200,
  Hermes clear bank 403 (`scope readwrite may not delete_bank`), Hermes and admin webhook 403
  (`create_webhook is disabled`), Hermes bank config 403 (`scope readwrite may not
  update_bank_config`).
- Gateway scope (SC-003, § 5 step 2 in advance): the memory key gets 200 on `hermes-embed` and 401
  on `hermes-fast` ("This key can only access models=['hermes-embed', 'hermes-rerank']").
- Caddy's first certificate attempt failed (TXT record not yet published); the retry succeeded
  after about 3 minutes, as for earlier vhosts.

## 4. Hermes remembers (US-1, FR-005)

1. Tell Hermes (Open WebUI with the agent model, or ntfy) "my test parrot is called Probe-097".
2. Open a **new** conversation and ask, as the first message, "what is my parrot called?". The
   answer is Probe-097.
3. Ask in Norwegian, "hva heter papegøyen min?", and get the same answer.
4. Ask about a cat that was never mentioned. The agent says it does not know.
5. In the store, the unit carries `client:hermes`:

   ```sh
   curl -s -H "Authorization: Bearer $HERMES_KEY" "$MEM/owner/tags"
   ```

**Run 2026-10-31** (PROD, owner): steps 1–4 as expected: Probe-097 recalled on the first turn of
a new conversation, in English and Norwegian, and the unknown cat answered as unknown. The
`owner` bank then held 2 documents (one per test conversation), both units tagged
`client:hermes`, 0 failed operations. `hermes memory status`: provider `hindsight`, available; 0
memory errors in the agent log.

## 5. Cost and locality (US-3, SC-003, SC-004)

1. After a day of use, in Grafana (`llm-router` dashboard), the `memory` key shows only
   `hermes-embed` and `hermes-rerank` requests.
2. Directly with the memory key: `POST http://192.168.1.220:4000/v1/chat/completions` with
   model `coder` returns 401 or 403 (model not in key scope, R-011).
3. On the memory LXC, `ss -tnp` over an hour shows connections only to `192.168.1.220:4000`
   (gateway) and from the reverse proxy.
4. Stop the memory stack. A Hermes conversation still completes, a plugin failure line appears
   in Loki within 5 minutes (SC-010), and Open WebUI chat still works. Restart the stack.

## 6. Shared memory and Claude Code scopes (US-2, SC-005, SC-009)

Precondition: the hooks are enabled in the private Claude Code installation only (`claude-private`
on the Mac, R-010).

1. In Open WebUI (plain model, not the agent), say "my test sister lives in Probe-by". In
   `claude-private` in a repository under `~/Development/private`, ask "where does my test sister live?". The answer is Probe-by.
2. Tell Claude Code "my test boat is called Probe-båt". Ask Hermes over ntfy and get it back.
3. `list_tags` (MCP from any client) shows `client:open-webui` and `client:claude-code` on those
   units.
4. Open the EY Claude Code (`claude`) in a repository under `~/Development/private`, and
   `claude-private` in a directory outside it. Neither sends anything (no settings entry in the
   first, the path guard in the second), and the store shows no new `cc-` document.
5. Set `claude-code` to `readonly` and deploy `memory`. A Claude Code retain is refused (403 in
   the hook log), recall still works, and Hermes and Open WebUI are unaffected.
6. Remove `claude-code` and deploy. Claude Code gets 401, the others are unaffected. Restore the
   original scope.

## 7. Open WebUI migration (FR-016)

1. Before the deploy, note the row count of Open WebUI's `memory` table.
2. After the deploy, the store has the same number of `owui-memory-*` documents, tagged
   `origin:open-webui-memory`.
3. The Personalisation › Memory setting is gone (memories off), and a fact from the imported set
   is answered in a new chat through the filter.

**Run 2026-10-31** (PROD, `hermes` deploy of `190ea7a`): the `memory` table held 7 non-empty rows
and `memories.enable` was `true` before the deploy. The LAB rehearsal skipped all five import
tasks and installed the filter. In PROD the deploy imported 7 memories ("Imported 7 Open WebUI
memories."); the `owner` bank then held 7 `owui-memory-*` documents, all tagged
`origin:open-webui-memory` and `client:open-webui`. `memories.enable` is `false`, the `memory`
table still holds its 7 rows, and the `shared_memory` filter is active and global ("Loaded module:
function_shared_memory", no errors). Step 3: the owner asked about a saved memory in a new chat
and got it back.

## 8. Correct and forget (US-5, R-012)

1. Ask "what do you remember about my test parrot?". The listing shows the Probe-097 unit.
2. Correct the parrot's name to Probe-098 (`update_memory`). Every client now answers Probe-098.
3. Forget it by asking any client to forget the parrot (`update_memory` redacting the fact, or
   `invalidate_memory`). No client recalls it.
4. **Resurrection check** (R-012 UNVERIFIED): in the same Hermes session as step 1, add two
   more turns, then ask in a new conversation. The parrot is still forgotten. If it comes back,
   switch the adapters to per-turn documents (R-012) and repeat.
5. Remove every `Probe-*` test fact the same way.

**Run 2026-11-01** (PROD, owner through Hermes): Hermes answered as expected at every step, but
the store did not change. Hermes corrected and forgot the parrot in its built-in memory files,
never through `update_memory` or `invalidate_memory`, and the plugin had mirrored the built-in
"Probe-098" add into the store without mirroring the removal. Afterwards 4 live units still held
the parrot, and recall ranked them first in English and Norwegian. The test facts were then
removed with Hermes's key over MCP (`update_memory` dropped the parrot turn from a unit that also
held a real fact, `invalidate_memory` retired the other 3), after which recall returned no
parrot. Fix: built-in notes off with a one-shot import (the owner profile stays, so standing
preferences keep reaching every prompt), and a `SOUL.md` that routes corrections and forgets to
the memory tools (FR-001, amended). Steps 1–4 are re-run through Hermes after that
deploy.

**Resurrection observed 2026-11-01** (R-012, step 4): the parrot unit edited with `update_memory`
in Hermes session `api-ff5d…` came back as a new unit when that Open WebUI chat got another turn.
The plugin resends the whole session on each retain, the document's original text still held the
parrot, and the chunk was rebuilt from it. The three invalidated units, in sessions with no new
turns, stayed retired. An edit to a session that is still in use therefore does not hold: T071.
The same day the owner had 9 units retired with `invalidate_memory` (the resurrected chunk, a
stale copy of a replaced built-in note, and 7 agent process narratives), leaving 31 live units;
the parrot chat is to be deleted in Open WebUI so it cannot rebuild again.

**Re-run 2026-11-01 19:00 Oslo time** (PROD, owner through Hermes, after PR #340: built-in notes off,
`SOUL.md` routing): steps 1–3 as expected. Hermes recalled Probe-100, corrected it to Probe-101,
and on the forget request retired five related units with `invalidate_memory`. Step 4 failed in
the store: the next turn in the step-1 chat rebuilt the retired chunk as a new live unit, and the
forget turn itself, naming Probe-100 and Probe-101, was stored like any other turn, so recall
ranked the turtle first again. Both units were retired by hand. Fix: one document per turn in the
memory server (T071, research R-012); the owner deletes the test chats in Open WebUI.

## 9. Restore drill (US-4, SC-006)

```sh
ansible-playbook -i ansible/inventories/prod/hosts.yml ansible/playbooks/memory-restore-drill.yml
```

Expected:

- `pg_restore` completes, and the stats match `stats.json`.
- Each probe in `drill-probes.json` finds its unit in the top 3 recall results.
- The export ZIP imports into an empty bank with the same document count.
- The teardown leaves no container or directory behind.

**Run 2026-11-01** (archive `memory-backup-20261101-053006`, the first with probes): FAIL, on the
probe check rather than the restore. The dump restored 17 documents and 22 nodes, matching
`stats.json`. 2 of 3 probes found their unit in the top 3. The third ranked 5th of 18 on the
live store too, so the restored copy recalled as the live one does, and the export leg did not
run. The teardown removed the stack and the drill directory. The backup now keeps only probes
that rank in the live top 3 (research R-014, amended); the drill is re-run on the next archive.

**Run 2026-11-01, 11:00 UTC** (archive `memory-backup-20261101-103909`, taken by hand after the
probe fix; the backup log reads "Drill probes: 3 kept of 4 tried"): PASS. The dump restored 23
documents and 32 nodes, as recorded; 3 of 3 probes found their unit in the top 3; the export ZIP
imported 23 documents into an empty bank. No container or directory was left behind. Two drill
defects surfaced on the way, both in the export leg, which had never run before: the `uri`
module read the ZIP from the controller, and it base64-encodes multipart file parts, which the
API does not decode ("not a readable .zip"). The upload is now `curl` on the LXC, with the key on
stdin.

## 10. Size (SC-007)

After the Open WebUI import and a week of use, peak memory use on the LXC
(`node_memory_MemAvailable_bytes` in Grafana) stays below 70 % of 2048 MB.

## 11. Web UI (FR-023, SC-011)

1. The portal page shows a "Memory" tile linking to `https://memory.hus-sky.no`.
2. In a private browser window, the tile opens `/login`, and no bank, document or memory is
   visible. `curl -s -o /dev/null -w '%{http_code}\n' https://memory.hus-sky.no/api/banks` returns
   401.
3. Sign in with `memory_ui_access_key`. Browse bank `owner`. Search for "test parrot" and correct
   the unit. Hermes, Open WebUI and Claude Code all recall the corrected text, and `list_tags`
   shows `client:control-plane` on a memory added in the UI.
4. Delete the test conversation's document in the UI, and confirm that no client recalls it.
5. Try bank settings, adding a webhook and a reflect query in the UI. Each shows an error (403),
   and the API container log shows the refusal. The UI does not crash or restart
   (`docker ps` uptime unchanged).
6. An empty login key is caught before deploy, by the role's preflight and by
   `test_memory_config.py`. No PROD test is needed: the guard test runs in CI.

**Run 2026-10-31** (PROD, owner, web UI at `https://memory.hus-sky.no`, portal tile "Memory"):
- Login with `memory_ui_access_key` works; `/` redirects to `/login` without a session.
- After the read-view rule (#331), the home, profile, graph, timeline, documents and background
  operations views load without refusals. The first click-throughs showed the refused reads that
  led to #327's view list and then #331's read rule.
- The store showed live Hermes use: 4 memories, 2 documents, 15 links; 13 background operations,
  all completed, including a graph-maintenance job after a retain (refused before #327).
- The Consolidation card shows "pending 4, last: never" permanently: consolidation is off by design
  (FR-004), so units are never consolidated. Cosmetic.
- Resource use: `memory_ui` 52 MiB of its 384 MiB limit; the LXC 525 of 2048 MB with all three
  containers (SC-007 headroom well above 30 %).

## Runbook: failed retains (`MemoryRetainFailures`)

1. Open the web UI's operations page (or `GET $MEM/owner/operations?status=failed` with the
   admin key) and list the failed operations.
2. Fix the cause. It is usually the gateway or the Mac.
3. Retry each operation in the web UI, or with `POST $MEM/owner/operations/{id}/retry`.
