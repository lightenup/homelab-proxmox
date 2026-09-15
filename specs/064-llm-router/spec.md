# Feature Specification: LLM Router (gateway LXC)

**Feature Branch**: `064-llm-router`
**Created**: 2026-08-29
**Status**: Draft
**Input**: Deploy a self-hosted LLM gateway on its own gated LXC that exposes **one OpenAI-compatible endpoint** to homelab clients, addressed by **intent aliases** (`hermes-fast`, `hermes-balanced`, `hermes-deep`) rather than provider model IDs. Backends: a Mac on the tailnet running a local inference server (free, private, **intermittently available**), a hosted aggregator, and an Anthropic API key. Health-check-driven routing plus ordered fallbacks make the Mac's availability invisible to callers. LAN and tailnet reachable with no public route; observable in the existing Prometheus/Grafana stack. (Source backlog: `docs/backlog/064-llm-router.md`.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A client gets an answer regardless of the Mac's state (Priority: P1)

A homelab client asks the gateway for an intent alias and receives a completion whether the Mac is awake, asleep, or off the tailnet entirely. The Mac is a discount that is usually available, never a dependency.

**Why this priority**: This is the reason the router exists. The only local inference box is intermittent; if its absence surfaces to callers as errors or hangs, every client has to implement its own failover and the gateway has delivered nothing.

**Independent Test**: With the Mac serving, request `hermes-fast` and confirm from metrics that the local deployment served it. Power the Mac off (or stop its inference server), repeat the identical request, and confirm a valid completion still returns with no client-visible error. Bring the Mac back and confirm it re-enters the pool without operator action.

**Acceptance Scenarios**:

1. **Given** the Mac is serving, **When** a client requests `hermes-fast`, **Then** the request is served by the local deployment at zero marginal cost, and the serving deployment is identifiable from metrics.
2. **Given** the Mac is powered off, **When** the same request is made, **Then** it is served by the standby deployment with no client-visible error and no unbounded retry.
3. **Given** the Mac has failed its background health check, **When** the next request arrives, **Then** it is routed to the standby *without* first attempting and timing out on the dead deployment.
4. **Given** the Mac comes back, **When** its health check next passes, **Then** it re-enters the pool automatically with no operator action.
5. **Given** every deployment behind an alias is in cooldown, **When** a request arrives, **Then** it fails fast with a clear error rather than hanging or retrying indefinitely.

---

### User Story 2 - Deploy comes up healthy through the gated pipeline (Priority: P1)

An operator runs the gated LAB→PROD pipeline; the LXC is provisioned, the gateway container starts, becomes healthy, and re-runs are idempotent with the version staying pinned.

**Why this priority**: A repeatable, healthy, idempotent deploy is the foundation every other story stands on, and it is the mechanism by which the alias remapping in Story 3 is delivered.

**Independent Test**: Run the pipeline against the pinned image tag; confirm the container reaches `Up (healthy)` and the readiness endpoint returns 200. Re-run the apply and confirm no unintended recreation and an unchanged pin. Confirm the post-apply healthcheck passes and writes evidence.

**Acceptance Scenarios**:

1. **Given** the pinned image tag, **When** the apply runs, **Then** the container is `Up (healthy)` and the gateway's readiness endpoint returns 200.
2. **Given** a completed deploy, **When** the apply repeats, **Then** it is idempotent (no unintended recreation) and the version stays pinned.
3. **Given** the post-apply healthcheck, **When** the pipeline runs it, **Then** it passes and writes evidence.
4. **Given** the pipeline's registration set, **When** a change touches the service's protected paths, **Then** the deploy is gated exactly as other services are.

---

### User Story 3 - Retiering is a config edit, not a code change (Priority: P1)

The Mac's memory grows from 32 GB to 128 GB and `hermes-balanced` should move from a hosted model to a large local one. The operator changes one mapping in configuration data and deploys; no client is touched.

**Why this priority**: The hardware upgrade is imminent and known. Without the alias indirection this becomes a change to every client, which is precisely the cost the router was built to avoid — so the indirection must be proven, not assumed.

**Independent Test**: Change one alias→deployment mapping in the declarative configuration data, deploy, and confirm subsequent requests to that alias are served by the new deployment. Inspect every client and confirm none changed.

**Acceptance Scenarios**:

