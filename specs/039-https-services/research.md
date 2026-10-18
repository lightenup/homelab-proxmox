# Research: HTTPS for All Homelab Services

**Feature**: 039-https-services
**Date**: 2026-02-28

## Implementation Note (2026-03-01)

R-001 selected `caddy-dns/lego-deprecated` as the DNS provider module. During deployment, this module was found to be incompatible with Caddy v2.11.1 (panics with `missing method AppendRecords` — the lego interface is no longer supported by current Caddy). The module was replaced with `caddy-dns/domainnameshop`, a native libdns-based provider for Domeneshop (international brand: Domainname.shop). This module uses the same API credentials (`DOMENESHOP_API_TOKEN`, `DOMENESHOP_API_SECRET`) and supports both global `acme_dns` and per-site `tls` directives. The Caddyfile uses `acme_dns domainnameshop {$DOMENESHOP_API_TOKEN} {$DOMENESHOP_API_SECRET}` in the global options block.

---

## R-001: Caddy DNS Provider for Domeneshop

### Context

FR-012 requires replacing the stock Caddy binary with a custom build including the Domeneshop DNS provider module. FR-002 requires DNS-01 challenges via the Domeneshop API. The question is: which Caddy-compatible DNS module supports Domeneshop?

### Findings

1. **No native `caddy-dns/domeneshop` module exists.** The caddy-dns GitHub organization has modules for ~30 providers (Cloudflare, Hetzner, Namecheap, etc.) but not Domeneshop.
2. **No `libdns/domeneshop` module exists.** The libdns project (the modern Caddy DNS provider interface) has no Domeneshop implementation.
3. **`caddy-dns/lego-deprecated` supports Domeneshop** via the `go-acme/lego` library, which has a native `domeneshop` DNS provider. However, this module was archived on 2024-06-04 and is deprecated. It wraps the older lego API that Caddy is moving away from.
4. **`go-acme/lego` CLI** has native Domeneshop support (`DOMENESHOP_API_TOKEN`, `DOMENESHOP_API_SECRET` env vars). This can obtain certificates independently of Caddy.

### Decision

**Use `caddy-dns/lego-deprecated` via xcaddy build.** Despite the deprecation, this module still compiles and functions correctly with current Caddy versions. It is the only zero-development-effort path to get Caddy to natively manage DNS-01 challenges with Domeneshop.

### Rationale

- Writing a new `libdns/domeneshop` provider requires Go development (implementing `GetRecords`, `AppendRecords`, `SetRecords`, `DeleteRecords` against the Domeneshop REST API). This is substantial work outside the scope of an IaC feature.
- Using an external ACME client (lego CLI / certbot) + Caddy loading external certs contradicts the spec's intent (FR-002, FR-003, FR-012) and adds operational complexity (cron jobs, certificate file management, reload triggers).
- The lego-deprecated module is frozen, not broken. It compiles with Go and the lego v4.9.1 dependency tree. The deprecation refers to the project's maintenance status, not its functionality.
- **Migration path**: When a `libdns/domeneshop` module becomes available (community or self-authored), the Caddyfile syntax changes from `dns lego_deprecated domeneshop` to `dns domeneshop { ... }`. The xcaddy build switches the `--with` flag. All other infrastructure (systemd, Ansible, vault) remains identical.

### Alternatives Considered

| Alternative | Rejected Because |
|---|---|
| Write `libdns/domeneshop` in Go | Out of scope for IaC project; requires Go toolchain, testing, and ongoing maintenance |
| External lego CLI + cron + Caddy `tls load` | Adds operational complexity; does not meet FR-012 (module built into Caddy); breaks automatic renewal model |
| Use certbot-dns-domeneshop | Python dependency; incompatible with Caddy's native cert management; adds cron/reload complexity |
| Switch to a registrar with a native caddy-dns module (e.g., Cloudflare) | Domain already purchased at Domeneshop (A-001); unnecessary cost and migration |

---

## R-002: Custom Caddy Binary Build Strategy

### Context

FR-012 requires replacing the APT-installed stock Caddy with a custom build. Decision D-005 mandates xcaddy or equivalent. How should the build be performed and managed by Ansible?

### Findings

