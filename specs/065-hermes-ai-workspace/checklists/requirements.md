# Specification Quality Checklist: Hermes — a self-hosted AI workspace on local models

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-20
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

All items pass. Two iterations were required.

### Iteration 1 — three requirements had no acceptance coverage

A keyword scan initially reported full coverage and was **wrong**: it matched "cite" in SC-007
(which is about uploaded documents) against FR-022 (web search), and "programmatic" in SC-002
(which only asserts the interface *refuses* unauthenticated callers) against FR-024. Reading the
criteria rather than grepping them found three genuine gaps:

| requirement | gap | closed by |
|---|---|---|
| FR-022 — web search | no criterion at all | **SC-013** |
| FR-024 — programmatic interface | only its auth behaviour was covered, never that it works | **SC-014** |
| FR-025 — scheduled prompts | SC-010 covered failure being visible, never a successful run | **SC-015** |

### Judgement calls worth recording

- **"SSH" is named in FR-006 and User Story 4.** It is a protocol name, so arguably an
  implementation detail — but the owner asked for SSH access by name, so it is treated as a stated
  user requirement rather than a leaked choice. The *how* (which keys, which service) is left to
  planning.
- **The chosen application is deliberately not named in the spec.** It is recorded in the research
  note (`docs/backlog/065-hermes-service.md`) instead, so the requirements stay the contract and the
  product remains substitutable. FR-026 constrains the *class* of solution — configuration of
  existing software — which is testable via SC-011 without naming anything.
- **SC-008 refers to "gateway metrics".** The gateway is pre-existing estate context rather than a
  choice this feature makes, so naming it describes where the measurement comes from rather than
  prescribing an implementation.
- **No [NEEDS CLARIFICATION] markers were needed.** Every materially ambiguous decision — the
  application, the authentication posture, where retrieval runs, and which optional capabilities to
  include — was settled with the owner before drafting. The surviving open question (whether the
  self-hosted search component is a sidecar or its own service) is a planning decision, not a
  specification gap.

### Carried into planning

The principal risk is recorded in Assumptions rather than as a requirement: **the estate's reverse
proxy provides no authentication**, so FR-002 places the entire access-control burden on this
system, and it will be reachable from the public internet with the homelab's tools and models behind
it. An estate-wide authentication layer is the correct answer and is explicitly out of scope here.
