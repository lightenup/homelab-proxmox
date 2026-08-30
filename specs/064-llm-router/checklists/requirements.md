# Specification Quality Checklist: LLM Router (gateway LXC)

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) — *with a deliberate exception, see Notes*
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

**Iteration 1** — Product and vendor names were moved out of the requirements and success criteria
into Assumptions and Risks so the FRs and SCs stayed capability-worded. The aggregator choice and
the tier→model mapping were resolved by informed default rather than left as open markers, since
both have a clear lean and neither changes a requirement. Three markers remained: gateway choice,
client-auth granularity, local inference runtime.

**Iteration 2** — All three markers resolved by operator decision and recorded in a new `Decisions`
section: LiteLLM with PostgreSQL and Redis (FR-014); per-client keys plus a gateway-wide cap
(FR-010, FR-015); Ollama headless with models kept resident (FR-016). Knock-on edits: FR-001 sized
up to 4 GB / 16 GB; FR-009 gained a distinct alert for cap exhaustion; User Story 5 and SC-010 now
require per-client attribution and non-interference; SC-012 added for the gateway-wide cap; three
edge cases added (cap exhaustion as a shared outage, backing-service failure presenting as
auth failure); Risks rewritten around the accepted stateful-dependency cost and the cap's own
failure mode.

**Deliberate exception to "no implementation details"** — FR-014 and FR-016 name LiteLLM,
PostgreSQL, Redis and Ollama, and the Decisions section names OpenRouter. This is intentional and
not an oversight: the source backlog explicitly deferred these choices *to the spec* (D-001, D-003),
they are load-bearing on whether FR-010 and SC-005 are satisfiable at all, and the repository's
existing specs (e.g. `062-eurooffice-deploy`) name concrete products in their FRs. The Success
Criteria remain product-agnostic and are verifiable without knowing which gateway was chosen.

**Iteration 3 (post-`/speckit.analyze` remediation)** — `/speckit.analyze` found two CRITICAL issues,
both the same root cause: Phase 0 changed the architecture without amending the spec in the same
change, which Constitution I requires. Repaired here.

- **FR-014** amended — Redis is now conditional on worker count rather than mandatory, resolving the
  contradiction between the spec's MUST and the plan's Constitution IV recommendation. Operator
  confirmed dropping it.
- **FR-008 / SC-007** amended — "tailnet-only" was unsatisfiable alongside FR-009 (the monitoring LXC
  is LAN-only). Narrowed to "no public reachability", with LAN exposure recorded as an accepted risk
  rather than left implicit.
- **FR-009(c)** reworded from a probe requirement to a *signal* requirement, matching research D-103.
- **FR-017** added — the LXC's tailnet egress path is built by this feature, not assumed.
- **FR-018 / SC-013** added — an all-backends-failing gateway was undetectable without client traffic,
  leaving the spec's own headline edge case unmitigated. Now covered by a failure-rate alert plus a
  synthetic canary.
- **SC-001** sharpened to require all three aliases and a genuine Mac power-off, not just a stopped
  daemon — different failure modes with different timeout behaviour.
- Coverage is now 100%: every FR and SC is referenced by at least one task (was 86% tagged, with
  SC-011 at zero).

**Ready for** `/speckit.implement`. No open questions remain.