1. **Given** the new model is available on the Mac, **When** the alias mapping is changed in configuration data and the service is deployed, **Then** subsequent `hermes-balanced` requests are served locally.
2. **Given** that change, **When** clients are inspected, **Then** **no client configuration or code changed** — clients still address the same alias.
3. **Given** the remap, **When** the role runs, **Then** no role logic was edited to accommodate it.

---

### User Story 4 - Routing and spend are observable (Priority: P2)

An operator opens Grafana and can see which alias is being used how often, which deployment is serving or failing, whether the local tier is up, and what the metered tier is costing.

**Why this priority**: Necessary for operating the router and for catching a silently-degraded local tier before it shows up as a bill — but the router delivers its core value (Stories 1–3) before the dashboards exist.

**Independent Test**: With traffic flowing across all three aliases, confirm Grafana shows per-alias request volume and per-deployment success/failure. Stop the Mac's inference server and confirm a distinct "local tier down" signal appears rather than an inference drawn later from spend.

**Acceptance Scenarios**:

1. **Given** the monitoring contract, **When** Prometheus scrapes, **Then** per-alias request counts and per-deployment success/failure are visible in Grafana.
2. **Given** the Mac is unreachable, **When** the backend probe runs, **Then** "local tier down" is an explicit signal rather than something inferred later from a metered bill.
3. **Given** metered usage, **When** spend accrues, **Then** it is attributable per alias.
4. **Given** the gateway process is alive but its backends are all failing, **When** monitoring is inspected, **Then** this is distinguishable from a healthy gateway — liveness alone MUST NOT read as green.

---

### User Story 5 - A runaway client cannot bill unbounded (Priority: P2)

An agent stuck in a retry loop against a metered alias is cut off by a per-client limit instead of accruing an unbounded bill.

**Why this priority**: The failure is financial rather than functional, and it is realistic — the router's first consumer is an agent. It ranks below core routing because it protects against a scenario rather than enabling one, but it is required, not optional.

**Independent Test**: Deliberately drive a client past its configured limit and confirm the request is refused with a clear error and that the event is visible in monitoring.

**Acceptance Scenarios**:

1. **Given** a per-client limit, **When** one client exceeds it, **Then** that client's further requests are refused with a clear error while every other client continues to be served normally.
2. **Given** that refusal, **When** monitoring is inspected, **Then** the breach is visible and attributed to the specific client.
3. **Given** the gateway-wide cap, **When** it is exhausted, **Then** requests are refused with an error distinguishable from a per-client breach, and a distinct alert fires.

---

### Edge Cases

