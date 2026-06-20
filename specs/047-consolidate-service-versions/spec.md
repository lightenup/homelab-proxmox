# Feature Specification: Consolidate Service Version Variables into group_vars

**Feature Branch**: `047-consolidate-service-versions`
**Created**: 2026-06-20
**Status**: Draft
**Input**: User description: "Consolidate service version variables into group_vars"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bump a service version from a single known location (Priority: P1)

A homelab operator needs to upgrade Nextcloud, the Nextcloud exporter, or the AdGuard exporter to a newer release. They open the central service variables file, change the version pin, and run the playbook — without having to know or remember that these particular services keep their version inside a role's internal defaults file.

**Why this priority**: This is the entire purpose of the change. Today three service version pins live in role `defaults/` files while the rest live in `group_vars`, so a routine upgrade requires hunting through role internals. Removing that inconsistency is the core value.

**Independent Test**: Locate every service version pin by opening only the two `group_vars` version blocks; confirm Nextcloud, Nextcloud exporter, and AdGuard exporter versions are all present there and absent from any role `defaults/` file.

**Acceptance Scenarios**:

1. **Given** the operator wants to upgrade Nextcloud, **When** they open `group_vars/services/vars.yml`, **Then** they find `nextcloud_version`, `nextcloud_exporter_version`, and `adguard_exporter_version` under a clearly labeled service versions block.
2. **Given** the operator searches the role `defaults/` files for any of the three relocated version variables, **When** the search completes, **Then** no matches are found.
3. **Given** the three version variables now live only in `group_vars`, **When** the operator runs the Nextcloud or AdGuard playbook against a host, **Then** the playbook completes with no "undefined variable" errors.

---

### User Story 2 - All version pins grouped and discoverable (Priority: P2)

An operator scanning the configuration wants every service version in one consistent, labeled section so the inventory of pinned versions is obvious at a glance, matching the style already used in the monitoring variables file.

**Why this priority**: Improves maintainability and reduces drift, but the system already functions; this is a readability/consistency benefit layered on top of the P1 relocation.

**Independent Test**: Open `group_vars/services/vars.yml` and confirm a `# Service versions` block exists near the top containing all five service version pins (`nextcloud_version`, `nextcloud_exporter_version`, `adguard_exporter_version`, `immich_version`, `financial_scenario_version`).

**Acceptance Scenarios**:

1. **Given** `immich_version` and `financial_scenario_version` previously sat scattered in their own config sections, **When** the operator views the file, **Then** both appear within the new `# Service versions` block rather than in separate per-service sections.
2. **Given** the monitoring versions file uses a `# Service versions` heading, **When** the operator compares the two files, **Then** the services file uses the same heading style.

---

### Edge Cases

- A relocated version variable is deleted from a role default but accidentally not added to `group_vars` → the playbook fails fast with an undefined-variable error rather than silently using a stale default. This is the intended, desirable behavior: no role-level fallback masks a missing pin.
- Other consumers of the relocated variables (templates, healthcheck scripts, compose files) continue to resolve them because `group_vars` has higher precedence than role defaults and the variable names are unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All five service version pins (`nextcloud_version`, `nextcloud_exporter_version`, `adguard_exporter_version`, `immich_version`, `financial_scenario_version`) MUST reside in `ansible/group_vars/services/vars.yml` under a single labeled `# Service versions` block.
- **FR-002**: The `# Service versions` block MUST follow the same labeling style as the existing block in `ansible/group_vars/monitoring/vars.yml`.
- **FR-003**: `nextcloud_version` and `nextcloud_exporter_version` MUST be removed entirely from `ansible/roles/nextcloud/defaults/main.yml`, with no placeholder or commented-out remnant.
- **FR-004**: `adguard_exporter_version` MUST be removed entirely from `ansible/roles/adguard/defaults/main.yml`, with no placeholder or commented-out remnant.
- **FR-005**: The relocated `immich_version` and `financial_scenario_version` entries MUST keep their current values and be moved into the new block rather than duplicated.
- **FR-006**: Variable values MUST be preserved unchanged during relocation (`nextcloud_version: "32"`, `nextcloud_exporter_version: "0.9.0"`, `adguard_exporter_version: "1.2.1"`, `immich_version: "v2.4.0"`, `financial_scenario_version: "0.1.0"`).
- **FR-007**: Image registry paths, hardcoded floating compose tags, and digest-pinned images MUST NOT be moved or altered — they are explicitly out of scope.
- **FR-008**: After the change, no role `defaults/` file may need to be edited to perform a routine service version upgrade.

### Key Entities

- **Service version pin**: A name/value pair identifying the container image release a service is deployed at (e.g., `nextcloud_version: "32"`). Consumed by role tasks, compose templates, and healthchecks. Must have exactly one definition location.
- **Service variables file** (`group_vars/services/vars.yml`): The single intended home for all service version pins outside the monitoring stack.
- **Role defaults file** (`roles/<service>/defaults/main.yml`): Role-internal defaults; after this change holds no service version pins for the affected roles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A search for `nextcloud_version`, `nextcloud_exporter_version`, or `adguard_exporter_version` across `ansible/roles/` returns zero matches.
- **SC-002**: All five service version pins appear under the `# Service versions` block in `group_vars/services/vars.yml`.
- **SC-003**: Running the Nextcloud and AdGuard playbooks against a host completes with no undefined-variable errors attributable to the relocated variables.
- **SC-004**: An operator can locate and change any service version pin by opening at most one file (`group_vars/services/vars.yml` or `group_vars/monitoring/vars.yml`), with zero role `defaults/` edits required for a routine upgrade.

## Assumptions

- Variable names remain identical; only their definition location changes. All existing references (templates, scripts, compose files) continue to resolve via `group_vars` precedence over role defaults.
- The intended values are exactly those currently set in the source files as of 2026-06-20, which match the backlog document.
- No inventory host overrides these variables in a way that depends on the role-default fallback; removing the defaults is safe because `group_vars` will always supply a value.
- The `# Service versions` block is placed near the top of `group_vars/services/vars.yml`, mirroring the monitoring file layout.
