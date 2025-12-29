# Service Health Checks

This feature allows verifying the health of homelab services using a regression test suite that derives targets directly from the Ansible inventory.

## Usage

### CLI

Run the healthcheck script directly:

```bash
./scripts/healthcheck/run.sh
```

**Options:**
- `--profile <lan|tailscale>`: Select network profile (default: `lan`).
- `--filter <substring>`: Run checks only for hosts matching the substring.
- `--json`: Output JSON to stdout (in addition to saving to artifacts).

### Ansible

Run via Ansible playbook:

```bash
ansible-playbook ansible/playbooks/healthcheck.yml
```

To use the Tailscale profile:

```bash
ansible-playbook ansible/playbooks/healthcheck.yml -e "profile=tailscale"
```

## Configuration

Health checks are defined in Ansible inventory variables (e.g., `host_vars` or `group_vars`).

**Variables:**
- `healthcheck_path`: The URL path to check (e.g., `/api/health`). **Required** to enable checks for a host.
- `healthcheck_port`: The port to connect to (default: `80`).
- `healthcheck_scheme`: `http` or `https` (default: `http`).
- `healthcheck_verify_ssl`: `true` or `false` (default: `true`).
- `healthcheck_expect_status`: Expected HTTP status code (default: `200`).
- `healthcheck_expect_json`: JSON string to validate against the response body (subset match).

**Example (`ansible/host_vars/immich.yml`):**
```yaml
healthcheck_path: "/api/server/ping"
healthcheck_port: 2283
healthcheck_expect_json: '{"res":"pong"}'
```

## Artifacts

The latest run report is saved to `artifacts/healthcheck/latest.json`.
