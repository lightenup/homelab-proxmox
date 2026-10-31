# Research: Two-way ntfy (095)

All findings measured 2026-10-25 against the live estate: ntfy server `v2.28.0` (source tarball),
`nousresearch/hermes-agent` `v0.21.6` (inside the running `hermes_agent` container), ntfy Android
docs. File references inside the agent image are paths under `/opt/hermes/`.

## R-001: Is an ntfy conversation an interactive approval surface?

- **Decision**: Yes. Phone-originated sessions get the gateway's blocking approval round-trip.
- **Evidence**: `tools/approval.py:114-240` keeps a per-session gateway approval queue
  (`_gateway_queues`, `register_gateway_notify`, `resolve_gateway_approval`). It is answered by the
  `/approve` handler (`gateway/slash_commands.py:1195`). `BasePlatformAdapter.supports_exec_approval_buttons`
  (`gateway/platforms/base.py:2889`) is False for ntfy, which does not override
  `_send_exec_approval_prompt`, so "the runner otherwise sends the plain-text `/approve` prompt".
  `approvals.cron_mode`, `single_query_mode` and `unattended_mode` stay `deny`, which keeps FR-005
  unchanged.
- **To verify on LAB first** (task T-gate): one flagged command from an ntfy session produces a
  text prompt, and `/approve` runs it.

## R-002: Slash commands that would bypass the model (`/yolo`, `/update`)

- **Finding**: `/yolo` is a session-scoped approval bypass (`tools/approval.py:324`, `:485`). The
  ntfy plugin registers `allow_update_command=True` (`plugins/platforms/ntfy/adapter.py`,
  `register`). Over ntfy, a single message could therefore turn approvals off, or update the agent.
- **Decision**: Gate slash commands on the ntfy platform with upstream's per-platform policy
  (`gateway/slash_access.py`). Set `allow_admin_from` to a value that matches no user id, which
  enables gating with no admin. Set `user_allowed_commands` to an explicit allowlist:
  `approve, deny, new, reset, stop, status` (`help` and `whoami` are always allowed).
  **Superseded by spec FR-014**, which adds `compress, retry, undo, usage, title, model`.
  `/yolo`, `/update` and every other command are then refused.
- **Open detail (resolved in R-014)**: the keys go in the root-level `ntfy:` block of
  `config.yaml`. Confirm on LAB that `/yolo` over ntfy is refused before PROD.
- **Alternatives rejected**: `approvals.mode` changes do not stop `/yolo`. A derived image would
  break `083` R-002 (stock image).

## R-003: Sender identity

- **Finding**: ntfy never exposes the publisher to subscribers. `model/model.go:50-51`: `Sender
  netip.Addr json:"-"` and `User string json:"-"`. The adapter therefore pins `user_id` to the
  **topic name** (`adapter.py:_on_message`). The agent's authz is fail-closed when no allowlist is
  set (`gateway/authz_mixin.py:_principal_authorized`).
- **Decision**: Identity = write ACL on the inbound topic. `NTFY_ALLOWED_USERS=hermes-in`, exactly.

## R-004: One phone credential or two?

- **Finding**: The Android app supports one user per server, and sets `Authorization` itself
  ("If you have a user configured for a server, you cannot add an Authorization header", docs
  *Subscribe from your phone § Custom headers*). ntfy ACLs attach to **users**, not tokens
  (`auth-access: user:topic:perm`, `user/access_cache.go`).
- **Decision**: The phone credential is the existing **`owner`** user. Add `owner:hermes-in:read-write`
  and `owner:actions:read-write` alongside `owner:*:read-only`. The longer pattern wins
  (`user/access_cache.go:Lookup`, rule 2), and it must be `read-write`, not `write-only`, because
  the specific entry replaces the wildcard's read. Resolves backlog open question 1.
- **Consequence**: The owner's web-app password grants the same write access. It is the same
  person, and the runbook treats the owner token and password as shell credentials (FR-010).

## R-005: Agent can read its own secrets

- **Finding**: `/opt/data/.env` is `-rw------- hermes:hermes` (27 KB, all agent secrets), and the
  terminal backend runs as uid `hermes`. Upstream scrubs credentials from the subprocess *env*
  (`tools/environments/local.py:_scrub_credentials`), but the file stays readable.
- **Decision**: The agent's ntfy user `hermes` gets **read-only** on `hermes-in` and keeps
  write-only on `hermes`. No credential that can write `hermes-in` or `actions` is ever rendered
  on the agent's LXC (FR-001/002, SC-002).

## R-006: Native approval buttons without a credential in the message (FR-012)

- **Finding**: `http` action headers come only from the message, and the app adds no auth of its
  own (docs *Publishing § Send HTTP request*). An `http` button would therefore embed a token in
  agent-composed content, which fails FR-012.
- **Candidate**: a `broadcast` action with `intent=io.heckel.ntfy.SEND_MESSAGE` and
  `extras.base_url=https://ntfy.hus-sky.no, extras.topic=hermes-in, extras.message=/approve`. The
  ntfy app "will forward the intent as a HTTP POST request to publish a message" (docs *Subscribe
  from your phone § Send messages using intents*), presumably with the server's configured user.
  **No credential is in the notification**, and only a press on the phone produces the publish.
- **Unverified (on-device test, P2 gate)**: (a) the app receives its own broadcast from its own
  action button; (b) `SEND_MESSAGE` publishes with the configured `owner` user, so it is not
  refused.
