# Feature Specification: Confidence Suite Trim

**Feature Branch**: `086-confidence-suite-trim`

**Created**: 2026-10-18

**Status**: Draft

**Input**: User description: "Trim the lab confidence suite and gate it on its real dependencies. FR-001 suite runs only the hypervisor-nested-workload profile (superset of bootstrap + control-plane; ~18→~8 min); FR-002 the confidence gate path list becomes the suite's dependency closure; FR-003 a drift guard fails CI if the harness/lab playbooks gain an uncovered dependency; FR-004 keep 063 FR-003/005/006/007/009 behaviour. Supersedes 063 FR-002 and FR-008."

## Background

`Prod 1 - LXC Promote` spends 17–21 minutes in the confidence suite. The rest of a promote takes about a minute. Run history and the harness code show two problems:

1. **The suite runs the same work several times.** It runs three profiles in a row, and each one contains the one before it:
   - Every profile re-runs the same bootstrap playbook.
   - The second and third profiles both install Proxmox VE.
   - The third profile only adds a nested VM/LXC workload block and stricter safety checks. The strict checks run in addition to the standard ones, not instead of them.

   On run 39138210585 the three profiles took 2m40, 7m30 and 8m00. The third profile alone covers everything the first two check.
2. **The 063 path gate uses the wrong file list.**
   - **It triggers on files the suite never reads:**
     - `terraform/**`. The suite only runs `terraform fmt` there, which PR CI already does.
     - `ansible/inventories/**`, including the prod inventory.
     - `ansible/roles/lxc_base/**`.
     - All of `scripts/lab/**`, which includes the service deploy orchestrator and the plan renderers.
   - **It misses files the suite does read:**
     - the `assertion_utils` role
     - `ansible/ansible.cfg`
     - `ansible/group_vars/{all,proxmox_hosts}`, which the lab playbooks load through the `ansible/playbooks/group_vars` symlink.

   Example: commit c80273d changed only `ansible/inventories/prod/hosts.yml` and still cost an 18-minute suite run. Replaying every promote since July against the suite's real dependencies, only one would have needed a run: fab0723, which touched `group_vars/all`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A suite run takes one profile, not three (Priority: P1)

An operator promotes a change that does touch the lab harness. The confidence suite runs, but each check runs once. The run finishes in roughly the time of the nested-workload profile alone, and its checks are the same as the three-profile run.

**Why this priority**: This is the largest single saving, about 10 minutes on every run that executes the suite. It needs no change to the gating logic.

**Independent Test**: Force-run the suite with `run_confidence_suite=true` on the branch. Confirm the suite job takes about 8–9 minutes, and that the evidence pack verifies offline and reports `suite_ok=true`.

**Acceptance Scenarios**:

1. **Given** a forced suite run, **When** the suite executes, **Then** it runs the safety step, followed by exactly one profile: `hypervisor-nested-workload`.
2. **Given** that run, **When** its evidence pack is verified offline, **Then** verification passes and the bootstrap, PVE, network, nested-workload and guardrail checks are all present.
3. **Given** an operator who wants to debug a single smaller profile, **When** they run `pve-lab suite bootstrap` or `pve-lab suite hypervisor-control-plane`, **Then** those profiles still work.

---

### User Story 2 - The suite runs only when its own inputs change (Priority: P1)

An operator promotes a service whose changes don't touch any file the suite reads. Examples: a service role, the prod inventory, a Terraform module, the service deploy orchestrator. The gate reports `run=false` and the promote finishes without the suite. A change to a file the suite does read, such as a lab playbook, a harness library, the lab inventory or group vars the lab host loads, still runs the suite.

**Why this priority**: As much benefit as Story 1. Under today's list, most suite runs since July had no relevant change.

**Independent Test**: Replay the changed files of the promotes since July against the new path list. Every promote should skip except fab0723.

**Acceptance Scenarios**:

1. **Given** a diff touching only `ansible/inventories/prod/hosts.yml`, **When** the gate decides, **Then** `run=false`.
2. **Given** a diff touching only `terraform/**`, `ansible/roles/lxc_base/**` or `scripts/lab/pve-service-deploy`, **When** the gate decides, **Then** `run=false`.
3. **Given** a diff touching a lab playbook, a harness library, the lab inventory, `ansible/group_vars/all/**`, `ansible/group_vars/proxmox_hosts/**`, the `assertion_utils` role or `ansible/ansible.cfg`, **When** the gate decides, **Then** `run=true`.
4. **Given** a change to the path list itself or to the promote workflow, **When** the gate decides, **Then** `run=true`, so a gate change is tested once.

---

### User Story 3 - The path list can't silently drift (Priority: P2)

A developer adds a new dependency to the suite: a new library sourced by the harness, a new role included by a lab playbook, or a new group the lab host joins. PR CI fails until the path list covers the new dependency. The gate therefore can't start skipping the suite for files it now reads.

