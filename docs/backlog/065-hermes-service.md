# Feature Specification: Hermes service + Claude plan door

**Feature Branch**: `065-hermes-service`
**Created**: 2026-08-29
**Status**: Backlog — **blocked on [`064-llm-router`](./064-llm-router.md)** (Hermes addresses the
gateway by intent alias; without it Hermes would hold provider credentials directly).
**Input**: Run **Hermes** as a gated LXC with persistent state, consuming the `064` gateway by intent
alias for light/medium work. Add a second, always-on **plan-door LXC** running the unmodified Claude
Code CLI, authenticated once by the account owner through Anthropic's own flow, which Hermes triggers
headlessly for heavy autonomous work. Make Hermes **quota-aware**: model the 5-hour rolling window and
the weekly per-model allowance from locally-measurable data, back off as the window fills, and
schedule deferred work into windows that would otherwise expire unused.

## Summary

Hermes gets the same treatment as every other service here: an unprivileged `lxc_service` LXC running
containers via `docker_compose_v2`, state on the LXC's local disk, a dedicated backup role pushing to
the Synology, and a monitoring contract. The two things that are *not* boilerplate are the persistence
split and the plan door.

**Persistence.** "Data on the NAS like the other containers" needs a split that this repo already
makes: Nextcloud keeps MariaDB on local disk and only user files on NFS, and `financial-scenario`
bind-mounts `scenarios.db` from local disk *specifically so `financial_scenario_backup` can reach it*.
Hermes' state is almost certainly a SQLite database and/or a vector index — both of which invite
locking failures and corruption over NFS. So: **state on local disk, backed up to the NAS; bulk
artifacts on NFS**.

**The plan door.** The Claude subscription cannot be a router backend — not as a preference, but
because Anthropic's terms say OAuth is "intended exclusively… to support ordinary use of Claude Code
and other native Anthropic applications" and that developers "may not collect, store, or intermediate
Claude.ai credentials or session tokens", with enforcement reserved "without prior notice". What *is*
inside the envelope is the account owner running the **unmodified** client, logged in through
Anthropic's own flow, doing their own work — the same page brackets plan limits as assuming "ordinary,
individual usage of Claude Code and the Agent SDK". So the plan door is **a process Hermes launches,
never an endpoint Hermes calls with a credential it holds**.

**Why quota-awareness is worth building.** The 5-hour window is *rolling* (it starts on your first
request, not on a clock boundary) and it **refills without banking** — unused capacity is gone at
reset. So the optimisation is not primarily throttling near the cap; it is filling windows that would
otherwise expire empty, which is mostly overnight. That is precisely what an always-on plan-door LXC
buys over running it on the Mac, and it is why the always-on box was chosen.

## User Scenarios & Testing

### User Story 1 - Hermes survives an LXC rebuild with its state intact (P1)

**Acceptance**:
1. **Given** Hermes has accumulated state, **When** the LXC is rebuilt from code, **Then** the
   restore procedure returns Hermes to its prior state from the NAS backup.
2. **Given** the backup role, **When** it runs on schedule, **Then** a restorable artifact lands on
   the Synology and its age is monitored.
3. **Given** the state store, **When** its location is inspected, **Then** it is on the LXC's local
   disk and bind-mounted so the backup role can reach it — **not** on an NFS mount.

### User Story 2 - Light work goes local, heavy work goes to the right door (P1)

**Acceptance**:
1. **Given** the `064` gateway, **When** Hermes performs a classify/extract/summarise task, **Then**
   it requests `hermes-fast` and never names a provider model.
2. **Given** a task with a hard correctness bar, **When** Hermes dispatches it, **Then** it uses
   `hermes-deep` (metered API) or the plan door according to policy — not the light tier.
3. **Given** the gateway is unreachable, **When** Hermes dispatches, **Then** it degrades visibly
   (queued or reported) rather than silently producing low-quality output from a fallback tier.

### User Story 3 - Hermes is quota-aware and fills empty windows (P1)

**Acceptance**:
1. **Given** the current 5-hour window is lightly used, **When** batchable work is pending, **Then**
   Hermes runs it through the plan door rather than deferring it.
2. **Given** the window is heavily used by interactive work, **When** Hermes has non-urgent work,
   **Then** it defers that work and records the next reset time.
3. **Given** the weekly allowance is near its threshold, **When** Hermes dispatches, **Then** it
   drops to the metered/local tiers and raises a Pushover alert.