- **Residual risk**: a compromised agent can publish a notification on `hermes` with a misleading
  label whose button sends `/approve`. This is the same class as the agent asking the owner to
  type `/approve`. The mitigation is UX: approval notifications always show the command, and the
  runbook says never to approve without reading the command.
- **Implementation**: needs the ntfy adapter to override `_send_exec_approval_prompt`, which is a
  code change. Preferred route: an upstream PR to `nousresearch/hermes-agent`, adopted by a pin
  bump. A derived image is not chosen (`083` R-002). Until then approvals stay typed (US-2).

## R-007: Offline gap (FR-006)

- **Finding**: The adapter subscribes with no `since=` → `SinceNoMessages` (`server/server.go:1789-1793`):
  no replay, which is the desired behaviour. The gateway has lifecycle hooks loaded from
  `$HERMES_HOME/hooks/<name>/{HOOK.yaml,handler.py}` with a `gateway:startup` event
  (`gateway/hooks.py:1-10`). The heartbeat job writes `/heartbeat/hermes_agent.prom` every 15
  minutes.
- **Decision**:
  1. A `gateway:startup` hook posts on `hermes`: "back online at T. Last heartbeat H. Anything sent
     to hermes-in between H and T was not received." It always posts, because restarts are rare
     (deploys), so no threshold is needed for this case. It posts at ntfy priority 2 (silent),
     because 083 kept restarts silent (spec FR-006).
  2. Mid-run stream drops: once 095 removes the permanent 403, sustained `[Ntfy] Stream error`
     lines become a real signal. A `092` Loki rule (warning, 10 min window) alerts via the normal
     route, which includes Pushover. Short blips stay silent.
- **Hook deployment**: rendered by Ansible into `hermes_data_dir/hooks/` and bind-mounted
  **read-only** over `/opt/data/hooks/gap-notice`, so the agent cannot rewrite gateway-executed
  Python. The same treatment as `agent-config.yaml`.

## R-008: Audit logging (FR-009)

- **Finding**: The adapter logs inbound messages only at DEBUG (`Message on topic …`). Approvals
  are logged at INFO (`User approved %d dangerous command(s) via /approve`, slash_commands.py:1211).
- **Original decision (superseded 2026-10-26)**: a read-only hook (`agent:start` and `command:*`)
  logging one line per inbound message and per approval or denial.
- **Revised decision (2026-10-26, owner): no audit hook; use upstream's `gateway.log` lines,
  collected by T072.** Verified against the v0.21.6 source and on the LAB rig with a temporary
  probe hook (removed afterwards):
  - Upstream already writes all four events at INFO to `gateway.log`: inbound (`run_turn.py:2148`,
    first 80 characters with newlines collapsed), approve with scope (`slash_commands.py:1211`),
    deny (`:1235`), refused slash command (`run_busy.py:1127`). Bare-word replies reuse the
    approve/deny handlers (`run_busy.py`). All four lines were seen on the rig during T008.
  - The hook cannot see the decisions that matter. Probe results: `command:status` fired while
    the agent was idle; `/yolo` produced the refusal line and **no hook event** (gating runs before
    hooks, `run_inbound.py:843` vs `:847`); `/approve` sent while the turn waited on the approval
    ran the command and logged `via /approve (once)`, but **no `command:approve` event** (by design
    upstream: "The running-agent path deliberately does NOT fire these").
  - The hook's only addition would be the ntfy message id on inbound lines: `agent:start` can read
    it from the session context (`HERMES_SESSION_MESSAGE_ID`, seen as `mcmtxTjd9Y7h`). That alone
    doesn't justify carrying code against an internal API (Constitution IV). FR-009 is amended:
    agent-side lines carry no message id; relay lines (P2) still must.
  - `gateway.log` is upstream's permanent component log (`hermes_logging.py`: INFO+, rotating
    5 MB × 3, `RedactingFormatter`), so Alloy can tail it.
- **Consequences**: T011 and the audit half of T017 are dropped; the hooks mount (T018/T019)
  stays for the gap-notice hook (US3, no upstream equivalent); T072 now also serves FR-009; T020's
  audit check queries the file stream.

## R-009: Reply-to-report context (FR-007, US-4)

- **Finding**: No-agent cron output is delivered out-of-process (`standalone_sender_fn`) and is not
  part of any session. An ntfy reply starts or continues the `hermes-in` session without that text.
- **Decision (P2, needs a spike)**: Cron delivery also appends the report to a small "recent
  reports" file under the agent's data dir. A hook injects the latest report (or the one named) as
  context for a phone session on `agent:start`. If the upstream hook context cannot inject, fall
  back to a skill that reads the file. The spike decides which.

## R-010: Action buttons for alerts (US-5)

- **Finding**: ntfy server-side templates only support `title`, `message` and `priority`
  (`server/types.go:140-144`). The Alertmanager → ntfy direct path (`082` FR-005) **cannot** attach
  per-alert buttons. A static `?actions=` query parameter could not name the alert.
- **Decision**: The relay becomes Alertmanager's ntfy-side webhook receiver. It formats the
  notification itself (porting `homelab-alertmanager.yml`'s title, priority and message logic into
  tested Python) and publishes to `alerts` with up to three `broadcast`/`SEND_MESSAGE` buttons
  (R-006) whose message is a compact action command (contract `action-command.md`). The
  `alertmanager` ntfy user is retired, and the relay's own user writes `alerts`, so the rule of one
  publisher per topic still holds. Pushover is untouched, so the relay is never the only path.
