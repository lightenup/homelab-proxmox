# Feature Specification: Service Health Regression Checks

**Feature Branch**: `018a-service-health-regression-checks`
**Created**: 2024-05-22
**Status**: Draft
**Input**: User description: "Create a new feature spec + plan + tasks... 018a-service-health-regression-checks... SSOT using Ansible inventory"

## User Scenarios & Testing

### User Story 1 - Run Full Regression Suite (Priority: P1)

As a System Administrator, I want to run a single command to verify the health of all my homelab services, so that I can quickly detect regressions after maintenance or updates.

**Why this priority**: This is the core value proposition—saving time and ensuring reliability.

**Independent Test**: Run the command against a healthy system and verify all checks pass. Stop a service (e.g., Immich) and verify the command fails and reports the specific service as down.

**Acceptance Scenarios**:

1. **Given** all services are running, **When** I run the healthcheck script, **Then** it returns exit code 0 and lists all services as "PASS".
2. **Given** Immich is stopped, **When** I run the healthcheck script, **Then** it returns exit code 1 and lists Immich as "FAIL".

### User Story 2 - Single Source of Truth (Priority: P1)

As a Maintainer, I want to define health checks alongside my service configuration in Ansible variables, so that the inventory is the single source of truth for both deployment and verification.

**Why this priority**: Prevents configuration drift and reduces maintenance burden (SSOT principle).

**Independent Test**: Add a `healthcheck` variable to a host in `hosts.yml` (or `group_vars`), run the tool, and verify it executes the check.

**Acceptance Scenarios**:

1. **Given** a service `immich` has `healthcheck_path: /api/server/ping` defined in inventory, **When** I run the tool, **Then** it executes a check against that path on the `immich` host.
2. **Given** I remove the `healthcheck_path` variable, **When** I run the tool, **Then** no check is executed for that host.

### User Story 3 - Profile Selection (Priority: P2)

As a Remote User, I want to run checks using Tailscale IPs instead of LAN IPs, so that I can verify connectivity from outside the network.

**Why this priority**: Supports remote management and verifies VPN configuration.

**Independent Test**: Run with `--profile tailscale` and verify it uses the Tailscale IP addresses.

**Acceptance Scenarios**:

1. **Given** I am on a remote network, **When** I run with `--profile tailscale`, **Then** the tool uses the `tailscale_ip` from the inventory.
2. **Given** I am on the LAN, **When** I run with `--profile lan` (default), **Then** the tool uses the `ansible_host` (LAN IP).

### Edge Cases

- **Inventory Missing**: If `hosts.yml` is missing or unreadable, the tool should fail with a clear error message.
- **Target Not Found**: If a check references a target `ghost_service` not in the inventory, the tool MUST log a warning, mark that specific check as SKIPPED/ERROR, and continue executing the remaining checks.
- **Service Timeout**: If a service hangs, the check should timeout (e.g., after 5s) rather than hanging indefinitely.

## Clarifications

### Session 2025-12-29
- Q: How should the system handle a check definition that references a target hostname not found in the inventory?
  - A: **Skip & Warn**: Log a warning, mark the check as "ERROR/SKIPPED", and continue running other checks.
- Q: Should the healthcheck tool support authenticated endpoints (e.g., requiring API tokens)?
  - A: **No (Unauthenticated Only)**: The tool will only support checks against public endpoints. No secret management required.
- Q: Where should the check definitions (paths, ports, expectations) be stored?
  - A: **Inventory Variables**: Define checks directly in Ansible `group_vars` or `host_vars` (e.g., `healthcheck_path: /api/ping`).
- Q: What language/tool should be used for the runner script?
  - A: **Python**: Use Python with `PyYAML` and `requests`. Best for parsing complex inventory data and handling logic.
- Q: What naming convention should be used for the Ansible variables defining the checks?
  - A: **Prefix (`healthcheck_`)**: Use `healthcheck_path`, `healthcheck_port`, `healthcheck_expect`. Clear namespacing.
- Q: How should the runner script access the inventory data (hosts and variables)?
  - A: **`ansible-inventory --list`**: Use the Ansible CLI to export the full resolved inventory as JSON. Most accurate.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST extract check definitions (path, port, expected status/body) directly from Ansible inventory variables using the `healthcheck_` prefix (e.g., `healthcheck_path`, `healthcheck_port`).
- **FR-002**: The system MUST resolve the inventory by executing `ansible-inventory --list` to ensure correct variable inheritance and group resolution.
- **FR-003**: The system MUST support HTTP/HTTPS checks with status code validation (default 200).
- **FR-004**: The system MUST support optional JSON body validation (e.g., `{"status": "ok"}`).
- **FR-005**: The system MUST provide a CLI interface with exit codes (0 for success, non-zero for failure).
- **FR-006**: The system MUST output a human-readable summary table to the console.
- **FR-007**: The system MUST optionally output a machine-readable JSON report.
- **FR-008**: The system MUST support "profiles" to select between LAN IPs and Tailscale IPs.
- **FR-009**: The system MUST NOT support authentication; all checks MUST target unauthenticated endpoints (e.g., `/health`, `/ping`).

### Key Entities

- **Check Definition**: Defines *what* to check (derived from `healthcheck_*` vars: Path, Port, Expectation).
- **Inventory Host**: Represents a server/service with attributes (Hostname, LAN IP, Tailscale IP).
- **Check Result**: The outcome of a single check (Pass/Fail, Response Time, Error Message).