1. **xcaddy** is the official Caddy project tool for building custom binaries. It requires Go 1.22+.
2. The standard approach for Debian/Ubuntu systems:
   - Install Go and xcaddy on the build host (or the target LXC)
   - Run `xcaddy build --with github.com/caddy-dns/lego-deprecated`
   - Replace `/usr/bin/caddy` with the custom binary
   - The APT-installed Caddy's systemd unit file, user, group, and data directories remain valid
3. **Alternative: cross-compile on CI or developer machine** and deploy the binary via Ansible `copy`. This avoids installing Go on the proxy LXC but requires a build step outside Ansible.
4. **`dpkg-divert`** can be used to prevent APT from overwriting the custom binary on future updates.

### Decision

**Build on the reverse proxy LXC using Ansible tasks.** Install Go and xcaddy as build dependencies, build the binary in a versioned/tagged manner, replace `/usr/bin/caddy`, and use `dpkg-divert` to protect it from APT overwrites.

### Rationale

- Building on the target LXC ensures architecture match (amd64/arm64) without cross-compilation
- Ansible manages the entire lifecycle: install deps → build → replace → verify
- Dual-provisioning parity: same Ansible role works from CI and laptop (constitution IV)
- dpkg-divert is the Debian-standard mechanism for custom binary management

---

## R-003: Secrets Injection for Caddy Domeneshop Credentials

### Context

FR-013 and US-5 require Domeneshop API credentials (token + secret) stored in Ansible vault, injected at runtime. Decision D-006 specifies systemd environment file or override. How should this be implemented?

### Findings

1. **systemd `EnvironmentFile=`** is the standard approach. Create a file (e.g., `/etc/caddy/domeneshop.env`) containing `DOMENESHOP_API_TOKEN=xxx` and `DOMENESHOP_API_SECRET=yyy`. Reference it via a systemd override.
2. **systemd override** can be created at `/etc/systemd/system/caddy.service.d/domeneshop.conf` with `[Service]` section containing `EnvironmentFile=/etc/caddy/domeneshop.env`.
3. The lego-deprecated module reads credentials from environment variables `DOMENESHOP_API_TOKEN` and `DOMENESHOP_API_SECRET` at runtime.
4. **File permissions**: The env file must be owned by `root:root` with mode `0600` (or `root:caddy` with `0640`) to prevent other users from reading the secrets.

### Decision

**Use a systemd override with an EnvironmentFile.** The Ansible role will:
1. Template `/etc/caddy/domeneshop.env` from vault variables with mode `0600`
2. Template `/etc/systemd/system/caddy.service.d/domeneshop.conf` as a systemd drop-in override
3. Trigger `systemctl daemon-reload` and Caddy restart on changes

### Rationale

- Secrets never appear in Caddyfile templates (satisfies FR-013, US-5)
- systemd drop-in overrides are the idiomatic way to extend APT-managed service units without editing the original file
- The env file is not committed to the repo; it is generated on the target from vault at deploy time
- File permissions restrict access to root only

---

## R-005: Nextcloud Domain Migration

### Context

FR-007 and FR-008 require reconfiguring Nextcloud with the new domain (`nextcloud.hus-sky.no`) and HTTPS protocol, while temporarily trusting both old and new domains. How does this work with the existing Docker-based Nextcloud setup?

### Findings

1. **Current Nextcloud config** (from `ansible/roles/nextcloud/templates/.env.j2`):
   - `NEXTCLOUD_TRUSTED_DOMAINS={{ nextcloud_domain }} {{ nextcloud_ip }}`
   - `OVERWRITEPROTOCOL=http`
   - `OVERWRITECLIURL=http://{{ nextcloud_domain }}`
   - `TRUSTED_PROXIES={{ reverse_proxy_ip }}`
   - Default `nextcloud_domain` is `nextcloud.local`
2. **Migration requires**:
   - Change `nextcloud_domain` to `nextcloud.hus-sky.no`
   - Change `OVERWRITEPROTOCOL` to `https`
   - Change `OVERWRITECLIURL` to `https://nextcloud.hus-sky.no`
   - Add both `nextcloud.local` and `nextcloud.hus-sky.no` to `NEXTCLOUD_TRUSTED_DOMAINS`
3. **Nextcloud occ commands** may also be needed to update `trusted_domains` array in the PHP config if the Docker env vars don't cover all scenarios.

