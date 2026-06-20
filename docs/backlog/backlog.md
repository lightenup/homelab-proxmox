# Homelab Backlog

Index of pending / in-flight backlog items under `docs/backlog/`. Implemented features
that have moved to `specs/` are not relisted here once shipped; this is the "not yet done"
queue plus recently-landed deploy work kept for context.

Items are listed in intended implementation order.

| Order | Item | Status | Notes |
| --- | --- | --- | --- |
| — | [Service landing page at hus-sky.no](./045-landing-page.md) | Draft (Backlog) | Independent; apex landing page generated from `caddy_services`. Not on the PFS path. |
| ✓ | [Financial-scenario service deploy](./046-financial-scenario-deploy.md) | Implemented (2026-06-18) | Original 3-container deploy of PFS `0.1.0` (stateless). Baseline the v2 deploy builds on. |
| 1 | [Consolidate service version variables](./consolidate-service-versions.md) | Draft (Backlog) | **Do before 047.** Moves all image-version pins into `group_vars`, so the v2 version bump lands in one canonical place. |
| 2 | [Financial-scenario v2 deploy (stateful)](./047-financial-scenario-v2-deploy.md) | Draft (Backlog) — high-level | Deploy the new PFS version: new `scenarios.db` persistent volume on `api`, `mcp` becomes a stateless HTTP client. Depends on PFS `046`/`047`. Revisit before implementation. |

## Sequencing note

The PFS application work lands first in its own repo (`personal-financial-scenarios`):
**PFS 046 (MCP-as-HTTP-adapter refactor) → PFS 047 (scenario persistence / SQLite)**.
Only once those ship as a new versioned image pair does the homelab side become actionable.

On the homelab side: **consolidate-service-versions → 047 financial-scenario v2 deploy**.
Consolidation first means the v2 image-tag bump (and every future bump) is a one-line edit in
the canonical `group_vars` location rather than scattered across role defaults.