- **Alternatives rejected**: an `http` button straight to Alertmanager, which would expose `:9093`
  and embed a credential. Routing presses through Hermes, which is non-deterministic and widens
  egress. A companion message sent after each alert, which would mean two notifications per alert.

## R-011: Where the relay runs

- **Decision**: As a container in the **monitoring** LXC's compose stack (`monitoring_stack`
  role). It reaches Alertmanager on the compose network (silences API, alert state), receives
  Alertmanager's webhook locally, and reaches ntfy via Caddy (already allowed). Nothing new is
  exposed.
- **Rationale**: The first and main action is Alertmanager's. A new LXC for roughly 300 lines of
  code fails Code Economy (constitution IV). It is placed beside its only dependency, the same way
  Alloy sits in that stack.
- **Heartbeat (spec FR-008)**: the relay exposes `/metrics` with
  `ntfy_action_relay_heartbeat_timestamp_seconds`, refreshed by the subscription loop; Prometheus
  scrapes `action-relay:8080`; `NtfyActionRelayDown` alerts via the normal route.
- **Name resolution**: the relay reaches `https://ntfy.<domain>` through the same `extra_hosts`
  entries the blackbox exporter uses (`blackbox_static_hosts`).
- **Revisit when** an admitted P3 action needs reach that the monitoring LXC should not have, for
  example `pve` for a backup re-run.
- **Implementation language**: Python 3.11, standard library plus `httpx` (already the estate's
  choice in the agent). Code lives in the repo's `python/` package with `pytest` tests, so it
  inherits the coverage and mutation gates (constitution: testable logic over shell).

## R-012: Replay and expiry for button presses (FR-008)

- **Finding**: ntfy caches messages for 72 h. A subscriber reconnecting with `since=` could replay
  old presses. Message ids are unique.
- **Decision**: The relay subscribes with no `since` (like the agent) and dedupes by message id
  (a bounded LRU). Each action command carries `exp=<unix>`, set by the relay when it rendered the
  button (render time + 24 h, so repeat notifications of a long-running alert carry live buttons), and refuses anything expired. Silences are idempotent per
  (alert fingerprint, duration). If a matching active silence already exists, the relay reports
  it and creates nothing new.

## R-013: Chat UX split across two topics

- **Finding**: The owner types in `hermes-in` and replies arrive on `hermes`, so two topic views.
  The agent must not write to `hermes-in` (R-005).
- **Decision**: Accept it. Each agent reply carries a `view` action
  `ntfy://ntfy.hus-sky.no/hermes-in` labelled "Reply", one tap back to the message bar. The phone
  mutes notifications on `hermes-in`, because its own messages need no alert.
- **Note**: The deep-link `view` action needs adapter support for actions on normal messages, the
  same upstream PR as R-006. Until then the owner switches topics by hand.

## R-014: Approval semantics over ntfy (source check for the T008 LAB gate)

Read 2026-10-25 from `NousResearch/hermes-agent@v0.21.6` source (tag `f27cdbc`). The LAB gate
(T008) still runs, but it now confirms the findings below instead of discovering them.

- **Prompt text states scope and deadline (FR-004)**: met upstream. The text fallback
  (`gateway/run.py:590` `_format_exec_approval_fallback`, strings at `locales/en.yaml:619-626`)
  reads: "Reply `/approve` to run it once, `/approve session` to allow this pattern for the rest
  of this session, `/approve always` to allow it permanently, or `/deny` to cancel. If you don't
  answer within {window} it will NOT run."
- **One pending prompt per conversation (FR-004)**: met upstream. Concurrent tool calls queue
  their prompts behind `_ConcurrentToolAuthorizationGate` (`agent/tool_executor.py:486-552`),
  whose lock timeout derives from `approvals.timeout` plus a margin, so it does not expire while a
  prompt can still be answered. The gateway queue is FIFO, and a bare `/approve` resolves the
  oldest entry (`tools/approval.py:139`).
- **`/new` and `/reset` end session approvals**: met upstream. `_handle_reset_command`
  (`gateway/slash_commands_session.py:155`) → `_clear_conversation_scope` →
  `_clear_session_boundary_security_state` (`gateway/run_agent_cache.py:414`) →
  `tools.approval.clear_session`, which drops session approvals, `/yolo` and pending prompts.
- **`/approve session` is pattern-scoped**: `_persist_choice` (`tools/approval.py:381`) adds the
  flagged *pattern key* to the session's approved set, so later commands of the same kind run
  without a prompt and other flagged commands still prompt.
- **`/approve always` is permanent and process-wide (conflict)**: it adds the pattern to the
  permanent allowlist in memory, then tries `save_config`. With our read-only `config.yaml` the
  save fails and only a warning is logged (`Could not save allowlist`), but the in-memory entry
  stays until the process restarts. `_unattended_deny` (`tools/approval.py:635-650`) lets
  permanently approved patterns through cron, single-query and unattended surfaces, which breaks
  FR-005 for that pattern until a restart. No configuration removes the choice: `allow_permanent`
  is false only on a smart-deny override (`tools/approval.py:841`), and slash gating
  (`gateway/slash_access.py`) matches command names, not arguments.