### Decision

**Modify the existing Nextcloud role variables and .env template.** Introduce a `nextcloud_trusted_domains_extra` list variable for backward compatibility. Update `OVERWRITEPROTOCOL` and `OVERWRITECLIURL` to match the new HTTPS domain. The existing `.env.j2` template will be updated to include both domains.

### Rationale

- Minimal changes to existing Ansible structure
- The env var approach is already in place; only values change
- D-004 says both domains remain trusted indefinitely — no automatic removal needed

---

## R-006: Grafana Domain Migration

### Context

FR-009 requires reconfiguring Grafana with its new root URL. How does this work with the existing Docker Compose monitoring stack?

### Findings

1. **Current Grafana config** (from `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2`):
   - `GF_SERVER_DOMAIN={{ grafana_domain }}` (default: `monitoring.local`)
   - `GF_SERVER_ROOT_URL=http://{{ grafana_domain }}:{{ grafana_port }}` (default: `http://monitoring.local:3000`)
2. **Migration requires**:
   - Change `grafana_domain` to `grafana.hus-sky.no`
   - Change `GF_SERVER_ROOT_URL` to `https://grafana.hus-sky.no` (no port, since proxy handles 443)

### Decision

**Update `grafana_domain` variable and modify the docker-compose template's `GF_SERVER_ROOT_URL`.** The URL template should use a new `grafana_protocol` variable (defaulting to `https`) and omit the port when behind a proxy.

### Rationale

- Minimal changes to existing role
- The Grafana container still listens on port 3000 internally; only the external-facing URL changes
- The monitoring role's docker-compose template already uses variables for these settings

---

## R-007: Certificate Type — Individual vs Wildcard

### Context

D-007 says to default to individual certificates unless wildcard is simpler. With the lego-deprecated module, which approach works best?

### Findings

1. **Individual certificates**: Each site block in the Caddyfile (e.g., `nextcloud.hus-sky.no`, `immich.hus-sky.no`) automatically gets its own certificate when a DNS provider is configured. This is Caddy's default behavior.
2. **Wildcard certificates**: Require a site block with `*.hus-sky.no` or explicit configuration via the `tls` directive. Caddy can request a wildcard cert from Let's Encrypt using DNS-01.
3. **With lego-deprecated**: Both approaches work. The DNS provider is configured globally or per-site. Individual certs are simpler to configure and are the Caddy default.
4. **Let's Encrypt rate limits**: Individual certs are subject to 50 certificates per registered domain per week. With 5-6 subdomains, this is not a concern. Wildcard counts as 1 certificate.

### Decision

**Use individual certificates per subdomain (Caddy default).** Each named site block automatically gets its own cert via the globally configured DNS provider.

### Rationale

- Simpler configuration — no explicit wildcard setup needed
- Caddy's default behavior when site blocks use FQDNs with a DNS provider configured
- Rate limits are not a concern with 5-6 subdomains
- Debugging is easier — each cert can be inspected independently

---

## R-008: Caddy Global TLS Configuration with lego-deprecated

### Context

How should the Caddyfile be structured to use lego-deprecated for DNS-01 challenges globally?

### Findings

1. **Global ACME DNS configuration** in Caddyfile:
   ```
   {
       acme_dns lego_deprecated domeneshop
   }
   ```
   This tells Caddy to use the lego_deprecated module with the `domeneshop` provider for all sites that need ACME certificates.
2. **Per-site alternative**:
   ```
   nextcloud.hus-sky.no {
       tls {
           dns lego_deprecated domeneshop
       }
       reverse_proxy ...
   }
   ```
3. **Removing `auto_https off`**: The current Caddyfile has `auto_https off` globally. This MUST be removed (FR-011) to enable Caddy's automatic HTTPS.
4. **The `import` directive** continues to work — individual site configs in `conf.d/` are imported by the main Caddyfile.

### Decision

**Use the global `acme_dns` directive in the main Caddyfile.** This applies DNS-01 challenges to all sites without per-site configuration. Remove `auto_https off`.

### Rationale

- DRY — avoids repeating DNS provider config in every site block
- All sites use the same domain and DNS provider
- Cleaner separation: global TLS config in Caddyfile, per-site routing in conf.d/
