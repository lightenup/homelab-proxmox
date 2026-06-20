# Implementation Plan: Consolidate Service Version Variables into group_vars

**Branch**: `047-consolidate-service-versions` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/047-consolidate-service-versions/spec.md`

## Summary

Relocate three service version pins (`nextcloud_version`, `nextcloud_exporter_version`, `adguard_exporter_version`) out of role `defaults/` files and into a single `# Service versions` block at the top of `ansible/group_vars/services/vars.yml`, alongside the already-present `immich_version` and `financial_scenario_version`. Net result: every non-monitoring service version pin lives in one file, and routine upgrades never require editing a role's internal defaults.

This is a pure variable-relocation refactor. No logic, templates, or deployed behavior change — variable names and values are preserved; only definition locations move. It is a direct application of the constitution's **Code Economy / Consolidate before adding** principle.

## Technical Context

**Language/Version**: YAML (Ansible 2.x)
**Primary Dependencies**: Ansible variable precedence (`group_vars` > role `defaults/`); no new modules or roles
**Storage**: N/A — plain inventory variable files
**Testing**: `ansible-playbook --syntax-check` / `--check` (dry run) against nextcloud and adguard plays; `grep` assertions per spec Verification section
**Target Platform**: Ansible control node (laptop and CI runner, per Dual-Provisioning Parity)
**Project Type**: Infrastructure-as-code (single repo, `ansible/` tree)
**Performance Goals**: N/A
**Constraints**: Values must be byte-for-byte preserved; no commented-out remnants left behind
**Scale/Scope**: 3 files touched, 5 version pins total in the consolidated block

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Spec-Driven Workflow | ✅ | Driven from `specs/047-*/spec.md`; tasks to follow via `/speckit.tasks`. |
| II. Secrets Policy | ✅ | No secrets involved; only public version strings. |
| III. Separation of Concerns | ✅ | Ansible-only change; no Terraform touched. |
| IV. Code Economy (YAGNI) | ✅ | This change *is* a consolidation — it removes scattered definitions and adds no new files, variables, or indirection. No `research.md`/`data-model.md`/`contracts/` generated, as there are no unknowns, no entities, and no external interfaces — empty scaffolding would violate this principle. |
| V. Dual-Provisioning Parity | ✅ | Inventory variables resolve identically from laptop and CI; no workflow dropdown or scope changes needed (no new service). |

**Gate result**: PASS. No violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/047-consolidate-service-versions/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

No `research.md`, `data-model.md`, `quickstart.md`, or `contracts/` are generated: there are zero NEEDS CLARIFICATION items, no data entities, and no external interfaces. Generating them would be empty boilerplate, prohibited by Constitution Principle IV.

### Source Code (repository root)

```text
ansible/
├── group_vars/
│   ├── services/
│   │   └── vars.yml          # ADD `# Service versions` block (top); MOVE immich_version
│   │                         #   & financial_scenario_version into it; ADD the 3 relocated pins
│   └── monitoring/
│       └── vars.yml          # Reference only — existing `# Service versions` style to mirror
└── roles/
    ├── nextcloud/defaults/main.yml   # DELETE nextcloud_version, nextcloud_exporter_version
    └── adguard/defaults/main.yml     # DELETE adguard_exporter_version
```

**Structure Decision**: Existing `ansible/` IaC layout; three existing files edited, no new files created (Code Economy — prefer modifying existing files).

## Implementation Approach

1. **`ansible/group_vars/services/vars.yml`** — Insert a `# Service versions` block near the top (after the shared/docker preamble, mirroring `monitoring/vars.yml` heading style) containing all five pins:
   ```yaml
   # Service versions
   nextcloud_version: "32"
   nextcloud_exporter_version: "0.9.0"
   adguard_exporter_version: "1.2.1"
   immich_version: "v2.4.0"
   financial_scenario_version: "0.1.0"
   ```
   Remove the now-relocated `financial_scenario_version` line from the Financial Scenario section and the `immich_version` line from the Immich section (no duplication).

2. **`ansible/roles/nextcloud/defaults/main.yml`** — Delete the `nextcloud_version` and `nextcloud_exporter_version` lines entirely (no placeholder/comment).

3. **`ansible/roles/adguard/defaults/main.yml`** — Delete the `adguard_exporter_version` line entirely (no placeholder/comment).

## Verification

Per spec Success Criteria and the backlog Verification section:

1. **SC-001 / grep**: `grep -rn "nextcloud_version\|nextcloud_exporter_version\|adguard_exporter_version" ansible/roles/` returns zero matches.
2. **SC-002 / placement**: Confirm all five pins appear under the `# Service versions` block in `ansible/group_vars/services/vars.yml`, with no duplicate definitions remaining in their old sections.
3. **SC-003 / resolution**: `ansible-playbook --syntax-check` plus a `--check` (dry-run) of the nextcloud and adguard plays against a host — confirm no "undefined variable" errors for the relocated variables. If a live host is unavailable, an `ansible -m debug -a "var=nextcloud_version"` (and the other four) against the relevant group confirms resolution from `group_vars`.
4. **SC-004 / single-file edit**: Visually confirm a version bump now requires editing only `group_vars/services/vars.yml` (or `group_vars/monitoring/vars.yml`), zero role-defaults edits.

## Complexity Tracking

No constitution violations — section intentionally empty.