- **Bare-word replies**: while a prompt is pending, `yes|ok|okay|confirm|y|approve|👍` approve once,
  `no|deny|…|👎` deny, `session` approves for the session, and `always|remember` approve
  permanently (`gateway/run_busy.py:516-555`). These are routed through the same `/approve` and
  `/deny` handlers, so they log the same lines. With no prompt pending, they are ordinary chat.
- **Slash-gating YAML path (R-002 open detail)**: resolved. It goes in the root-level `ntfy:` block
  of `config.yaml`, beside `gateway_restart_notification`; `_bridged_keys` copies
  `allow_admin_from` and `user_allowed_commands` into the platform `extra`
  (`gateway/config_loader.py:203-243`). The ntfy user id is the topic name (R-003), so
  `allow_admin_from` must be a non-empty value that is **not** `hermes-in`.
- **Decision (permanent approvals; Clarifications, option B)**: ship slice 1 with a detection
  control. The audit hook and the upstream log line `User approved %d dangerous command(s) via
  /approve (always)` (`gateway/slash_commands.py:1206`) feed a Loki rule,
  `HermesPermanentApprovalGranted`, that alerts on any match through the normal route. The runbook
  revokes the grant by restarting `hermes_agent`; with the read-only config, a restart clears it.
  In parallel, open an upstream PR adding a switch (for example `approvals.allow_permanent: false`)
  that removes the permanent choice from prompts, `/approve` and bare words. When it ships, set it
  and keep the alert as a backstop.
- **Decision (session scope; Clarifications, option A)**: the spec adopts upstream semantics.
  `/approve session` covers the approved pattern for the rest of the conversation, other flagged
  commands still prompt, and `/new` or `/reset` ends it. `/yolo` stays refused (R-002).
- **LAB finding 2026-10-26 (T008 step 1): a single-file `rm` in the agent's home is not flagged.**
  Sent `delete /opt/data/scratch.txt`, then `delete /opt/data/scratch2.txt`, on `hermes-lab-in`. Both
  ran with no prompt (`state.db` transcript: `terminal` → `rm /opt/data/scratch*.txt && echo
  "deleted"`, exit 0). Not a gate bypass. Evaluating the guard in the running container showed
  `detect_dangerous_command(...) == (False, None, None)`, with the gate context correct:
  `platform=ntfy`, `is_gateway=True`, `approvals.mode=manual`, no yolo, no permanent allowlist
  match. Cause: `_normalize_command_for_detection` (`tools/approval_detection.py:534-535`) folds the
  resolved `HERMES_HOME`/`HOME` (both `/opt/data` in the image) to `~/` before matching, so
  `rm /opt/data/x` becomes `rm ~/x`, which no pattern flags. A non-recursive delete of one file
  in the agent's own home is outside upstream's dangerous set by design. The same command
  evaluated on a dev Mac returned `True` only because `HOME` differs there; that's why the
  quickstart and the spec's US2 Independent Test chose a bad example. Flagged in the container:
  `rm -r`/`rm -rf` (recursive delete), `chmod 777` and `chmod -R 777`, and `rm` outside the home
  (`/tmp`, `/etc`: delete in root path). quickstart § 0.2 and spec US2 now use `rm -r` on a
  scratch directory. **Residual risk, recorded rather than fixed**: the agent can delete
  individual files in `/opt/data` (its own state, memory, jobs) without approval. The deploy-owned
  `config.yaml` is mounted read-only, and `.env` writes are covered by file-tool and pattern
  guards. Adding an `approvals.deny` or custom pattern for this would be a new policy beyond what
  095 set out to verify. Raise it as a follow-up if wanted.
- **LAB finding 2026-10-26 (T008 step 2): approval log lines go to a file, not stdout.** After
  `/approve` on `hermes-lab-in`, `docker logs hermes_agent` showed no approval line. The line is in
  `/opt/data/logs/gateway.log` (and `agent.log`): `INFO gateway.run: User approved 1 dangerous
  command(s) via /approve (once)`. Container stdout carries WARNING and above, and that's all 092's
  Docker collection ships. So the planned `HermesPermanentApprovalGranted` rule, which selected
  `container="hermes_agent"`, could never have fired. Fix: T072 adds `gateway.log` through 092's
  `alloy_file_logs`; T022/T023 select the file stream. `Stream error` lines (T030) are WARNING and
  do reach stdout (they were the 093 noise), so T030 is unaffected. Whether the audit hook's
  output (T017) reaches stdout is checked by T008 step 8.
