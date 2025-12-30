# Feature Specification: Tier 2 Hardening

**Feature Branch**: `019b1-proxmox-lab-harness-tier2-hardening`
**Created**: December 30, 2025
**Status**: Draft
**Input**: User description: "Implement the next hardening iteration for our Proxmox Lab Harness Tier 2."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure & Correct Repository Management (Priority: P1)

The harness must configure Proxmox VE repositories securely and correctly for Debian 13 (Trixie), using proper keyring management (official package or signed-by key file) instead of loose GPG files.

**Why this priority**: Critical for system stability and security. Using the correct repos and keys ensures we get valid packages and avoid "unauthenticated" warnings or future breakages.

**Independent Test**: Can be tested by running the harness and inspecting `/etc/apt/sources.list.d/` and `/usr/share/keyrings/` on the lab VM.

**Acceptance Scenarios**:

1. **Given** a fresh Debian 13 lab VM, **When** the harness runs, **Then** the Proxmox VE no-subscription repo is configured with `signed-by` pointing to a valid keyring (either from package or downloaded file).
2. **Given** a lab VM with the enterprise repo present, **When** the harness runs, **Then** the enterprise repo is disabled or removed.
3. **Given** an invalid repo configuration, **When** the harness runs, **Then** it fails fast if `apt-cache policy` shows the repo is missing or has no candidate.

---

### User Story 2 - Fully Non-interactive Installation (Priority: P1)

The harness must perform all package installations (Proxmox VE, Postfix, etc.) without any user interaction, preventing hangs due to prompts.

**Why this priority**: Essential for automation. Any prompt (like Postfix configuration or `needrestart`) breaks the unattended lab run.

**Independent Test**: Can be tested by running the harness against a fresh VM and observing that it completes without pausing for input.

**Acceptance Scenarios**:

1. **Given** a fresh lab VM, **When** installing `postfix`, **Then** it uses preseeded configuration (`postfix/main_mailer_type`='Local only', `postfix/mailname`=<hostname>) and does not prompt.
2. **Given** a kernel update or service restart, **When** `needrestart` triggers, **Then** it is configured with `NEEDRESTART_MODE=a` to restart automatically.
3. **Given** a slow mirror, **When** apt operations occur, **Then** retries (>=3) and timeouts prevent indefinite hangs.

---

### User Story 3 - Idempotent Execution (Priority: P1)

The harness and playbook must be re-runnable on an existing Tier 2 VM without causing errors or unnecessary changes.

**Why this priority**: Allows for iterative development and ensures the system converges to a desired state.

**Independent Test**: Run `pve-lab run --tier 2 --keep`, then run the Tier 2 playbook again against the existing VM. The second run should succeed with `changed=0`.

**Acceptance Scenarios**:

1. **Given** a successfully provisioned Tier 2 VM (kept from previous run), **When** the harness is run again against it, **Then** it completes successfully.
2. **Given** a re-run, **When** checking Ansible output, **Then** tasks like repo setup and package install report `ok` (no change).
3. **Given** a re-run, **When** checking artifacts, **Then** a new `tier2.log` and `summary.json` are generated correctly.

---

### User Story 4 - Enhanced Preflight Checks (Priority: P2)

The harness must validate the environment more rigorously before attempting installation, including network and virtualization capabilities.

**Why this priority**: Saves time by failing early if prerequisites (like nested virtualization or internet access) are missing.

**Independent Test**: Run the harness in an environment with missing prerequisites (e.g., no nested virt) and verify it fails with a clear error.

**Acceptance Scenarios**:

1. **Given** a host without nested virtualization enabled, **When** running in `--tier2-mode plus`, **Then** the harness fails with a specific error message about `kvm_intel` or `kvm_amd`.
2. **Given** a VM with broken DNS/internet, **When** the harness starts, **Then** it fails immediately if `deb.debian.org` is unreachable.
3. **Given** a hostname that doesn't resolve to a local IP, **When** the harness starts, **Then** it fails if `hostname -f` is not an FQDN or does not resolve to the lab IP.

---

### User Story 5 - Diagnostic Artifact Collection (Priority: P2)

The harness must collect comprehensive diagnostic information (logs, versions, status) after every run, regardless of success or failure.

**Why this priority**: Enables debugging failures without needing to SSH into the ephemeral lab VM.

