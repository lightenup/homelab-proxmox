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
| ✓ | [Market-model service deploy](./048-market-model-deploy.md) | **Delivered** — see `specs/049-market-model-deploy/` (+`050` expose, +`051` lab-IP fix) | Hosts the **market-model** sibling service (API + MCP, no GUI) on its own LXC, modelled on `047` but simpler: one image as two roles, `api:8000`+`mcp:8001` published direct (tailnet-only, no auth gate), liveness `/healthz`; disposable content-addressed cache → no backup/NFS. Deployed on its own LXC and exposed at `market-model.hus-sky.no`. |
| — | [Nextcloud upgrade 32 → 34](./057-nextcloud-upgrade-33-34.md) | **Delivered** — see `specs/060-nextcloud-upgrade-33-34/` | Sequential NC major upgrades **32→33→34** through the gated pipeline, backup/restore-drill fencing every hop, app-compat pass that drops built-in CODE (`richdocumentscode`). Prerequisite: the Euro-Office connector needs NC **33–35** (verified `info.xml`). ✅ Landed on **34.0.1** healthy, data intact; built-in CODE removed; `058` unblocked. (Also fixed a pre-existing broken nightly backup — `mysqldump` gone from the MariaDB 11 image → `mariadb-dump`.) |
| ✓ | [Euro-Office document server deploy](./058-eurooffice-deploy.md) | **Delivered** — see `specs/062-eurooffice-deploy/` | Deployed **Euro-Office** (AGPLv3 sovereign fork of ONLYOFFICE DocumentServer, `ghcr.io/euro-office/documentserver:v9.3.2` via `docker_compose_v2` on its own LXC), routed `eurooffice.hus-sky.no` through Caddy (TLS+WS), wired the `eurooffice` connector into Nextcloud via `occ`. Replaces flaky built-in CODE; OnlyOffice-grade `.docx` fidelity. |
| — | [Migrate host-bind NFS services to in-guest](./migrate-host-bind-mounts-to-in-guest-nfs.md) | Idea (Backlog) — sparse stub | Move **immich** + **nextcloud** off the host-mount + `pct set` bind pattern onto the in-guest NFS pattern (jellyfin/financial-scenario). Removes the fstab/`pct set`/orchestrator seam. Watch uid/gid mapping + DR-orchestrator coupling. |
| — | [Path-gate the Promote confidence suite](./063-ci-confidence-suite-path-gate.md) | Backlog — CI perf | The Promote pipeline spends ~20 of ~22 min on a **generic** lab-hypervisor confidence suite that's identical for every service/change. Gate it on provisioning-relevant paths (mirroring `mutation.yml`'s `gate`→`result` split) so role/template/host_vars/docs promotes drop to ~2 min, while provisioning changes still run the full gate. Skipped ≠ failed, so prod apply needs no override. Independent; no service/data impact. |
| — | [Improvement candidates (consolidated)](./improvement-candidates.md) | Ideas (Backlog) — sparse | Operability / monitoring / security backlog carried over from the retired `specs/candidate/`. Grouped one-liners with Open/Done status. |

## Sequencing note

The PFS application work landed first in its own repo (`personal-financial-scenarios`):
**PFS 046 (MCP-as-HTTP-adapter refactor) → PFS 047 (scenario persistence / SQLite)**, released
together as **`v0.2.2`**. The homelab side is now actionable.

On the homelab side: **consolidate-service-versions (✓ delivered) → 047 financial-scenario v2
deploy**. Consolidation means the v2 image-tag bump (and every future bump) is a one-line edit in
the canonical `group_vars` location rather than scattered across role defaults.

**Nextcloud office-suite path** (both delivered): **`057` (NC 32→34 upgrade, `specs/060-*`) → `058`
(Euro-Office deploy, `specs/062-*`)**. `057` was the hard gate — the `eurooffice` connector's
`info.xml` requires NC `min-version="33"` — and was the riskier half (two sequential major upgrades
against live user data, fenced by a restore-verified backup per hop). With NC on **34**, `058` landed
as a familiar `lxc_service` + `docker_compose_v2` deploy plus one `caddy_services` route, replacing
the flaky built-in CODE (`richdocumentscode`) with an OnlyOffice-grade, AGPLv3, EU-sovereign editor.