- **Verified on LAB 2026-10-26 (T008 steps 1-9, rig `lab-pve-01`, image v0.21.6, T015 config):**

  | Step | Result |
  |---|---|
  | 1 Prompt text | PASS: command, reason ("recursive delete"), once/session/always/deny, deadline ("5 minutes", then "15 minutes" after T015) |
  | 2 Approve / deny / timeout | PASS: approve ran; deny blocked and the agent did not retry; no answer → "Approval timed out ... NOT run" |
  | 3 Gating, `/help`, allowed commands | PASS: `/yolo` and `/update` → "admin-only here" (logged `Slash command /yolo denied ... not in user_allowed_commands`); `/help` = FR-014 set + help/whoami; retry/title/usage/status/model/undo/compress all answer |
  | 4 Session scope | PASS: `/approve session` → second `rm -r` ran unprompted; `chmod 777` still prompted; after `/new` `rm -r` prompted again |
  | 5 One pending prompt | PASS: second prompt appeared only after the first was answered |
  | 6 Permanent until restart | PASS: `/approve always` → "pattern approved permanently", `via /approve (always)` in gateway.log, `Could not save allowlist: Read-only file system`; after `docker restart` the same `rm -r` prompted again |
  | 7 Long reply | FAIL on the stock adapter (next finding); **PASS 2026-10-26 with the R-018 shim**: `(1/2)` ending 1037, `(2/2)` ending 1200 |
  | 8 Audit lines | PASS (redefined, R-008 revised): `gateway.log` on the rig holds `inbound message:`, `via /approve (once\|session\|always)`, `via /deny` and `Slash command /yolo denied`; the Loki half waits for T072 at PROD (T020) |
  | 9 Stream-error interval | PASS: ntfy blocked 15 min on the rig (iptables REJECT to 192.168.1.211:443, auto-removed); adapter backoff 2s → 5s → 10s → 30s → 60s, then capped at 60s (19 `Stream error` WARNINGs, on stdout so already in Loki via 092). 60s ≤ the 5m range window, so `HermesNtfyStreamDown` (T030) keeps `[5m]`. Reconnect logs nothing; a `/status` round-trip right after the unblock confirmed recovery |
  | 3 (rerun) `/cancel` | PASS after adding it to FR-014: `/undo` → `/cancel` → "/undo cancelled. Conversation unchanged." |

  Further findings from the run, none blocking:
  - **`/approve always.` (trailing full stop) is treated as `/approve` once** (logged `(once)`).
    That fails safe but silently. Phone autocorrect adds full stops. Runbook (T024): type the
    scope word bare.
  - **`/undo` and `/new` confirmations offer `/approve`, `/always` or `/cancel`**; `always` and
    `cancel` are outside FR-014, so `/approve` is the only usable answer. Whether to add `cancel`
    is an owner decision (open).
  - **A pending `clarify` question survives `/new`**: the next message is consumed as its answer
    (`Gateway intercepted clarify text response`) and no turn starts. Nothing runs; it's a
    usability trap to note in the runbook.
  - **The model often refuses or interrogates a destructive request before calling the tool**,
    and after a deny it may ask (via `clarify`) instead of retrying. That's defence in depth, but
    not deterministic: never rely on it, and phrase gate tests so the model reaches the gate.
  - **`Could not save allowlist` is a WARNING on stdout**, so it's already in Loki via 092, and
    it fires exactly on a permanent approval when `config.yaml` is read-only. It's a candidate
    selector for T023 that doesn't depend on T072.
  - **Model-side outages surface honestly over ntfy**: with the Mac asleep, the router returned
    429 (`cooldown_list=['balanced-local']`) and the agent replied "Your request was not
    processed". `LlmRouterLocalTierDown` fired and resolved on its own. The rig shares the PROD
    router key (R-016), so rig traffic counts against PROD limits during the gate.
- **LAB finding 2026-10-26 (T008 step 7): replies over 4096 characters are cut silently.** A
  4892-char reply arrived as exactly its first 4096 characters, with no marker and no follow-up.
  `gateway.log`: `response ready ... response=4892 chars`, then the adapter WARNING `[Ntfy]
  Message truncated from 4892 to 4096 chars (ntfy limit)`. Cause: `plugins/platforms/ntfy/
  adapter.py:280-284` slices the body to `MAX_MESSAGE_LENGTH = 4096` in `send()`, and the
  adapter keeps the base default `splits_long_messages = False`. Chat replies get no
  gateway-level handling, and only cron delivery (`gateway/delivery.py` `_cap_oversized_output`)
  adds a visible "[truncated, full output saved to ...]" footer. The base class already has a
  splitter, `BasePlatformAdapter.truncate_message()`, which produces `(1/3)` chunks and keeps code
  fences, and the WhatsApp Cloud and BlueBubbles adapters use it. Our server's
  `message-size-limit` is 32k, so the 4096 cap is the adapter's own choice, not ntfy's. No
  configuration changes it. US1 AS-4 ("split or visibly cut") fails on v0.21.6. The WARNING
  reaches stdout and therefore Loki.

## R-015: How the LAB rig is brought up, deployed and torn down (T008 gate)

Checked 2026-10-25 against `scripts/lab/pve-lab`, `scripts/lab/pve-service-deploy`,
`.github/workflows/{proxmox-apply,lxc-deploy-lab}.yml` and `pve` itself (as `ci`).

- **No existing path deploys an application role to the rig [repo]**. `lxc-deploy-lab.yml` runs
  `pve-service-deploy --environment lab`, which deploys the **production** LXC with
  `deploy_environment=lab` (backlog 067; 083 R-011). `lab_inventory` is never true there, so it
  can only exercise the "pipeline LAB stage" branch of `agent.env.j2`, never the scratch pair.
  The only thing that targets `lab-pve-01` (10.99.0.10) is `pve-lab`, whose playbooks verify a
  nested Proxmox install and never run a service role.
- **Reach [pve]**: `ci@pve` routes to 10.99.0.0/24 over `vmbr99` (gateway 10.99.0.1). The dev
  Mac cannot (no route; Zscaler blocks Tailscale), so every rig command runs on `pve`.