4. **Given** any plan-door invocation, **When** it completes, **Then** Hermes has recorded that
   invocation's exact cost and token usage.

### User Story 4 - Only the account owner reaches the plan door (P1)

**Acceptance**:
1. **Given** any surface Hermes exposes, **When** a request originates from anyone other than the
   account owner, **Then** it MUST NOT reach the plan door — it is served by the router tiers or
   refused.
2. **Given** the plan-door LXC, **When** its credentials are inspected, **Then** the Claude session
   exists only there, established interactively by the owner, and is not copied, exported, or read by
   Hermes.

### Edge Cases

- **State store on NFS** — SQLite/vector indexes over NFS risk locking failures and corruption. The
  split in FR-002/FR-004 is a hard requirement, not a preference.
- **Rebuild silently drops the plan-door login** — this is the same class of gap as
  `ansible/playbooks/fail2ban.yml`: a manual, out-of-pipeline step that a rebuild quietly loses, and
  the failure is silent until something goes unrun. The plan-door session MUST be liveness-monitored
  and its re-establishment MUST be a documented runbook step in the rebuild path.
- **Session expiry / token refresh** on the plan-door LXC → same failure mode; same monitor.
- **A job spans a window boundary** — a long run can start with headroom and hit the cap mid-flight.
  Jobs MUST be restartable/resumable, or sized to fit a window.
- **Weekly cap hit mid-week** — far more disruptive than a session cap, and it is counted in
  **model-hours per model**, so Opus hours are the scarce resource. Default the plan door to
  Sonnet-class; Opus is opt-in per job.
- **Double counting** — Hermes' own burn (measured exactly) and the owner's interactive burn (read
  from local session logs) can overlap if both are summed naively from the same source.
- **Budget model drifts from reality** — no API reports remaining quota, so the model is an estimate.
  It MUST be calibratable against what `/usage` displays, and MUST fail safe (assume less headroom
  than modelled) when uncertain.
- **A second household member appears** — if Hermes ever gains a multi-user surface, FR-007 becomes
  the thing that keeps the deployment inside Anthropic's terms. Design for it now, not later.
- **Runaway agent loop** — bounded by the `064` per-client budget for metered traffic, but the plan
  door needs its own concurrency/rate cap.
- **Transcript retention** — Hermes' prompts and outputs may contain personal data; retention and
  location must be a decision, not a default.

## Requirements

- **FR-001**: Run Hermes on a dedicated unprivileged `lxc_service` LXC (nesting) via
  `docker_compose_v2`, image/version pinned in `ansible/group_vars/services/vars.yml`.
- **FR-002**: Hermes' **state** (database, vector index, queue, config) lives on the LXC's local disk
  and is bind-mounted into the container so a backup role can reach it. It MUST NOT live on an NFS
  mount. (Precedent: `financial_scenario`, `nextcloud`.)
- **FR-003**: A `hermes_backup` role backs that state up to the Synology over `nfs_mount`, on a
  schedule, alongside the existing `*_backup` roles. Backup age MUST be monitored.
- **FR-004**: If Hermes produces **bulk artifacts** (documents, transcripts, exports) they MAY live on
  an in-guest NFS mount (`features_mount = "nfs"` + the rw `nfs_mount` role). The read-only
  `shared_nfs_mount` role is NOT suitable (it asserts `SD-003` RO).
- **FR-005**: Hermes addresses the `064` gateway by **intent alias only** (`hermes-fast`,
  `hermes-balanced`, `hermes-deep`) and holds no provider credentials of its own.
- **FR-006**: The **plan door** is a separate, always-on LXC running the **unmodified** Claude Code
  CLI, authenticated **once, interactively, by the account owner**, through Anthropic's own sign-in
  flow. Hermes triggers runs there; Hermes MUST NOT collect, store, proxy, or transmit the session
  credential, and no gateway may sit in front of it.
- **FR-007**: Plan-door access is restricted to the account owner. Any non-owner request reaching
  Hermes MUST NOT be able to cause a plan-door invocation.
- **FR-008**: Every plan-door invocation MUST use `--output-format json` and record `total_cost_usd`
  and the returned `usage` block, giving Hermes an exact account of its own consumption.
- **FR-009**: Hermes MUST maintain a budget model over (a) the **5-hour rolling** session window and
  (b) the **weekly per-model** allowance, combining its own measured burn with the owner's interactive
  burn, and MUST consult it before choosing the plan door. Thresholds MUST be configurable.
