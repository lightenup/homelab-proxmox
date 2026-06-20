# Feature Specification: Financial-Scenario v2 Deploy (Stateful)

**Feature Branch**: `047-financial-scenario-v2-deploy`
**Created**: 2026-06-20
**Status**: Draft (Backlog) — **high-level; revisit before implementation**
**Input**: Host the next version of the `personal-financial-scenarios` app, which introduces (1) a
single-engine topology where the MCP server is a thin HTTP client of the api (PFS `046`) and (2) a
persisted scenario store backed by SQLite on the api service (PFS `047`). Update the existing
homelab deploy to match — without regressing the LAN/tailnet-only posture or the gated pipeline.

> **Scope note**: This document is intentionally high-level. The exact volume paths, env vars, and
> backup mechanism depend on decisions still being finalized in the PFS repo (PFS `046`/`047`). Flesh
> out FRs and the Decision Log during planning, once those specs land and the new image tag exists.

## Summary

The original deploy ([046-financial-scenario-deploy](./046-financial-scenario-deploy.md)) hosts PFS
`0.1.0` as a **stateless** 3-container stack (`api`, `mcp`, `gui` from two GHCR images), persisting
only the reference-data bind-mount. The next PFS version changes two things that the homelab deploy
must track:

1. **MCP becomes a stateless HTTP client of the api** (PFS `046`). The `mcp` container no longer runs
   its own engine or loads reference data — it forwards all traffic to `api:8000`. Deployment effect:
   the `mcp` container's `reference_data` bind-mount is **removed**, and `mcp` gains a `depends_on:
   api` (service_healthy) so it never starts before the authority it depends on.
2. **The api gains a persisted SQLite scenario store** (PFS `047`). For the first time the backend
   holds **user-generated state** (saved scenarios authored from the GUI or by an MCP agent).
   Deployment effect: a **new persistent volume** for `scenarios.db` on the `api` service that must
   survive container recreation and image upgrades — and, unlike reference data (which originates in
   the app repo), this data exists **only** on the host, so it needs a real backup story.

Everything else from `046` is unchanged: two pinned GHCR images, GUI-only published port with nginx
fronting `/api`, `/docs`, `/mcp`, the GHCR pull credential, the LAN/tailnet-only posture (no Caddy
route, no landing-page card), and the blackbox liveness monitoring contract.

## What changes vs. 046 (the whole feature, at a glance)

| Area | 046 (current) | 047 (this item) |
| --- | --- | --- |
| Image tag | `financial_scenario_version: 0.1.0` | bump to the new PFS release tag |
| `mcp` container | own engine, reference-data bind-mount | stateless HTTP client; **no** reference-data mount; `depends_on: api` |
| `api` state | reference-data bind-mount only | reference-data **+ new `scenarios.db` persistent volume** |
| Backups | out of scope (data originates in repo) | **in scope** — `scenarios.db` is host-only user data |
| Topology | two independent engine copies | single engine authority on `api` |

## User Scenarios (high-level — expand during planning)

### US1 — Upgrade in place without losing data (P1)
As the operator, I bump the pinned tag and redeploy through the existing gated pipeline; the stack
comes up healthy on the new topology, and **previously saved scenarios and reference-data edits
survive** the image re-pull.

### US2 — Agent-authored scenarios appear in the GUI (P1)
As an operator using an MCP client over the tailnet, I save a scenario via MCP; it is persisted on
the `api` service and is then selectable in the GUI for comparison — proving the single-store,
single-engine topology works end-to-end in the homelab.

### US3 — Saved scenarios are backed up (P2)
As the operator, I want `scenarios.db` included in the homelab backup regime (à la
`immich_backup`/`nextcloud_backup`) so a lost LXC does not lose hand-built scenarios.

## High-level requirements (to be expanded)

- **HR-001**: Pin the new PFS image tag via the consolidated `group_vars` version variable (depends on
  [consolidate-service-versions](./consolidate-service-versions.md)).
- **HR-002**: Add a persistent host volume for the api scenario store (`scenarios.db`), mounted at the
  path the new app version reads/writes. *(exact host path + container path: open, see Q-001)*
- **HR-003**: Remove the `mcp` container's reference-data bind-mount and add `depends_on: api`
  (service_healthy), reflecting PFS `046`'s HTTP-client topology.
- **HR-004**: Preserve first-deploy-vs-upgrade safety for **both** stateful mounts — seed reference
  data when empty (as today); never clobber an existing `scenarios.db` on upgrade.
- **HR-005**: Add a backup/restore path for `scenarios.db` consistent with the existing backup roles.
  *(mechanism: open, see Q-002)*
- **HR-006**: No change to the exposure posture, the GHCR pull, the GUI-only port model, or the
  monitoring contract from `046`.

## Dependencies

- **PFS `046` (MCP-as-HTTP-Adapter Refactor)** — hard prerequisite; defines the stateless-mcp topology.
- **PFS `047` (Scenario Persistence & Agent Authoring)** — hard prerequisite; defines the SQLite store,
  the store path, and whether the api needs a new env var for the DB location.
- **A new PFS GHCR release tag** containing both of the above — the thing this deploy pins.
- **[consolidate-service-versions](./consolidate-service-versions.md)** — sequenced first so the tag
  bump lands in the canonical `group_vars` location.
- **[046-financial-scenario-deploy](./046-financial-scenario-deploy.md)** — the baseline this extends.

## Out of Scope (carried from 046 unless noted)

- Public exposure / Caddy route / landing-page card — still excluded (LAN/tailnet-only).
- App source changes — done in the PFS repo (`046`/`047`); this only pulls and runs pinned tags.
- App-level Prometheus metrics — still blackbox liveness only.
- LLM-backed catalog ingestion — `EXTRACTION_BASE_URL` stays unset.
- **Backups are now IN scope** (the one deliberate reversal from 046's "out of scope").

## Open Questions (resolve when PFS 046/047 finalize)

- **Q-001**: What is the store path inside the api container, and does it take a configurable env var
  (e.g. a DB path / data dir)? Drives the bind-mount target and any new `environment:` entry.
- **Q-002**: Backup mechanism for `scenarios.db` — reuse an existing backup role pattern, or a simple
  scheduled file copy / SQLite `.backup`? SQLite needs a consistent snapshot (not a raw cp under
  concurrent writes), so the chosen method must quiesce or use the online-backup API.
- **Q-003**: Does the single-engine topology change LXC sizing (api now also serves all MCP traffic)?
  Likely still fits 2c/2048MB, but confirm during planning.
- **Q-004**: Is the MCP shared-secret still image-baked (046 D-011), or did PFS make it
  env-configurable? If the latter, wire a vault-backed per-deploy secret here.