- **Rig lifecycle [repo]**: `pve-lab run` destroys the VM on exit unless `--keep` is given
  (`pve-lab:1314-1319`); `pve-lab down` destroys every VM in 9000–9099 tagged
  `ManagedBy=homelab-proxmox` (`check_safety`), plus nested 100/101. `pve-lab up` takes no
  arguments from the CLI, so it always clones the tier-1 template. Decision: bring the rig up with
  `pve-lab run --profile hypervisor-control-plane --keep`, which clones the tier-2 template and
  sizes it to 4 GB / 2 vCPU / `cpu host` (`pve-lab:780`).
- **Template [owner decision, 2026-10-25]**: tier 2. The hermes stack does not fit the 2 GB
  tier-1 template (agent `mem_limit: 3g`, plus Open WebUI and SearXNG). Tier 1 would need a
  `scripts/lab/` edit (protected path) or a post-clone `qm set` outside the ci sudoers. The rig
  carries a nested PVE it does not use (plan, Complexity Tracking).
- **SSH key [repo]**: without `PROVISION_SSH_KEY`, `pve-lab` generates a key under `/tmp` and
  deletes it on exit (`lib/rebuild.sh:12-45`), so a later job could not reach the kept rig. The
  workflow passes a stable `PROVISION_SSH_KEY=/home/ci/.ssh/lab_rig_ed25519`, created on `pve`
  if missing. It is a LAB-only key, never in vault and never leaves `pve`.
- **Vault [repo]**: both `up` and `deploy` read the persistent password file on `pve`
  (`/var/lib/homelab-proxmox/vault/.ansible_vault_pass`, the same file `pve-service-deploy`
  prefers), so no vault secret passes through GitHub Actions.
- **Deploy [design]**: `ansible/playbooks/hermes_lab_rig.yml` runs `geerlingguy.docker` and
  `hermes` on `lab` with `-e deploy_environment=lab`. It loads `group_vars/services/{vars,vault}.yml`
  through `vars_files` instead of adding `lab-pve-01` to `services` in the shared lab inventory,
  so the tier-2 harness never has to decrypt the services vault. The name avoids the `lab_*.yml`
  prefix: `test_confidence_gate_paths.py` treats every `ansible/playbooks/lab_*.yml` as a
  nested-harness playbook whose roles must trigger the confidence suite. It skips `lxc_base` (dist-upgrade,
  sshd drop-in, Alloy) and `service_backup` (already off for LAB). The role's own guards apply
  unchanged: `hermes_agent_operational` is false (`lab_inventory`), the LAB-rig branch renders the
  scratch pair, and the rendered-file assert checks it.
- **Held rig vs `proxmox-apply` [repo]**: `pve-lab run` starts with CLEANUP-PRE-001, which
  destroys any existing lab VM, so a harness run would kill a rig mid-gate. A shared concurrency
  group only orders running jobs; it does not protect a rig that sits idle between jobs. Decision
  (owner, 2026-10-25): `proxmox-apply.yml` gets a step before the harness that fails while
  `pve-lab status` reports a lab VM. Outside a running harness, any lab VM is a kept one. Both
  workflows also share the concurrency group `pve-lab`.
- **Teardown barrier [owner decision, 2026-10-25]**: `action=down` requires the input
  `confirm=destroy-lab-rig`, checked in the first step (constitution, CI/CD expectations:
  destructive automation needs a barrier). No environment approval: it only removes a throwaway VM.
- **Reachability [unverified, checked by `action=up`]**: the agent calls the LLM router directly
  at `http://{{ llm_router_ip }}:{{ llm_router_port }}` (192.168.1.220, a LAN address) and ntfy at
  `https://ntfy.{{ caddy_base_domain }}`. The old harness reached `deb.debian.org`, so internet
  egress works; LAN egress from 10.99.x and the router's client acceptance are unknown (`ci` cannot
  read pve's iptables). `action=up` probes both from the rig. Decision (owner, 2026-10-25): if
  either fails, stop and raise it; the fix (pve NAT/forwarding or router allowlist) is out of
  this branch until agreed.
- **Laptop path (constitution V)**: the same commands, run by hand after `ssh ci@pve`
  (quickstart § 0). A laptop cannot route to the rig, which principle V allows when documented.
- **A second, independent reason the laptop path is required pre-merge [found 2026-10-25]**:
  `gh workflow run lab-rig.yml --ref 095-ntfy-two-way -f action=up` returned `HTTP 404: workflow
  lab-rig.yml not found on the default branch`. This is a GitHub platform restriction, not a
  `gh`/CI bug: `workflow_dispatch` can only be triggered via the API/CLI once the workflow file
  exists on the repository's default branch — `--ref` selects which version of an *already
  known* workflow runs, it does not register a brand-new one. `lab-rig.yml` has never been on
  `main`. Not worked around by merging early (that would land unfinished 095 work just to
  unblock a dispatch button); the laptop path above already sidesteps the Actions API entirely,
  so it resolves this too, for a second reason beyond the original routing one. Does not affect
  `proxmox-apply.yml` or `lxc-promote-prod.yml` — both already existed on `main` before 095
  edited them.
