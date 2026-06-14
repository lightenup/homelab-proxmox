# Contract: `caddy_services` shared variable

**Location**: `ansible/group_vars/services/vars.yml`
**Consumers**: `reverse_proxy` role (routes + landing page), `monitoring_stack` role (blackbox targets)
**Scope note**: The `monitoring` host is a member of the `services` inventory group, so this var is in
scope for the monitoring play without any `group_vars/all` placement.

## Shape

```yaml
caddy_services:
  - host: immich            # required: subdomain label (→ immich.hus-sky.no)
    ip: "{{ immich_ip }}"   # required (when enabled): backend host — reference the existing
    port: "{{ immich_port }}" # required (when enabled): backend port  central var, do NOT duplicate
    title: "Immich"         # optional: card heading (default: host, capitalized)
    desc: "Photos"          # optional: card description (default: "")
    enabled: true           # optional: default true
    user_facing: true       # optional: default true
```

> **IP/port form**: each entry references the existing central backend vars (`{{ immich_ip }}`,
> `{{ immich_port }}`, etc.) rather than hard-coding an address. This keeps IP strings defined in
> exactly one place (constitution Networking rule — "avoid scattering IP strings") so `caddy_services`
> owns *which services exist + their metadata*, while the `*_ip`/`*_port` vars remain the single IP source.

## Field rules

| Field | Required | Default | Constraint |
|-------|----------|---------|------------|
| `host` | yes | — | unique across the list; DNS-label-safe |
| `ip` | yes if `enabled` | — | IPv4 of the backend LXC, **as a Jinja ref** to the central var (`"{{ <svc>_ip }}"`) |
| `port` | yes if `enabled` | — | 1–65535, **as a Jinja ref** to the central var (`"{{ <svc>_port }}"`) |
| `title` | no | `host \| capitalize` | display only |
| `desc` | no | `""` | display only |
| `enabled` | no | `true` | gates route + probe + card |
| `user_facing` | no | `true` | gates probe + card (not route) |

## Behavioural contract (acceptance-testable)

1. Adding one entry (enabled, user_facing) and deploying creates — with no other edit — a Caddy
   route, a blackbox target, and a landing card. Removing it removes all three. *(SC-003)*
2. `enabled: false` ⇒ entry absent from route, target, and card. *(SC-003, FR-006)*
3. `user_facing: false` ⇒ entry absent from target and card; route may persist if `enabled`.
4. Missing `title`/`desc` ⇒ card renders with host fallback; deploy does not fail. *(edge case)*
5. After migration, this is the ONLY hand-maintained subdomain list: no literal
   `blackbox_https_targets`, no per-service `.caddy.j2` templates remain. *(SC-004)*

## Initial population (reproduces today's active routes/probes)

| host | ip (ref) | port (ref) | enabled | user_facing | source today |
|------|----------|------------|---------|-------------|--------------|
| grafana | `{{ monitoring_ip }}` | `{{ grafana_port }}` | true | true | grafana.caddy.j2 + blackbox target |
| immich | `{{ immich_ip }}` | `{{ immich_port }}` | true | true | immich.caddy.j2 + blackbox target |
| nextcloud | `{{ nextcloud_ip }}` | `{{ nextcloud_port }}` | true | true | nextcloud.caddy.j2 + blackbox target |
| jellyfin | `{{ jellyfin_ip }}` | `{{ jellyfin_port }}` | true | true | jellyfin.caddy.j2 + blackbox target |
| adguard | `{{ adguard_ip }}` | `{{ adguard_web_port }}` | **false** | true | adguard.caddy.j2 (see note) |
| ha | `{{ homeassistant_ip }}` | `{{ homeassistant_port }}` | **false** | true | homeassistant.caddy.j2 guarded by `homeassistant_active: false` |

> **grafana** has no `grafana_ip` var — it uses `monitoring_ip` (the Grafana container runs on the
> monitoring LXC). The entry references `{{ monitoring_ip }}`/`{{ grafana_port }}`, the existing vars.
>
> **adguard** is `enabled: false` because AdGuard is **not in use at all** (LXC pending candidate #8,
> blackbox target already commented out). Note that today's `adguard.caddy.j2` renders
> **unconditionally**, so a live `adguard.hus-sky.no` route currently points at an unused backend.
> Setting the entry to `enabled: false` **intentionally removes that dangling route** — this is a
> correct cleanup, NOT a parity regression against the T001 baseline. The disabled entry is retained
> (not deleted) so candidate #8 can re-enable it with a one-line flag flip.
>
> **ha** is `enabled: false`, matching today (its template is already guarded off via
> `homeassistant_active: false`) — no route today, no route after. True parity.
