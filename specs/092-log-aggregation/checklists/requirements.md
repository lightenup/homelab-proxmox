# Specification Quality Checklist: Log Aggregation and Log-Based Alerting

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-24
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- This is an infrastructure spec for a single operator, so "stakeholder" means the homelab
  operator. The owner decided the tooling (Loki and Alloy), where the store runs, the 30-day
  retention, the five services that get error rules, and that there is no time-of-day rule. These
  are kept as decisions, not open implementation choices. Credential formats (FR-005) are named
  because they define what the redaction drill tests.
- Low-level settings from the backlog item (WAL ceiling, cache sizes, retry counts, rule file
  paths, metric names) were left out of the FRs. They are plan inputs, listed under Dependencies →
  Plan inputs and in the backlog item's Research notes.
- Owner answers of 2026-10-24 are under Clarifications: the owner's key is allowed from any
  internal source (FR-009), the pipeline is production-only (FR-017, SC-009), and a leaked
  credential is rotated and purged by a documented procedure (FR-016, SC-008). FR-016 and FR-017
  are new compared with the backlog item. FR-001 to FR-015 keep the backlog's numbering.
- Validation passed on the first iteration after one wording fix: FR-015's scope sentence read as
  if it excluded the Proxmox host.
- Amended during `/speckit-plan` (2026-10-24), recorded under Clarifications as "Session
  2026-10-24 (plan: login census)":
  - FR-009 now keys on (users, key, source class), because LAN addresses are DHCP. The source
    classes are the Proxmox host, the LAN, and the tailnet for pve.
  - FR-015 now covers the LXCs only. The owner kept password SSH on pve, and every password
    login there alerts (new US-4 scenario 6, SC-005).
  - FR-017: the store renders on every path. The production switch covers collectors, rules and
    the expected-host set.
  - FR-002 and FR-008: Nextcloud's own log file is collected, because its errors exist only
    there.

  Still passes.
- Amended after `/speckit-analyze` (2026-10-24):
  - SC-009 also covers the pipeline alert rules (the LAB path no longer renders them).
  - FR-003 is checked at deploy.
  - The flood edge case is now a per-host throttle with no loss.
  - Multi-line joining is deferred.
  - US3 scenario 1: the query is carried in the summary.
  - FR-001's pin placement wording was fixed, and the install assumption now names the GitHub
    `.deb`.

  Still passes.