- **The laptop path's own SSH key step was missing, and silently broke a kept rig [found
  2026-10-25]**: `scripts/lab/lib/rebuild.sh:14` only reuses `PROVISION_SSH_KEY` when that path
  **already exists** (`-f` test); the workflow's `up` case creates it first
  (`if [[ ! -f "${PROVISION_SSH_KEY}" ]]; then ssh-keygen ...; fi`) before ever calling
  `pve-lab run`, but quickstart's laptop-path commands did not include that step — they only
  `export`ed the variable. With the file absent, `rebuild.sh` falls through to its own ephemeral
  key (`lib/rebuild.sh:26-33`), uses it to provision the VM, then deletes it on exit regardless
  of `--keep` (`:38-44`) — `--keep` preserves the VM, not the provisioning key. Net effect: a
  rig that nothing can SSH into, discovered only on the next step (`ansible.builtin.uri` via
  `-i inventories/lab/hosts.yml` failed `Permission denied (publickey)`, `no such identity`).
  Recovery is a second `pve-lab run --keep` after creating the key — `CLEANUP-PRE-001` at the
  start of every `pve-lab run` destroys the previous (now-unreachable) rig automatically, so
  this is one command, not a manual teardown. Fixed in quickstart.md: the laptop path now
  creates the key inline with the same `ssh-keygen` invocation the workflow uses, so it is
  copy-paste safe standalone.

- **`pve-lab down` outside a run writes its nested-teardown evidence under `/` [found
  2026-10-26, T069]**: `mkdir: cannot create directory '/reports': Permission denied` and
  `rebuild.sh: line 381: /reports/cleanup/teardown-vm-100.txt: No such file or directory`. With no
  run active the evidence directory is empty, so the path resolves to `/reports/...`. It's harmless
  (the VM was destroyed and `status` was clean), but noisy and it loses teardown evidence. The
  fix belongs in `scripts/lab/` (protected path), outside 095; raise it as a follow-up.

## R-016: What the LAB rig actually asserts, and its credential policy for the T008 gate

Reviewed 2026-10-25 after T062–T066 landed, before any rig is brought up.

- **What is asserted [repo]**:
  - *CI*: `test_lab_rig_workflow.py` (workflow and playbook shape, teardown barrier, vault stays
    on `pve`, `proxmox-apply` held-rig guard) and `test_ntfy_acl.py` (`hermes_lab` has no grant
    on a production topic). Neither renders the `hermes` role.
  - *`action=up`*: ntfy and LLM-router reachability from the rig. No credential involved.
  - *`action=deploy`, role preflight*: pinned images, no NFS, aliases exist, each secret
    **defined and non-empty**, no `api.openai.com`, signup off.
  - *`action=deploy`, role main*: the rendered `agent.env` holds only the scratch pair and not
    the PROD ntfy token (`tasks/main.yml:122-135`); no `*_ALLOW_ALL_USERS`; compose confinement;
    health; egress probe; no heartbeat job.
  - *T008*: upstream agent behaviour over the scratch topics. It does not test infrastructure.
- **What is not asserted [repo]**:
  - ntfy is the **only** credential the rig holds a LAB-specific value for. The rig renders the
    production values of: `llm_router_client_hermes_key`, `llm_router_client_hermes_agent_key`,
    `llm_router_client_scout_probe_key` (passthrough, backlog 088), `hermes_agent_api_server_key`,
    `hermes_webui_secret_key`, `hermes_admin_password_bootstrap`, `hermes_searxng_secret`. No
    assert distinguishes them from PROD; the LLM router cannot tell rig traffic from PROD.
  - The role's env guards read the file back **after** it is written on the target. They detect;
    they do not prevent. No test renders `agent.env.j2` offline in any of its three modes.
  - The egress probe's `hermes-own-node-exporter` entry uses `hermes_ip`, which is the PROD LXC.
    On the rig it still proves a LAN destination is refused, but not the one its name says.
  - Prod 1's confidence suite (`pve-lab confidence` → `cmd_run` → CLEANUP-PRE-001) destroys any
    lab VM. Its job is in concurrency group `lxc-promote-prod-lab-<service>` and has no held-rig
    check, so it can kill a rig mid-gate.
- **Decision (pragmatic, 2026-10-25) — proceed with the gate, with three conditions**:
  1. **Accept production identities on the rig for the T008 gate only.** Compensating
     controls: the rig is reachable only from `pve`; it runs only for the gate (T069 the same
     day, see 3); the router keys are already budget- and rpm-capped per client (`064`, `071`);
     the agent's egress allowlist applies on the rig as on PROD. Rotating none of them after the
     gate is acceptable because none leaves `pve`/the rig.
  2. **Freeze the rig's credential set (T070).** An offline render test pins the exact set of
     secret-bearing variables each mode renders. Adding a key to the rig fails CI and forces an
     explicit decision here, instead of arriving silently. No rig-specific keys beyond the ntfy
     scratch pair are added in 095.
  3. **Close the confidence-suite hole (T071)** with the same guard `proxmox-apply` has, and
     bound the rig's lifetime by procedure (T069): down the same day, also if T008 stalls or
     fails; re-`up` is cheap.
- **Deferred (out of 095, follow-up backlog item)**: a rig credential *allowlist* policy with
  rig-specific router keys (needs an `llm_router` PROD deploy to mint them), a rig-correct
  `hermes-own-node-exporter` probe, and an expiry or alert for a forgotten rig. Revisit before
  the rig is used by a second feature (plan, Constitution IV watch item 2).
