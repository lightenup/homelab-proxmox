# Specification Quality Checklist: ntfy — self-hosted push notifications to the owner's phone

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-16
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

All items pass on the first iteration.

- **Implementation detail moved out.** The backlog entry names concrete mechanisms: config keys
  (`auth-default-access: deny-all`), the webhook template and `priority` query parameter, vault
  variable names, `host_vars`, and `caddy_services` flags. These are rephrased as outcomes in
  FR-005 to FR-010 and FR-001 to FR-003, and the backlog entry is cited as the planning input. The
  product name (ntfy) appears only in the title and in Assumptions, following the `065` convention.
- **Requirement → acceptance coverage**:

  | Requirements | Covered by |
  |---|---|
  | FR-003, FR-004, FR-008, FR-009, FR-010 | US-1, SC-001 |
  | FR-005, FR-006, FR-007 | US-2, SC-002 |
  | FR-013, FR-015 | US-3, SC-005 |
  | FR-012 | US-4 |
  | FR-011 | SC-003 |
  | FR-001, FR-002, FR-014, FR-016 | SC-004 (rebuild through the normal deploy path) |
  | FR-017 | SC-007 |

- **Open questions resolved with defaults.** Retention is 72 h (FR-013). The priority + template
  combination is recorded as an assumption to verify on the lab deploy, not as a clarification,
  because the requirement (FR-010) does not change either way.
- **Numbering.** The directory uses `082` to match the backlog entry and the cross-references in
  `083`, not the next free spec number (`066`). Backlog `066` is a different item.
