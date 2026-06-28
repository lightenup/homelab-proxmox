# Homelab Backlog

Index of pending / in-flight backlog items under `docs/backlog/`. Implemented features
that have moved to `specs/` are not relisted here once shipped; this is the "not yet done"
queue plus recently-landed deploy work kept for context.

Items are listed in intended implementation order.

| Order | Item | Status | Notes |
| --- | --- | --- | --- |
| ✓ | [Service landing page at hus-sky.no](./045-landing-page.md) | Implemented | Independent; apex landing page generated from `caddy_services`. Not on the PFS path. |
| ✓ | [Financial-scenario service deploy](./046-financial-scenario-deploy.md) | Implemented (2026-06-18) | Original 3-container deploy of PFS `0.1.0` (stateless). Baseline the v2 deploy builds on. |
| ✓ | [Consolidate service version variables](./consolidate-service-versions.md) | Delivered (`specs/047-consolidate-service-versions/`) | All image-version pins now live in `group_vars`; the v2 tag bump is a one-line edit there. |
| ✓ | [Financial-scenario v2 deploy (stateful)](./047-financial-scenario-v2-deploy.md) | Implemented | Deploy PFS **`v0.2.2`** (`046`+`047`): host bind-mount `scenarios.db` on `api`, `mcp` → stateless HTTP client, new `financial_scenario_backup` role → Synology NFS. PFS prereqs shipped; open questions resolved. |
| — | [Market-model service deploy](./048-market-model-deploy.md) | Backlog — blocked on market-model `006` | Host the **market-model** sibling service (API + MCP, no GUI) on its own LXC, modelled on `047` but **simpler**: one image run as two roles, `api:8000`+`mcp:8001` published direct (tailnet-only, no auth gate), liveness `/healthz`. Store is a disposable content-addressed cache → **no backup/NFS**. Unblocks once market-model publishes its first GHCR image. |
| — | [Migrate host-bind NFS services to in-guest](./migrate-host-bind-mounts-to-in-guest-nfs.md) | Idea (Backlog) — sparse stub | Move **immich** + **nextcloud** off the host-mount + `pct set` bind pattern onto the in-guest NFS pattern (jellyfin/financial-scenario). Removes the fstab/`pct set`/orchestrator seam. Watch uid/gid mapping + DR-orchestrator coupling. |
| — | [Improvement candidates (consolidated)](./improvement-candidates.md) | Ideas (Backlog) — sparse | Operability / monitoring / security backlog carried over from the retired `specs/candidate/`. Grouped one-liners with Open/Done status. |

## Sequencing note

The PFS application work landed first in its own repo (`personal-financial-scenarios`):
**PFS 046 (MCP-as-HTTP-adapter refactor) → PFS 047 (scenario persistence / SQLite)**, released
together as **`v0.2.2`**. The homelab side is now actionable.

On the homelab side: **consolidate-service-versions (✓ delivered) → 047 financial-scenario v2
deploy**. Consolidation means the v2 image-tag bump (and every future bump) is a one-line edit in
the canonical `group_vars` location rather than scattered across role defaults.