- **Addendum 2026-10-30: the Home Assistant MCP token is PROD-only.** `hermes_mcp_servers`
  gained its first `auth: bearer` entry, `homeassistant` (HA's MCP Server at
  `/api/mcp/assist`, token of the non-admin, local-only HA user `hermes`, vault
  `hermes_mcp_homeassistant_key`, env `AUXILIARY_MCP_HOMEASSISTANT_API_KEY` so child processes
  never inherit it; 083 R-004). Unlike the router keys accepted in condition 1, this
  credential switches things in the house, and the rig can reach `192.168.1.212` through the
  egress allowlist like PROD does. Decision: the entry is `enabled: "{{ hermes_agent_operational
  | bool }}"`, so the LAB rig and the pipeline LAB stage render neither the token (agent.env,
  Open WebUI's tool-server key) nor its egress rule. The credential freeze (T070) pins the key
  in `PROD_SECRETS` only, and `test_homeassistant_mcp_is_gated_on_prod_in_group_vars` pins the
  gate in `vars.yml`. Cost: Home Assistant tools disappear from the PROD agent between the
  pipeline's LAB apply and its PROD apply (both deploy the same LXC, backlog 067).
- **Addendum 2026-10-31: the memory MCP key is in every mode (097 R-009).** The `memory` entry
  renders `AUXILIARY_MCP_MEMORY_API_KEY` from `memory_client_hermes_key` in PROD, the LAB rig and
  the pipeline LAB stage, and the freeze pins it in all three sets. It adds no new exposure: the
  memory plugin already holds the same key in `hindsight-config.json` in every mode, the key is
  classified `internal`, its scope cannot export or wipe the bank, and lab copies reach no
  memory service (097 R-016: the lab nftables rule and the agent's chain reject it).

## R-017: `ntfy-acl-check.sh` crosses ntfy's default rate limit (found running T067 on PROD)

Found 2026-10-25 running T067's PROD verification: 61/120 PASS, with every request from #61
onward returning `429` regardless of credential or topic, immediately after 60 consecutive
correct auth decisions.

- **Finding**: ntfy's `visitor-request-limit-burst` defaults to 60 requests per visitor,
  replenished one per `visitor-request-limit-replenish` (default `5s`) — confirmed against
  `binwiederhier/ntfy:v2.28.0 serve --help`. Neither is overridden in
  `ansible/roles/ntfy/templates/server.yml.j2`, so the server default applies. `behind-proxy:
  true` makes the limit see the real client IP (not Caddy's), so it is scoped to whichever
  single host runs the check, not shared with the phone or other services.
- **Why now**: the matrix has grown every spec that touched it and stayed under 60 every time
  (20 cells at `082`, 35 at `089`, 54 at `090`, per their own quickstart records). `095`'s
  `hermes_lab` row is the first to push it over — to 120 cells, double the burst.
- **Decision**: fix the script, not the server. The request volume is the diagnostic tool's
  own, not real traffic; loosening a public-facing service's abuse protection for that reason
  would be the wrong trade. `ntfy-acl-check.sh` now retries on `429` with a bounded count,
  honoring `Retry-After` when ntfy sends one and falling back to the documented 5s default
  otherwise (commit `844d372`). Verified against a throwaway token-bucket test server before
  touching PROD. A full run now takes several minutes past the burst, not a single pass.
- **Forward note**: P2 (T044/T045) adds more rows (`actions`, `relay`, `action_relay`), growing
  the matrix further. The retry fix scales with it; no further action needed unless ntfy's
  defaults change.

## R-018: Long replies over ntfy: a read-only adapter shim until upstream chunks

Decision 2026-10-26 (owner), after T008 step 7 failed (R-014: the bundled ntfy adapter slices chat
replies to 4096 characters with only a WARNING).

- **Decision**: fix it now with a thin, read-only user-plugin override, and send the same change
  upstream (T076). Waiting for a release (block slice 1) and documenting a silent cut (weaken US1
  AS-4) were rejected.
- **Mechanism [v0.21.6 source]**: `hermes_cli/plugins_discovery.py:221` `resolve_manifest_winners`:
  "a same-named copy under `~/.hermes/plugins/<name>` is the documented way to override a bundled
  plugin". The key is `platforms/ntfy`; the directory must be named `ntfy` or it's skipped as an
  impostor. User platform plugins load only when listed in `plugins.enabled`
  (`gate_manifest`), which lives in the deploy-owned, read-only `config.yaml`.
- **Shape**: subclass, not fork. The shim imports the bundled `plugins.platforms.ntfy.adapter`
  (import verified in the running container), sets `splits_long_messages = True`, and its
  `send()` sends each chunk of `BasePlatformAdapter.truncate_message(content,
  MAX_MESSAGE_LENGTH)` through the parent's `send()`. Auth headers, markdown, the HTTP call and
  error handling stay upstream's code. Verified in the container: the 4892-char failing reply
  splits into 2 chunks (4083 + 820 chars) ending `(1/2)` / `(2/2)`, with nothing lost. `register()`
  reuses the bundled one and replaces only `adapter_factory`.
- **Posture**: same as the hooks (plan, Complexity Tracking): static files owned by root, bind-mounted
  `:ro` at `/opt/data/plugins/platforms/ntfy`, so the agent (which can write `/opt/data`) can't
  modify gateway-executed code or turn the override off. This is code we carry, so it's tested
  (T073) and has a removal trigger (T076).
- **Cron delivery is unaffected**: `gateway/delivery.py` already caps cron output at 4000
  characters with a visible "[truncated, full output saved to ...]" footer, below the
  adapter's limit.
- **Ordering in the app**: chunks are published in order. ntfy lists newest first, so `(2/2)`
  appears above `(1/2)`; the indicators make the order clear.