- **FR-010**: Non-urgent plan-door work MUST be queueable and drained into low-utilisation windows,
  so capacity that would expire unused is spent.
- **FR-011**: The plan door defaults to a Sonnet-class model; Opus-class is opt-in per job, because
  the weekly allowance is counted per model.
- **FR-012**: Claude Code telemetry (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, OTLP → collector → Prometheus)
  MUST feed the existing monitoring stack, with a Grafana panel for both windows and a Pushover alert
  on the weekly threshold.
- **FR-013**: The plan-door LXC's authenticated state MUST be liveness-monitored (an unauthenticated
  or expired session is a distinct, alerting condition) and re-authentication MUST be a documented
  runbook step included in the rebuild path.
- **FR-014**: Both LXCs deploy through the gated LAB→PROD pipeline with the full registration set:
  allowlist entries in `scripts/lab/service-scope-allowlist.json` (protected path → PR needs the
  `allow-protected-path-changes` label), `scripts/healthcheck/<svc>.sh` per service, and both names
  in the `service` dropdown of `lxc-deploy-lab.yml`, `lxc-promote-lab.yml`, `lxc-promote-prod.yml`.
- **FR-015**: Transcript/prompt retention MUST be an explicit, bounded setting with a documented
  location; personal content MUST NOT be written to a world-readable path or to the landing page.

## Success Criteria

- **SC-001**: Rebuilding the Hermes LXC and restoring from the NAS backup returns it to its prior
  state; verified as a drill, not assumed.
- **SC-002**: Hermes' state store is on local disk; no state DB path resolves onto an NFS mount.
- **SC-003**: A light task is served by the local tier through the gateway at zero marginal cost, and
  Hermes' code contains no provider model ID.
- **SC-004**: A plan-door invocation returns JSON from which Hermes records exact cost and tokens.
- **SC-005**: With the 5-hour window lightly used, pending batch work is executed rather than
  deferred; with it heavily used, the same work is deferred with a recorded reset time.
- **SC-006**: Crossing the weekly threshold drops Hermes to the metered/local tiers and fires a
  Pushover alert.
- **SC-007**: The budget model, run for one week alongside `/usage`, tracks the displayed
  percentages closely enough to drive the thresholds, and errs toward under-estimating headroom.
- **SC-008**: A non-owner request cannot cause a plan-door invocation.
- **SC-009**: An expired/logged-out plan-door session raises an alert rather than failing silently.
- **SC-010**: Both services deploy idempotently through the pipeline with green healthchecks.

## Research & decisions

**D-001 (OPEN — the big one): what Hermes actually is.** This spec deliberately fixes everything that
holds regardless of the application choice — LXC shape, persistence split, backup, how it consumes the
gateway, the plan door, the quota model, owner-only access. The application surface itself (bought,
built, or assembled; what interface it exposes; whether it has a UI at all) is undecided and must be
settled before the spec-kit `/plan` stage, because it determines the healthcheck endpoint, the state
schema, and whether FR-007's multi-user concern is live or theoretical.

**D-002 (DECIDED): the plan door runs in a dedicated always-on LXC, not on the Mac.** The Mac option
is unambiguously ordinary personal use and needs no new infrastructure — but plan-door jobs would
inherit the Mac's sleep behaviour, which defeats the entire point, since the windows worth filling are
the overnight ones. The trade accepted: a headless box holding a long-lived authenticated session,
which is why FR-013 (monitor it) and FR-007 (owner-only) exist.

**Terms analysis.** Anthropic's Claude Code legal page permits running Claude Code inside other
infrastructure under stated conditions, and this deployment is built to meet them explicitly:
the binary is **unmodified** and no built-in authentication method is removed or restricted (FR-006);
usage is **not paid for, resold, or intermediated on anyone else's behalf** — the sole user is the
account owner authenticating with their own subscription credentials (FR-006, FR-007); and **no
credential is collected, stored, or intermediated** by Hermes or any gateway (FR-006, and `064`'s
FR-007 which keeps subscription credentials out of the router entirely). The clause that rules out the
obvious shortcut: *"Anthropic does not permit third-party developers to offer Claude.ai login into
their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of
their users."* The 2026 crop of OAuth-mux routers advertising "use your Pro plan instead of API
credits" sits on the wrong side of that line, and enforcement is reserved *"without prior notice"* —
the stake is the account, not a throttled request. If Hermes ever serves a second person, FR-007 is
what keeps the deployment compliant.

