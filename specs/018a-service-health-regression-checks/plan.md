# Implementation Plan: Service Health Regression Checks

**Feature**: 018a-service-health-regression-checks
**Status**: Draft

## Approach Selection: Option A (Inventory-Driven Checks)

We will implement **Option A** as requested. This approach minimizes maintenance by deriving target IPs directly from the Ansible inventory at runtime.

### Why Option A?
- **SSOT**: The Ansible inventory (`ansible/inventories/generated/hosts.yml`) is the definitive source for hostnames and IPs.
- **Maintenance**: Adding a service in Terraform/Ansible automatically makes it available to the healthcheck runner without updating a separate registry.
- **Flexibility**: We can define checks against groups (e.g., `monitoring`) and the runner will expand them to all hosts in that group.

## Architecture

### 1. Configuration (Ansible Variables)
Checks are defined directly in Ansible variables (`group_vars` or `host_vars`) using the `healthcheck_` prefix.
```yaml
# group_vars/immich.yml
healthcheck_path: "/api/server/ping"
healthcheck_port: 2283
healthcheck_expect_json: '{"res":"pong"}'
```

### 2. Runner Script (`scripts/healthcheck/healthcheck.py`)
A Python script that:
1.  Parses arguments (`--profile`, `--json`, `--filter`).
2.  Executes `ansible-inventory --list` to get the full resolved inventory JSON.
3.  Iterates through all hosts in the inventory.
4.  Filters for hosts that have `healthcheck_path` defined.
5.  Resolves the target IP based on the profile (`ansible_host` for LAN, `tailscale_ip` for Tailscale).
6.  Executes HTTP requests in parallel (using `concurrent.futures`).
7.  Outputs results to stdout (table) and JSON.

### 3. Ansible Wrapper (`ansible/playbooks/healthcheck.yml`)
A simple playbook that executes the script on `localhost`. This ensures the healthcheck can be run via `ansible-playbook` for consistency with other ops tasks.

## Execution Flow

1.  **User** runs `./scripts/healthcheck/run.sh --profile lan`.
2.  **Runner** calls `ansible-inventory --list`.
3.  **Runner** parses JSON to find hosts with `healthcheck_path`.
4.  **Runner** resolves IPs:
    *   LAN: Uses `ansible_host`.
    *   Tailscale: Uses `tailscale_ip` (if present).
5.  **Runner** performs checks.
6.  **Runner** prints summary table.
