# Data Model: Service Metadata Schema

**Feature**: `018d-service-lifecycle`
**Context**: `host_vars` for hosts in the `services` group.

## Schema Definition

The following keys are **REQUIRED** for all services unless otherwise noted.

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `service_name` | String | Human-readable name of the service. | `"immich"` |
| `service_role` | Enum | Role of the service. Allowed: `app`, `infra`, `monitoring`, `proxy`. | `"app"` |
| `healthcheck_enabled` | Boolean | Whether to run healthchecks. | `true` |
| `healthcheck_profile` | Enum | Network profile. Allowed: `lan`, `tailscale`, `both`, `none`. Default: `lan`. | `"lan"` |
| `healthcheck_url` | Object | **Required** if profile != `none`. Connection details. | See below |
| `healthcheck_verification_command` | String | **Required** if profile == `none`. Shell command to verify status. | `"systemctl is-active worker"` |
| `healthcheck_expect_status` | Integer | Expected HTTP status code. Default: `200`. | `200` |
| `healthcheck_expect_body_contains` | String | Optional. Substring to search for in response body. | `"System OK"` |
| `healthcheck_reason` | String | **Required** if `healthcheck_enabled` is `false`. Reason for skipping. | `"Maintenance"` |
| `expose_via_proxy` | Boolean | Optional. Whether this service is exposed via the reverse proxy. | `true` |
| `proxy_hostname` | String | Optional. FQDN for the proxy. | `"immich.homelab.local"` |
| `service_data_paths` | List[String] | Optional. Important data paths for backup/restore. | `["/mnt/data"]` |
| `service_owner` | String | Optional. Owner/Operator. | `"admin"` |

### `healthcheck_url` Object

| Key | Type | Description | Example |
|-----|------|-------------|---------|
| `scheme` | Enum | `http` or `https`. | `"http"` |
| `port` | Integer | Port number. | `2283` |
| `path` | String | URL path. | `"/api/server-info/ping"` |

## Validation Rules

1. **Strict Keys**: Any key in `host_vars` NOT listed above (or standard Ansible keys like `ansible_host`) will trigger a **Drift Warning**.
2. **Profile Logic**:
   - If `profile` is `none`, `healthcheck_url` is forbidden/ignored, `verification_command` is required.
   - If `profile` is `lan`/`tailscale`, `healthcheck_url` is required.
3. **Disabled Logic**:
   - If `healthcheck_enabled` is `false`, `healthcheck_reason` is mandatory.

## Example JSON Representation

```json
{
  "service_name": "immich",
  "service_role": "app",
  "healthcheck_enabled": true,
  "healthcheck_profile": "lan",
  "healthcheck_url": {
    "scheme": "http",
    "port": 2283,
    "path": "/api/server-info/ping"
  },
  "expose_via_proxy": true,
  "proxy_hostname": "immich.local"
}
```