**Why this priority**: A false skip is worse than a false run (063 Edge Cases). A narrower list increases that risk unless something checks it.

**Independent Test**: Locally, add a `source "${LIB_DIR}/newlib.sh"` line to the harness, or an `include_role` of an uncovered role to a lab playbook. The Python test suite should fail and name the uncovered path.

**Acceptance Scenarios**:

1. **Given** the harness sources a file the list doesn't cover, **When** PR CI runs, **Then** the drift test fails and names that file.
2. **Given** a lab playbook includes a role the list doesn't cover, **When** PR CI runs, **Then** the drift test fails.
3. **Given** the promote workflow stops reading the path list file (for example, someone reintroduces an inline regex), **When** PR CI runs, **Then** the test fails.

### Edge Cases

- **Path list file missing or empty at gate time**: the gate fails safe and returns `run=true`, consistent with 063 FR-007.
- **Gate reads the workflow's ref, not the promoted SHA**: the `confidence_gate` job checks out the workflow's ref. Promotes run from `main`, so the list matches what's merged. A list changed only on an unmerged branch takes effect once merged, and the list file and workflow are themselves in the list.
- **Galaxy dependencies**: `ansible/requirements.yml` is listed conservatively, even though the lab playbooks don't currently use Galaxy content.
- **Tier-1 template (VMID 9001)**: CI no longer exercises it. It's still available for manual `bootstrap` runs.
- **Upstream breakage**: the suite still installs Proxmox VE from upstream on every run, so it still catches upstream repository failures when it runs. Baking PVE into the template is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The confidence suite MUST run the safety step and then exactly one profile, `hypervisor-nested-workload`. The `bootstrap` and `hypervisor-control-plane` profiles MUST remain runnable on their own.
- **FR-002**: The confidence gate MUST decide using a path list kept in a single repo file (`scripts/ci/confidence-suite-paths.txt`). The list MUST cover the files the suite reads:
  - the harness and the libraries it sources (directly or through another library)
  - `checks.d/`, `profiles.d/`, `contracts/`
  - the evidence fetch and verify scripts used by the suite job
  - the tier-2 template script
  - the lab playbooks and the lab inventory
  - group vars for every group the lab host belongs to
  - roles the lab playbooks include
  - `ansible/ansible.cfg` and `ansible/requirements.yml`
  - the promote workflow and the list file itself

  The list MUST NOT include `terraform/**`, non-lab inventories, `ansible/roles/lxc_base/**`, or `scripts/lab/**` files the suite doesn't use.
- **FR-003**: PR CI MUST fail when any of the following isn't matched by the list:
  - a file the harness, `guardrails.sh` or `lib/rebuild.sh` sources or runs
  - a role a lab playbook includes or imports
  - a group-vars directory for a group in the lab inventory

  PR CI MUST also fail when the promote workflow's gate stops reading the list file.
- **FR-004**: These 063 behaviours MUST NOT change:
  - FR-003: `run_confidence_suite=true` forces a run.
  - FR-005: a skipped suite counts as a pass.
  - FR-006: a failed suite blocks prod apply unless overridden.
  - FR-007: inability to compute the diff means run.
  - FR-009: the diff base is the last verified commit, with the merge-base as fallback.
- **FR-005**: If the path list file is missing or has no patterns, the gate MUST decide `run=true`.
- **FR-006**: 063's spec MUST record that its FR-002 (path list) and FR-008 (no change to what the suite does) are superseded by this feature.

### Key Entities

- **Confidence-suite path list**: one regular expression per line (`#` comments allowed), matched against repo-relative changed paths. It's the single source of truth shared by the gate and the drift test.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A suite run that executes takes **≤ 10 minutes** (was 17–21).
- **SC-002**: Replaying the promotes since 2026-07-01 against the new list, **at most 1** would run the suite (fab0723), down from every run that executed under the old gate.
- **SC-003**: A promote of a change confined to service roles, the prod inventory, Terraform or the service orchestrator completes **without** the suite and needs no override for prod apply.
- **SC-004**: Introducing an uncovered harness or playbook dependency fails PR CI **100%** of the time (verified by the test's own negative cases).
- **SC-005**: Zero regressions in the force-run, skip-as-pass, failed-suite override and destructive-plan paths.

## Assumptions

- The nested-workload profile covers the other two: it runs the same bootstrap and PVE install tasks. Its `plus` block and `strict` safety checks are additions, not alternatives.
- Promotes run from `main`, so the gate reading the list from the workflow's ref is acceptable. This is the same assumption as 063's checkout.
- Adding a list file is justified under Constitution IV: it has two consumers today (the gate step and the drift test), and the inline regex couldn't be checked.
- Out of scope:
  - baking PVE into the tier-2 template
  - moving the suite off the promote path
  - recording a dynamic file-access manifest

  These remain follow-up options.