- **Gateway liveness green while every backend is broken** — the documented trap: the process is alive, every request fails. Readiness *and* backend outcomes MUST both be monitored, not liveness alone. A traffic-derived signal alone is insufficient: with no clients calling, a fully broken gateway stays silent until someone tries it, which is how this trap is usually discovered (FR-018).
- **Mac awake but the model is not loaded** — a local server that just-in-time loads on first request can take tens of seconds on a cold call, tripping a naive timeout into a false fallback. Timeouts MUST account for cold load, or a keep-loaded policy MUST be set on the Mac.
- **Input too long for the small model** — MUST escalate a tier rather than returning a context-length error to the caller.
- **All deployments behind an alias in cooldown** — MUST fail fast with a clear error; MUST NOT hang or retry forever.
- **Health checks cost money** — probing metered deployments on a short interval bills real tokens. Probe cadence and mode MUST be chosen so background checks are not a line item.
- **The router holds every provider credential owned** — it is the highest-value credential target in the homelab. Vault-sourced, no public route, per-client keys, and spend capped at two levels.
- **Runaway client loop** — an agent retrying against a metered alias can bill unbounded; a per-client budget/limit is required.
- **Gateway-wide cap exhausted** — the backstop cap refuses *every* client at once, so it is an availability event as much as a spend one. It MUST alert distinctly from a per-client breach, and MUST NOT be the first thing an operator learns from a failing client.
- **Backing services down or unmigrated** — the gateway's virtual keys and budgets depend on its database and cache. A failed schema migration or a database that is up-but-empty can present as an authentication failure for every client. Backing-service health MUST be part of the deploy's readiness assertion, not assumed from the gateway container alone.
- **Floating image tag drift** — MUST pin, and record the pin centrally.
- **Unauthenticated backend on the LAN** — binding a local inference server to all interfaces exposes it without authentication. The backend MUST be reached over the tailnet, not exposed on the LAN.
- **Gateway routing-pool defects** — pool-selection bugs ("no deployments available" against apparently healthy deployments) have been reported against a leading candidate. Whichever gateway is chosen, the deploy MUST pin a version that has been exercised against a deliberately-downed backend before promotion.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The gateway MUST run from a pinned image tag (never a floating tag) on a dedicated, unprivileged LXC service host with nesting enabled, sized **2 vCPU / 4 GB RAM / 16 GB disk** — it proxies rather than infers, but it also hosts the stateful backing service FR-010 and FR-014 depend on. Every image tag in the stack MUST be pinned, and the pins MUST be recorded in the repository's central version-pin location.
- **FR-002**: The gateway MUST expose exactly **one** OpenAI-compatible endpoint. Clients MUST address **intent aliases**; a client MUST NOT need to know a provider model ID.
- **FR-003**: The alias→deployment mapping MUST be declarative configuration data, templated into the gateway config by the role. Changing the model behind an alias MUST NOT require editing role logic or any client.
- **FR-004**: Every alias with a remote equivalent MUST declare **ordered deployments** so that primary failure falls back automatically: `hermes-fast` falls back to `hermes-balanced`; `hermes-balanced` falls back to the metered tier.
- **FR-005**: Background health checks MUST be enabled with an interval of 60 s or less, so a failed deployment leaves the pool *before* a request lands on it. Probe cadence and mode MUST NOT generate material metered spend.
- **FR-006**: Inputs exceeding a deployment's context window MUST escalate to a larger tier rather than returning an error to the caller.
- **FR-007**: All provider credentials MUST come from the Ansible vault; none in git. The router MUST NOT hold Anthropic **subscription/OAuth** credentials of any kind — the Anthropic backend is an **API key billed to the account owner**.
- **FR-008**: The gateway MUST have **no public reachability**: no public reverse-proxy route, no public DNS name, no landing-page entry. It is reachable from the LAN and the tailnet. Any later landing-page entry MUST be non-user-facing or gated. *(Narrowed from "tailnet-only" — see Decisions § Exposure scope for what was traded and why.)*
- **FR-009**: The service MUST publish a monitoring contract covering (a) gateway liveness *including its backing service*, (b) a scrape of the gateway's metrics endpoint, (c) a **local-tier availability signal** so the Mac's state is first-class — the requirement is the signal, not any particular probe mechanism, and as of 2026-09-14 the probe target is oMLX's `/health` on the LAN rather than Ollama over the tailnet — and (d) an **all-backends-failing signal** that fires whether or not client traffic is flowing (see FR-018). The gateway being down MUST alert; the Mac being down MUST be informational, not critical. Exhaustion of the gateway-wide spend cap (FR-010) MUST raise its own distinct alert, since it refuses every client at once.
- **FR-010**: The gateway MUST enforce spend and rate limits at **two levels**: a per-client limit bound to each client's own credential, and a **gateway-wide cap** across all clients as a backstop. Requests past either limit MUST be refused with a clear error that distinguishes which limit was hit. Breaching the per-client limit MUST NOT affect other clients.
- **FR-011**: The feature MUST deploy through the gated LAB→PROD pipeline with the full registration set: a service-scope allowlist entry (protected path — changes require the protected-path label on the PR), a post-apply healthcheck script, and the `service` dropdown entry in the lab-deploy, lab-promote and prod-promote workflows.
- **FR-012**: The service MUST NOT persist user data. Any request logging MUST stay on the LXC's local disk with bounded retention and no network storage mount. Prompt and response bodies MUST NOT be logged by default.
- **FR-013**: The Mac backend MUST be addressed over the **LAN** by its stable mDNS `.local` name, never a DHCP-assigned IP, and MUST NOT be reachable unauthenticated from the LAN nor reachable at all from outside it. *(Amended 2026-09-14 — was tailnet-addressed by MagicDNS name. Zscaler blocks Tailscale on the replacement Mac but not LAN traffic, and the Mac and PROD gateway share `192.168.1.0/24`. See [`amendment-local-tier-omlx.md`](./amendment-local-tier-omlx.md).)*
- **FR-014**: The gateway MUST be **LiteLLM**, deployed with a **PostgreSQL backing service** on the same LXC, so that virtual keys, per-client budgets (FR-010) and per-alias spend attribution (SC-005) are served natively rather than reconstructed. A **Redis service MUST be added only if the proxy runs more than one worker** — it exists to share router and rate-limit state *between* workers and has no consumer at one. The pinned LiteLLM version MUST be one that has passed the downed-backend drill (SC-008) before promotion, and the backing service MUST persist across container restart and upgrade.
- **FR-015**: Every client MUST authenticate with its **own key**, issued per consumer and sourced from the vault. That key MUST be the unit against which FR-010's per-client limits are enforced and against which usage and spend are attributed in metrics. A shared key across consumers MUST NOT be used.
- **FR-016**: The local tier MUST be served by **oMLX** on the Mac, exposing its OpenAI-compatible endpoint on the LAN, and MUST keep every aliased model **resident** so a model swap cannot trip the gateway's timeout into a false fallback. oMLX is the only local backend the gateway addresses and the only one covered by FR-009's local-tier signal; any other inference runtime on the Mac is unmanaged and out of scope. *(Amended 2026-09-14 — was Ollama, on a Mac now being returned. Residency is the same hazard Ollama's `OLLAMA_KEEP_ALIVE` addressed, reached by a different lever. See [`amendment-local-tier-omlx.md`](./amendment-local-tier-omlx.md).)*

- **FR-017**: The LXC MUST have its own egress path onto the tailnet, independent of the PVE host's subnet router. This path MUST NOT require privileged-container features or host device passthrough. *(Amended 2026-09-14 — the original justification was reaching the Mac by MagicDNS name, which FR-013 no longer requires. The sidecar is retained for the first deploy on a different justification: it is what makes FR-008's tailnet client reach independent of `pve`'s subnet router, which is currently logged out and would otherwise be a single point of failure for all tailnet access. **Revisit once the subnet router is logged back in and proven stable** — if it carries client reach reliably, the sidecar costs a container and a vault auth key for nothing.)*
- **FR-018**: An all-backends-failing condition MUST be detectable **independently of client traffic**. The service MUST emit both a failure-rate signal across all deployments and a low-cadence synthetic request whose failure raises an alert. The synthetic request is client traffic, not a health probe, and is therefore outside SC-011's probe budget.

### Key Entities *(include if feature involves data)*

- **Intent Alias**: The stable, client-facing name for a class of work (`hermes-fast`, `hermes-balanced`, `hermes-deep`). The only model identifier a client ever knows. Maps to an ordered list of deployments and survives every change to the models behind it.
- **Deployment**: One concrete backend a request can be served by — a model on a specific provider, with its endpoint and credential. Deployments are ordered within an alias (preferred, then standby) and carry health state and a cooldown.
- **Backend Tier**: The three sources of inference — the **local tier** (Mac on the tailnet, zero marginal cost, intermittently available), the **aggregator tier** (hosted, metered, always available), and the **frontier tier** (Anthropic API key, metered, for `hermes-deep`).
- **Alias Mapping**: The declarative configuration data binding aliases to ordered deployments, plus fallback, cooldown and health-check settings. The single artefact an operator edits to retier.
- **Client Identity**: The credential a homelab consumer presents, and the unit against which spend and rate limits are enforced and against which usage is attributed in metrics.
- **Monitoring Contract**: The service's declared liveness, metrics-scrape and backend-probe targets, and their alert severities.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With the Mac **powered off — not merely its server stopped** — every one of the three aliases still returns a valid completion; no client changes and no manual intervention are required. Both failure modes are exercised, because a stopped daemon refuses fast while a vanished tailnet peer can hang to timeout.
- **SC-002**: With the Mac serving, `hermes-fast` is demonstrably served locally — the serving deployment is visible in metrics — at zero marginal cost.
- **SC-003**: Remapping an alias to a different model is a single configuration-data edit plus a deploy, with zero client-side change.
- **SC-004**: The pipeline deploys idempotently; the container is `Up (healthy)`; the readiness endpoint returns 200; the post-apply healthcheck passes with evidence.
- **SC-005**: Grafana shows per-alias request volume, per-deployment failures and metered spend, and a downed Mac raises its own distinct signal separate from gateway health.
- **SC-006**: No credential appears in git, and the router holds no Anthropic subscription credential.
- **SC-007**: The gateway is unreachable from outside the LAN and tailnet, and has no public reverse-proxy route, public DNS name, or landing-page entry.
- **SC-008**: A deliberately-downed backend — the Mac's inference server stopped mid-test — produces fallback rather than an error, and the Mac rejoins the pool within one health-check interval of returning, with no operator action. This is exercised during acceptance, not assumed.
- **SC-009**: An input longer than the small tier's context window is answered by a larger tier rather than returning a context-length error.
- **SC-010**: A client driven past its own limit is refused with a clear error attributed to that client, while other clients continue to be served.
- **SC-011**: Background health checks over one week add no material metered spend (under 1% of the period's total).
- **SC-012**: Exhausting the gateway-wide cap refuses requests with an error distinguishable from a per-client breach and raises its own alert.
- **SC-013**: With every backend deliberately made to fail and **no client traffic flowing**, an alert fires within one canary interval — the gateway does not sit silently green.

## Decisions

Three choices the source backlog deliberately left open are settled here:

- **D-001 — Gateway**: **LiteLLM with PostgreSQL** (FR-014). Chosen over a config-only
  LiteLLM and over Bifrost because it is the only option that serves per-client budgets (FR-010) and
  per-alias spend (SC-005) natively rather than reconstructing them from token counts, and because
  its documentation depth on health-check-driven routing covers exactly the intermittent-backend case
  this feature turns on. The cost is accepted knowingly: the LXC grows to 4 GB / 16 GB (FR-001) and
  gains a stateful dependency to keep healthy, migrate and patch. **Redis was dropped from the
  original form of this decision**: everything D-001 was chosen for is Postgres-backed, and Redis
  only shares state between workers, of which there is one. It returns as a four-line addition if
  the worker count ever rises.
- **D-003 — Aggregator**: **OpenRouter**, on ecosystem size, automatic provider failover, a free
  tier and bring-your-own-key support. It sits behind the alias indirection like any other
  deployment, so substituting it later changes no requirement.
- **Client auth**: **per-client keys plus a gateway-wide cap** (FR-010, FR-015). The two-level shape
  is deliberate — per-client keys keep one runaway agent from starving the others, and the cap is the
  backstop for a failure mode nobody predicted. The cap's own risk is recorded below.
- **Local runtime**: **Ollama**, headless, with models kept resident (FR-016). Its keep-alive setting
  maps directly onto the cold-load requirement, and it is the best-trodden provider path from the
  gateway. LM Studio may remain installed on the Mac for hands-on experimentation, but it is not
  deployed, not addressed by an alias and not monitored.
- **Exposure scope**: **LAN + tailnet, no public reachability** (FR-008, SC-007). The original
  "tailnet-only" wording was narrowed once the design was concrete: the gateway listens on the LAN so
  the existing monitoring stack can scrape it without putting a second LXC on the tailnet. The trade
  is explicit — a compromised LAN host can reach the service holding every provider key. Recorded as
  an accepted risk below rather than left implicit in a requirement nobody could satisfy as written.
- **Tailnet egress**: the LXC gets its **own** tailnet path (FR-017), because the PVE host's subnet
  router advertises the LAN *into* the tailnet and gives a LAN-only LXC no route back out. This was
  discovered during planning; the spec previously assumed the path already existed.
- **D-002 — Routing signal**: unchanged from the backlog — route on **declared intent, not measured
  difficulty**.

> **Amended after planning.** Three of the decisions above were revised once Phase 0 made the design
> concrete: Redis was dropped from D-001, FR-009(c) became a signal requirement rather than a probe
> requirement, and the tailnet path moved from an assumption to FR-017. Rationale for each is in
> [research.md](./research.md) (D-102, D-103, D-104).

## Assumptions

- Tailscale is running on the Mac, which is reachable by a stable MagicDNS name from anything on the tailnet. **The LXC's own path onto the tailnet is built by this feature, not assumed** — see FR-017.
- An OpenRouter account and an Anthropic API key exist, both billed to the account owner.
- **Initial tier→model mapping** (hardware-dated, Mac at 32 GB): `hermes-fast` → a 4–8B local model; `hermes-balanced` → a 14–32B local model with an aggregator standby; `hermes-deep` → the Anthropic API (`claude-sonnet-5` class). On the 128 GB upgrade this is revisited — FR-003 exists so that revisit is a configuration edit.
- Intent routing is sufficient because the caller already knows whether a job is "classify this" or "reason about this", making it cheaper, deterministic and debuggable. Semantic or difficulty-based routing is deferred; it slots in above the gateway later without changing clients.
- The per-client and gateway-wide spend limits are set to values the account owner has chosen deliberately; picking the numbers is an operational decision, not a design one.
- The deploy follows the same shape as existing container-in-LXC services (e.g. `market-model`, `eurooffice`), and the monitoring-contract and pipeline-registration workflows are the known existing ones.
- ~4 GB of PVE RAM headroom and ~16 GB of disk are available for the new LXC.
- Wake-on-LAN for the Mac is not depended upon; the design treats the Mac as intermittent by construction.

## Out of Scope

- Hermes itself and the Claude-subscription "plan door" — covered by `065-hermes-service`. This feature delivers the router only.
- Semantic or difficulty-based per-prompt routing; revisit once there is traffic worth optimising.
- Local inference on the PVE node — not viable on the node's integrated graphics.
- A chat UI in front of the gateway.
- Any public reverse-proxy route or landing-page entry.
- Provisioning or managing the Mac's models beyond the requirement that Ollama runs headlessly and keeps the aliased models resident.
- LM Studio on the Mac — it may remain installed for manual experimentation but is not deployed, addressed or monitored by this feature.

## Dependencies

- **Blocked by**: nothing.
- **Blocks**: `065-hermes-service` — Hermes is the first consumer of this endpoint.
- **Assumes**: Tailscale and Ollama running on the Mac; a tailnet auth credential the LXC can use to join (FR-017); ~4 GB PVE RAM and ~16 GB disk headroom; an OpenRouter account and an Anthropic API key; the existing monitoring and pipeline-registration workflows as used by `market-model` and `eurooffice`.

## Risks & Fallbacks

- **Stateful dependency on one LXC**: the LiteLLM footprint puts a database on the service host, which must survive restart and upgrade, be migrated on version bumps, and be patched. A failed migration presents as authentication failure for every client, which is why backing-service health is part of readiness (see Edge Cases) rather than inferred from the gateway container. If the operational weight proves unjustified once real traffic exists, the documented retreat is config-only LiteLLM with spend derived from token counts and a static price table — a smaller change than switching gateways, because the alias mapping is unaffected.
- **LAN reachability is an accepted trade** (FR-008): the gateway holds every provider credential in the homelab and answers to any host on the LAN. This was chosen over a genuinely tailnet-only listener because the alternative forces the monitoring LXC onto the tailnet as well, doubling the egress problem for one probe. Mitigations are per-client keys (FR-015), the two-level spend caps (FR-010), and no public route of any kind. If the LAN ever stops being a trusted segment, revisit this first — it is the single widest exposure in the design.
- **Free-tier metric gating**: some LiteLLM Prometheus metrics are enterprise-gated. If per-alias spend turns out not to be among the free-tier metrics despite the database being present, the fallback is the same token-count-plus-price-table derivation, not dropping SC-005.
- **Gateway-wide cap as a shared failure**: the backstop cap protects the bill by refusing every client at once. Set too low it becomes a self-inflicted outage. Mitigation is its own distinct alert (FR-009, SC-012) and a cap set with real headroom above the sum of per-client limits.
- **Known routing-pool defect**: a pool-selection bug ("no deployments available" against apparently healthy deployments) has been reported against LiteLLM. Mitigation is FR/SC-008: the downed-backend drill is run against the exact pinned version before promotion, and the pin is not advanced without re-running it.
- **Cold-load false fallbacks**: Ollama unloads idle models by default, so the first request after idle can exceed a naive timeout and silently push traffic to the metered tier. Mitigation is a keep-resident policy on the Mac plus a timeout that accounts for cold load; the metric to watch is unexpected metered volume on `hermes-fast`.
- **Credential blast radius**: the router concentrates every provider key in one place. Mitigation is no public route, vault-sourced secrets, per-client keys, and no subscription credential of any kind. The residual LAN exposure is recorded as its own accepted trade above.
