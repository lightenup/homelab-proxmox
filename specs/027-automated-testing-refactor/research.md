# Research: Automated Testing Refactor

**Feature**: [specs/027-automated-testing-refactor/spec.md](spec.md)
**Date**: 2026-01-13

This document records research decisions made for the implementation plan. Each decision includes rationale and alternatives considered.

## Decision 1: Python runner structure and invocation

**Decision**: Create a small Python runner as a reusable library + thin CLI entrypoint under `python/src/`, invoked via `PYTHONPATH=python/src python3 -m <module>` (no packaging/install step required).

**Rationale**:
- The repo already uses Python as small CLI utilities invoked directly from workflows and bash, without a packaging step.
- Avoiding runtime dependencies keeps execution reliable on both GitHub Actions runners and the Proxmox executor.
- A real package layout (`src/...`) enables clean imports and testability (unit tests + golden tests) without requiring publishing or installation.

**Alternatives considered**:
- Keep everything under `scripts/` + stdlib `unittest`: simplest, but poorer test ergonomics and harder to evolve.
- Full packaging + `pip install .` in CI: cleanest UX, but introduces dependency bootstrap complexity on runners/executors.

## Decision 2: Dependency management for tests and tooling

**Decision**: Use a minimal Python tooling setup for development and CI (pytest required; optional linting).

**Rationale**:
- pytest enables fixtures and golden tests, which match the repo’s evidence/fixture-driven approach.
- Tooling configuration should remain minimal and not become a deployment dependency.

**Alternatives considered**:
- `requirements-dev.txt` only: simple, but tends to spread config across multiple files.
- No dependency management at all: makes CI brittle and local onboarding inconsistent.

## Decision 3: Golden tests for summaries and evidence parsing

**Decision**: Add golden tests for bounded summaries and evidence parsing by comparing outputs against fixtures in version control.

**Rationale**:
- Summary stability is operator-facing and must not regress during refactors.
- Golden tests provide a tight feedback loop: if output changes, diffs are explicit and reviewable.

**Alternatives considered**:
- Snapshot tests without explicit fixtures: convenient, but easier to accept accidental regressions.
- Only integration tests (run workflows): too slow for PR feedback.

## Decision 4: Nightly mutation testing (mutmut)

**Decision**: Run `mutmut` nightly, scoped initially to the runner’s decision logic and summary/evidence parsing modules. Upload results as CI artifacts.

**Rationale**:
- Mutation testing is most valuable on pure logic where failures are actionable.
- Scoping keeps runtime manageable and avoids noisy mutants in IO-heavy glue.
- Nightly cadence avoids slowing down PR checks.

**Alternatives considered**:
- Run mutation testing on every PR: likely too slow and noisy early.
- Broaden scope to all scripts immediately: higher cost, lower signal until tests mature.

## Decision 5: Molecule for Ansible roles (start with one service role)

**Decision**: Add Molecule coverage for selected Ansible roles, starting with one service role, using a Docker-based driver and an image that supports running Docker-in-Docker where needed.

**Rationale**:
- Role regressions are common and are currently mostly caught in live LAB runs.
- A Docker-based Molecule scenario provides repeatable CI feedback without touching the real Proxmox environment.

**Alternatives considered**:
- Only `ansible-lint` + syntax-check: cheaper but less confidence.
- Delegate Molecule to a real LXC/host: higher fidelity but introduces infra coupling into CI.

## Decision 6: Terraform testing strategy

**Decision**: Treat `terraform fmt`/`validate` as mandatory PR checks everywhere. Add `terraform test` coverage only where it is feasible without requiring access to the Proxmox API; otherwise run `terraform test` as an integration-only job on a trusted/self-hosted runner.

**Rationale**:
- Current Terraform constraints can make `terraform test` effectively require `apply/destroy` for some modules.
- PR checks should not require real infrastructure access.

**Alternatives considered**:
- Upgrade Terraform and adopt modern `terraform test` patterns (plan-only/mocking): enables more offline coverage but requires coordinated version changes.
- Skip `terraform test` entirely: lower confidence during refactors.

## Decision 7: Workflow validation with act

**Decision**: When workflows change during implementation, validate locally using `act` where feasible (minimum: `act -l`, and dry-run the edited workflow).

**Rationale**:
- Matches repo constitution guidance.
- Catches YAML and dispatch contract issues early.

**Alternatives considered**:
- Rely solely on GitHub Actions runs: slower feedback, more iteration time.