**What is measurable (and what is not).** There is **no API that reports remaining subscription
quota**. `/usage` prints the session window as a percentage and the weekly cap as hours-per-model with
reset times — authoritative, but a TUI rendering for a human: no JSON, no exit code. The statusline
JSON carries session `cost` and `context_window` but not plan headroom, and the request to expose the
`anthropic-ratelimit-*` headers to hooks/statuslines is still open. Claude Code's OpenTelemetry export
covers **consumption only** — `claude_code.token.usage`, `claude_code.cost.usage`,
`claude_code.session.count`, `claude_code.active_time.total` — with nothing for headroom. Hence FR-009:
model the burn, calibrate against `/usage`, fail safe.

Three feeds, all local, none touching a credential:
- **Hermes' own burn is exact** — `claude -p --output-format json` returns `total_cost_usd` and a
  `usage` block per invocation, and every plan-door request is one Hermes launched.
- **The owner's interactive burn** — `ccusage` parses the JSONL under `~/.claude/projects/` with no
  API key and no network call, and reports the active 5-hour block as it fills.
- **Both into Prometheus** — via an OTLP collector, into the stack already deployed.

**The window model.** 5 hours, **rolling from the first request**, not clock-aligned and not 4 hours;
capacity **refills without banking**. Suggested initial policy (FR-009 thresholds): under ~60% of the
session budget, plan door open for anything that qualifies; 60–85%, plan door only for work that
genuinely needs it; over 85%, router tiers only and queue plan-door work against the next reset.
Weekly is a separate axis in model-hours per model — hence FR-011.

**Sources**: Claude Code legal and compliance, authentication and credential use
(https://code.claude.com/docs/en/legal-and-compliance); monitoring/OTEL metric names
(https://code.claude.com/docs/en/monitoring-usage); headless JSON output
(https://code.claude.com/docs/en/headless); statusline fields
(https://code.claude.com/docs/en/statusline) and the open usage-exposure issues
(https://github.com/anthropics/claude-code/issues/33820,
https://github.com/anthropics/claude-code/issues/11535); `ccusage` (local JSONL parsing, 5-hour block
reporting); in-repo precedent for the persistence split (`ansible/roles/financial_scenario`,
`ansible/roles/nextcloud`, `ansible/roles/nfs_mount`, `ansible/roles/shared_nfs_mount`).

## Verification (acceptance)

1. **Deploy**: pipeline creates both LXCs; compose healthy; healthchecks green with evidence.
2. **Persistence drill**: write state, rebuild the Hermes LXC from code, restore from the NAS,
   confirm state intact. Confirm no state path resolves onto NFS.
3. **Tiering**: run one light and one heavy task; confirm from gateway metrics that they landed on
   the expected tiers and that Hermes named only aliases.
4. **Plan door**: trigger a job; confirm it runs on the plan-door LXC under the owner's session, and
   that Hermes recorded exact cost and tokens from the JSON result.
5. **Quota policy**: simulate a lightly-used window (batch work runs) and a heavily-used one (same
   work defers with a reset time). Cross a weekly threshold in the model → tier drop + Pushover.
6. **Calibration**: run the model for one week; compare against `/usage`; confirm it under-estimates
   rather than over-estimates headroom.
7. **Access**: attempt a plan-door-triggering request as a non-owner → refused or downgraded, never
   executed.
8. **Session-loss drill**: log the plan-door LXC out; confirm an alert fires rather than jobs failing
   silently, and that the runbook restores it.

## Dependencies

- **Blocked by**: [`064-llm-router`](./064-llm-router.md).
- **Assumes**: PVE headroom for two more small LXCs; a Claude Pro/Max subscription held by the
  account owner; the OTLP collector added alongside the existing monitoring stack; the `nfs_mount`
  (rw) role and the Synology export.
- **Related**: [`migrate-host-bind-mounts-to-in-guest-nfs`](./migrate-host-bind-mounts-to-in-guest-nfs.md)
  — this item uses the in-guest pattern from the start and adds no new host-bind seam.
- **Out of scope**: the gateway itself (`064`); any use of subscription credentials outside the
  unmodified client on the plan-door LXC; a public (non-tailnet) surface for Hermes; semantic /
  difficulty-based routing.