**Independent Test**: Run the harness (success or fail) and inspect the `artifacts/` directory on the controller.

**Acceptance Scenarios**:

1. **Given** a completed run (success or fail), **When** checking `artifacts/019-lab/<runid>/`, **Then** specific files (`tier2.log`, `pveversion.txt`, `pvesh_version.json`, `services.txt`, `apt_sources.txt`, `apt_policy_proxmox-ve.txt`) exist.
2. **Given** a failed run, **When** checking artifacts, **Then** the evidence bundle is still collected to `artifacts/019-lab/<runid>/` to aid troubleshooting.

### Edge Cases

- **Network Flakiness**: Apt operations might fail due to transient network issues. (Handled by retries).
- **Existing "Wrong" Config**: A VM might have a manually added bad repo. (Handled by repo management tasks ensuring state).
- **Different CPU Vendors**: Host might be AMD instead of Intel. (Handled by improved nested virt checks).

## Clarifications

### Session 2025-12-30

- Q: How should diagnostic artifacts be managed to prevent disk usage growth? → A: Keep last 5 runs (Auto-rotate).
- Q: What is the preferred method for installing the Proxmox repository keyring? → A: Download GPG key file directly to `/usr/share/keyrings/`.
- Q: How should Postfix be preseeded to ensure safety and non-interactivity? → A: "Local only" (Safe, loopback only).
- Q: How should `needrestart` be configured to handle service restarts? → A: Automatic (Restart services without prompting).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST configure the Proxmox VE 9 no-subscription repository using EITHER the official `proxmox-archive-keyring` package OR a downloaded key file in `/usr/share/keyrings/`.
- **FR-001a**: The apt source configuration MUST use the `signed-by` option pointing to the specific keyring.
- **FR-002**: The system MUST disable or remove the Proxmox VE enterprise repository.
- **FR-003**: The system MUST validate repo availability via `apt-cache policy proxmox-ve` and fail fast if the candidate version is missing.
- **FR-004**: The system MUST execute all `apt` and `dpkg` operations with `DEBIAN_FRONTEND=noninteractive`.
- **FR-005**: The system MUST preseed `postfix` with `postfix/main_mailer_type='Local only'` and `postfix/mailname=<hostname>` to avoid interactive prompts.
- **FR-006**: The system MUST set `NEEDRESTART_MODE=a` (or equivalent config) to ensure services restart automatically without prompts.
- **FR-007**: The system MUST implement `apt` retries (>= 3) with backoff and defined timeouts.
- **FR-008**: The system MUST be idempotent; a second execution on the same target MUST result in zero or minimal changes and a success status.
- **FR-009**: The system MUST validate that `hostname -f` returns an FQDN resolving to the primary IP (10.99.0.10) and that external repositories are reachable.
- **FR-010**: The system MUST detect nested virtualization support for both Intel (`kvm_intel`) and AMD (`kvm_amd`) when running in `plus` mode.
- **FR-011**: The system MUST collect diagnostic artifacts (`tier2.log`, `pveversion.txt`, `pvesh_version.json`, `services.txt`, `apt_sources.txt`, `apt_policy_proxmox-ve.txt`) to the controller's `artifacts/019-lab/<runid>/` directory on success or failure.
- **FR-012**: The system MUST retain artifacts for the last 5 runs on the controller, rotating only directories matching `artifacts/019-lab/lab-*`.

### Success Criteria

- **SC-001**: 5 consecutive runs of `./scripts/lab/pve-lab run --tier 2` succeed with no manual intervention.
- **SC-002**: 5 consecutive runs of `./scripts/lab/pve-lab run --tier 2 --tier2-mode plus` succeed.
- **SC-003**: Tier 2 playbook execution is idempotent: running the playbook a second time against an existing, provisioned VM yields `changed=0` (or documented minimal changes).
- **SC-004**: No interactive prompts are observed during execution.
- **SC-005**: Diagnostic artifacts are present in `artifacts/019-lab/<runid>/` for every run.

### Key Entities

- **Lab VM**: The ephemeral Debian 13 VM being configured as a Proxmox host.
- **Artifact Bundle**: A collection of text files and logs captured from the Lab VM.
- **Keyring**: The GPG keyring used to verify Proxmox repository packages.
