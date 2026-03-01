# Feature Specification: HTTPS for All Homelab Services

**Feature Branch**: `039-https-services`
**Created**: 2026-02-28
**Status**: Draft
**Input**: User description: "Implement https on services"

## User Scenarios & Testing

### User Story 1 - Mobile App Connectivity via HTTPS (Priority: P1)

As a homelab user, I want to connect the Nextcloud and Immich mobile apps to my services over HTTPS, so that the apps function correctly (both require HTTPS) and my photo sync and file access work from my phone.

**Why this priority**: This is the primary driver for the entire feature. Without HTTPS, the Nextcloud and Immich mobile apps refuse to connect, making the services effectively unusable from mobile devices.

**Independent Test**: Can be fully tested by installing/opening the Nextcloud mobile app, entering `https://nextcloud.hus-sky.no` as the server address, logging in, and verifying file sync works. Repeat for Immich at `https://immich.hus-sky.no` and verify photo backup functions.

**Acceptance Scenarios**:

1. **Given** the Nextcloud mobile app is installed on a phone connected to the LAN (or via Tailscale), **When** the user enters `https://nextcloud.hus-sky.no` as the server URL and logs in, **Then** the app connects successfully, displays files, and can upload/download content.
2. **Given** the Immich mobile app is installed on a phone connected to the LAN (or via Tailscale), **When** the user configures the server as `https://immich.hus-sky.no`, **Then** the app connects, displays the photo library, and automatic photo backup functions correctly.
3. **Given** a mobile device connected via Tailscale (remote, not on LAN), **When** the user accesses either service via its `hus-sky.no` subdomain, **Then** the connection is encrypted end-to-end and the app functions identically to LAN access.

---

### User Story 2 - Browser-Trusted Access to All Services (Priority: P2)

As a homelab user, I want all web-accessible services to present valid, browser-trusted certificates when accessed via their `hus-sky.no` subdomains, so that I no longer see browser security warnings and my login credentials are transmitted securely.

**Why this priority**: Browser warnings on HTTP sites erode trust and usability, especially for services handling credentials (Grafana, Nextcloud, AdGuard). While not blocking like mobile apps, this significantly improves daily usage experience.

**Independent Test**: Open each service URL (`https://nextcloud.hus-sky.no`, `https://immich.hus-sky.no`, `https://grafana.hus-sky.no`, `https://jellyfin.hus-sky.no`, `https://adguard.hus-sky.no`) in a browser on the LAN. Verify the padlock icon appears, the certificate is issued by Let's Encrypt, and no security warnings are shown.

**Acceptance Scenarios**:

1. **Given** a browser on the LAN, **When** a user navigates to `https://nextcloud.hus-sky.no`, **Then** the browser displays a padlock icon with a valid Let's Encrypt certificate and no security warnings.
2. **Given** a browser on the LAN, **When** a user navigates to `https://immich.hus-sky.no`, **Then** the browser displays a padlock icon with a valid Let's Encrypt certificate and no security warnings.
3. **Given** a browser on the LAN, **When** a user navigates to `https://grafana.hus-sky.no`, **Then** the browser displays a padlock icon with a valid Let's Encrypt certificate, and Grafana login and dashboards function correctly.
4. **Given** a browser on the LAN, **When** a user navigates to `https://jellyfin.hus-sky.no`, **Then** the browser displays a padlock icon with a valid Let's Encrypt certificate, and media playback works.
5. **Given** a browser on the LAN, **When** a user navigates to `https://adguard.hus-sky.no`, **Then** the browser displays a padlock icon with a valid Let's Encrypt certificate, and the AdGuard admin dashboard functions correctly.

---

### User Story 3 - Automatic Certificate Lifecycle (Priority: P2)

As a homelab operator, I want certificates to be issued and renewed automatically without any manual intervention, so that services never go down due to an expired certificate.

**Why this priority**: Manual certificate management would be unsustainable. A single missed renewal would break mobile app access (P1). Automation is essential for the feature to be viable long-term.

**Independent Test**: After initial deployment, verify certificates are issued. Wait for (or simulate) a renewal cycle and confirm certificates are renewed without manual steps. Check that certificate expiration dates are at least 60 days in the future after issuance.

**Acceptance Scenarios**:

1. **Given** the reverse proxy is deployed with the Domeneshop DNS provider configured, **When** the proxy starts for the first time, **Then** valid Let's Encrypt certificates are automatically obtained for all configured subdomains within 5 minutes.
2. **Given** certificates are currently valid, **When** they approach their renewal window (30 days before expiry, per Let's Encrypt default), **Then** renewal happens automatically without operator action and without service downtime.
3. **Given** a certificate renewal occurs, **When** a user accesses a service immediately after renewal, **Then** the new certificate is served without any interruption or error.

---

### User Story 4 - Graceful Migration from HTTP to HTTPS (Priority: P3)

As a homelab operator, I want the migration from `.local` HTTP to `hus-sky.no` HTTPS to preserve all existing service data, users, and settings, so that I don't lose any content during the transition.

**Why this priority**: Data preservation is critical, but this is primarily a deployment concern. The rollout can be carefully sequenced to mitigate risk, making it less urgent than getting the core HTTPS functionality working.

**Independent Test**: Before migration, document current state (Nextcloud user accounts and files, Immich photo count, Grafana dashboards). After migration, verify all data is intact and accessible via the new URLs.

**Acceptance Scenarios**:

1. **Given** Nextcloud is running at `http://nextcloud.local` with existing users and files, **When** the operator migrates to `https://nextcloud.hus-sky.no`, **Then** all user accounts, files, and settings are preserved and accessible via the new URL.
2. **Given** Immich is running with an existing photo library, **When** the operator migrates to `https://immich.hus-sky.no`, **Then** all photos, albums, and user accounts are preserved.
3. **Given** Nextcloud is being migrated, **When** the new HTTPS domain is configured, **Then** Nextcloud temporarily trusts both `nextcloud.local` and `nextcloud.hus-sky.no` domains to allow a grace period for clients to switch over.
4. **Given** Grafana is accessed directly at `http://monitoring.local:3000` with existing dashboards, **When** it is placed behind the proxy at `https://grafana.hus-sky.no`, **Then** all dashboards, data sources, and user accounts are preserved.

---

### User Story 5 - Secrets Security (Priority: P1)

As a homelab operator, I want all API credentials required for certificate issuance to be stored securely in Ansible vault and never exposed in the repository, so that my domain registrar account is not compromised.

**Why this priority**: This is a non-negotiable security requirement aligned with the constitution's secrets policy. Leaking the Domeneshop API credentials could allow an attacker to modify DNS records for the domain.

**Independent Test**: Search the entire repository (including git history of the new changes) for the Domeneshop API token and secret values. Confirm they appear nowhere except in vault-encrypted files.

**Acceptance Scenarios**:

1. **Given** the Domeneshop API token and secret are needed for DNS-01 challenges, **When** the operator stores them in Ansible vault, **Then** they are encrypted at rest and never appear in plaintext in any committed file.
2. **Given** a deployment runs via CI/CD or from a developer laptop, **When** the reverse proxy role executes, **Then** the API credentials are injected into the Caddy process at runtime from vault without being written to unencrypted files on the proxy LXC filesystem.
3. **Given** the repository is cloned by a new contributor, **When** they inspect all files, templates, and playbooks, **Then** no real API credential values are visible — only references to vault-sourced variables.

---

### Edge Cases

- What happens when Domeneshop API is temporarily unreachable during a certificate renewal? The reverse proxy must continue serving existing valid certificates while retrying renewal. Services must not go down.
- What happens when a user bookmarks the old `http://nextcloud.local` URL? The old `.local` hostname will stop resolving to the proxy once mDNS or AdGuard rewrites are updated. Users must be informed to update bookmarks. During the grace period, Nextcloud should trust both domains.
- What happens when AdGuard (the DNS server) itself is being accessed via a subdomain that relies on DNS resolution? LAN clients need an alternative DNS path (e.g., the public DNS record) or the AdGuard rewrite must be configured before AdGuard is placed behind the proxy.
- What happens when a new service is added in the future? The pattern for adding a new HTTPS-proxied service must be documented and repeatable (new Caddy site block template, AdGuard rewrite, optional DNS record).
- What happens if the Domeneshop API credentials are rotated? The operator must update the Ansible vault and re-run the reverse proxy deployment. Certificate renewal must resume automatically.
- What happens when a Tailscale client tries to resolve a `hus-sky.no` subdomain? Public DNS resolvers return the private LAN IP (`192.168.1.211`) from the registrar's A record. Tailscale's subnet route (`192.168.1.0/24`) makes this IP reachable. No special DNS configuration is needed on Tailscale clients — standard public DNS resolution works because the A record is publicly visible even though the IP is private.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST serve all listed services (Nextcloud, Immich, Grafana, Jellyfin, AdGuard) via HTTPS at their respective `<service>.hus-sky.no` subdomains. *(traces to US-1, US-2)*
- **FR-002**: The system MUST obtain TLS certificates automatically from Let's Encrypt using DNS-01 challenges via the Domeneshop API. *(traces to US-3)*
- **FR-003**: The system MUST renew certificates automatically before expiry without operator intervention. *(traces to US-3)*
- **FR-004**: The reverse proxy MUST terminate TLS for all services; individual service backends continue to serve HTTP internally. *(traces to US-1, US-2)*
- **FR-005**: DNS records (wildcard or per-subdomain) at the registrar MUST point to the reverse proxy LXC IP (`192.168.1.211`). *(traces to US-1, US-2)*
- **FR-006**: AdGuard MUST be configured with DNS rewrites for all service subdomains to resolve to the reverse proxy LXC IP (`192.168.1.211`) on the LAN, enabling split-horizon DNS. *(traces to US-1, US-2)*
- **FR-007**: Nextcloud MUST be reconfigured with the new domain (`nextcloud.hus-sky.no`) and HTTPS protocol in its trusted domains list, protocol override, and environment variables. *(traces to US-1, US-4)*
- **FR-008**: Nextcloud MUST temporarily trust both `nextcloud.local` and `nextcloud.hus-sky.no` domains during the migration period to allow clients to transition gracefully. *(traces to US-4)*
- **FR-009**: Grafana MUST be reconfigured with its new root URL (`https://grafana.hus-sky.no`) so that redirects and generated links work correctly. *(traces to US-2, US-4)*
- **FR-010**: New Caddy site blocks MUST be added for Grafana, Jellyfin, and AdGuard (services not currently behind the proxy). *(traces to US-2)*
- **FR-011**: The existing Caddy `auto_https off` global setting MUST be removed to enable automatic HTTPS. *(traces to US-1, US-2, US-3)*
- **FR-012**: The stock Caddy binary MUST be replaced with a custom build that includes the Domeneshop DNS provider module. *(traces to US-3)*
- **FR-013**: Domeneshop API credentials (token and secret) MUST be stored exclusively in Ansible vault and injected into the Caddy runtime environment securely. *(traces to US-5)*
- **FR-014**: All changes MUST be deployable from both CI/CD (GitHub Actions) and a developer laptop (dual-provisioning parity). *(traces to US-4, US-5)*
- **FR-015**: A Home Assistant Caddy site block (`ha.hus-sky.no`) MUST be included in the design for future-proofing, but MAY be inactive if the service is not yet deployed. *(traces to US-2)*
- **FR-016**: Existing service data, user accounts, and settings MUST be preserved through the migration. *(traces to US-4)*

### Key Entities

- **Service Subdomain Mapping**: Associates each service with its public subdomain (`<service>.hus-sky.no`), backend IP, and backend port. Defines the routing configuration for the reverse proxy.
- **TLS Certificate**: Represents a Let's Encrypt certificate bound to one or more `hus-sky.no` subdomains. Has issuance date, expiry date, and renewal state. Managed automatically by the reverse proxy.
- **DNS Rewrite Rule**: An AdGuard DNS rewrite entry mapping a `hus-sky.no` subdomain to the reverse proxy LAN IP. Required for split-horizon DNS so LAN clients resolve subdomains locally.
- **Registrar DNS Record**: A DNS A record (or wildcard) at Domeneshop pointing `*.hus-sky.no` (or individual subdomains) to the reverse proxy LAN IP. Required for routing client traffic (LAN and Tailscale) to the proxy. Note: DNS-01 validation uses TXT records created via the Domeneshop API, not A records — the A record is purely for traffic routing.
- **Vault Secret**: An encrypted Ansible vault entry holding the Domeneshop API token and secret. Never stored in plaintext. Injected at deployment time.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All five listed services (Nextcloud, Immich, Grafana, Jellyfin, AdGuard) are accessible via `https://<service>.hus-sky.no` from a browser on the LAN, each presenting a valid Let's Encrypt certificate with no security warnings.
- **SC-002**: The Nextcloud mobile app connects to `https://nextcloud.hus-sky.no`, authenticates, and completes a file sync operation (upload and download) successfully.
- **SC-003**: The Immich mobile app connects to `https://immich.hus-sky.no`, authenticates, and completes a photo backup successfully.
- **SC-004**: Certificate renewal occurs automatically. Within 90 days of initial deployment, at least one renewal cycle completes without manual intervention (verifiable via certificate issuance date or proxy logs).
- **SC-005**: A repository-wide search for Domeneshop API credential values returns zero matches outside of vault-encrypted files.
- **SC-006**: All existing Nextcloud user accounts and files are accessible after migration. All existing Immich photos and albums are accessible after migration. All Grafana dashboards remain intact after migration.
- **SC-007**: The deployment can be executed successfully from both a GitHub Actions CI/CD run and from a developer laptop using the same Ansible playbooks and roles.

## Assumptions

- **A-001**: The domain `hus-sky.no` has been purchased and is active at Domeneshop.
- **A-002**: Domeneshop API credentials (token + secret) can be generated via the registrar web UI and are available for the operator to enter into Ansible vault.
- **A-003**: Domeneshop DNS records (registrar-side, either wildcard or per-subdomain A records) are created manually as a one-time out-of-band step, since the registrar web UI is the appropriate tool for this.
- **A-004**: The reverse proxy LXC (`192.168.1.211`) already exists and is managed by Terraform/Ansible. No new LXC provisioning is needed.
- **A-005**: AdGuard is running on `192.168.1.210` and is the LAN DNS server. It supports DNS rewrite configuration via its Ansible-managed setup or its web UI.
- **A-006**: The Domeneshop DNS API supports the DNS-01 ACME challenge flow required by Let's Encrypt and Caddy.
- **A-007**: All service backend IPs and ports remain unchanged; only the proxy and DNS layers change. Current backends: Nextcloud (`192.168.1.216:8080`), Immich (`192.168.1.213:2283`), Grafana/Monitoring (`192.168.1.214:3000`), Jellyfin (`192.168.1.215:8096`), AdGuard (`192.168.1.210`, web UI port to be confirmed during planning — not currently defined in Ansible vars).
- **A-008**: Terraform owns no changes in this feature — all work is Ansible-only (per the constitution's separation of concerns).
- **A-009**: The Home Assistant service is not yet deployed. Its Caddy site block is included as a placeholder for future activation.
- **A-010**: The `hus-sky.no` domain's public A records will point to a private LAN IP (`192.168.1.211`). Public DNS resolvers will serve these records normally (they are valid DNS entries), but the IP is only routable from the LAN or via Tailscale's subnet route (`192.168.1.0/24`). This is acceptable since services are LAN + Tailscale only and are not intended for public internet access.

## Out of Scope

- **Proxmox UI HTTPS** — Proxmox has its own self-signed certificate on port 8006 and is accessed only by administrators via Tailscale. Different access pattern, not user-facing.
- **Public internet exposure** — No router port forwarding, no Cloudflare tunnels, no external access. Services remain LAN + Tailscale only.
- **Email/MX records** — The Domeneshop DNS tier includes no email services; email configuration is not relevant.
- **VLAN migration** — Network segmentation is a separate future initiative documented in `docs/network-layout.md`. HTTPS works independently of VLAN topology.
- **Tailscale MagicDNS integration** — A desirable future enhancement but orthogonal to the core HTTPS/domain setup. Can be layered on later.
- **HTTP-to-HTTPS redirect** — Whether HTTP requests to port 80 should redirect to HTTPS is a proxy configuration detail, not a user requirement. The reverse proxy's default behavior is acceptable.
- **Removal of old `.local` mDNS hostnames** — The old hostnames can remain in DNS indefinitely without harm. Cleanup is a separate housekeeping task.
- **AdGuard DNS rewrite automation via API** — If AdGuard rewrites must be configured manually via the AdGuard web UI rather than Ansible, that is acceptable as a one-time setup step. Ansible automation of this is desirable but not required for this feature.
- **Certificate expiry alerting** — Caddy handles renewal automatically with built-in retries over a 30-day renewal window. Adding Prometheus or Uptime Kuma checks for certificate validity is a separate monitoring enhancement that can be layered on after the base HTTPS feature is stable.
- **Monitoring system URL updates** — Existing Uptime Kuma targets and healthcheck URLs check backends directly by IP:port (e.g., `http://192.168.1.213:2283`). These continue to function since backends are unchanged. Updating monitoring to validate the HTTPS proxy layer is a separate observability improvement.

## Decision Log

| # | Ambiguity | Decision | Rationale |
|---|-----------|----------|-----------|
| D-001 | Wildcard vs per-subdomain DNS records at registrar | Per the reference document, either approach is acceptable. Default to wildcard (`*.hus-sky.no`) for simplicity. | A wildcard A record avoids the need to add a new DNS record every time a new service is added. Since all subdomains point to the same reverse proxy IP, wildcard is simpler and future-proof. |
| D-002 | How AdGuard DNS rewrites are managed (Ansible-automated vs manual one-time setup) | Accept both approaches: Ansible automation is preferred, but manual configuration via AdGuard web UI is acceptable as a fallback. | The reference document lists AdGuard as a service that needs a new Caddy site block, but also notes that DNS rewrites are needed. If AdGuard lacks an Ansible-manageable config file for rewrites, manual setup is a pragmatic one-time task. |
| D-003 | Scope of Home Assistant Caddy site block | Include the `ha.hus-sky.no` site block template in the reverse proxy role, but flag it as inactive/conditional. Deploy only when Home Assistant is running. | The reference document says "include in design but may not be implemented in this feature." A conditional template costs nothing and avoids a separate PR later. |
| D-004 | Backward compatibility duration for Nextcloud dual-domain trust | Nextcloud trusts both `nextcloud.local` and `nextcloud.hus-sky.no` until the operator explicitly removes the old domain. No automatic timeout. | The reference document specifies "temporarily trust both" but does not define a duration. Keeping both trusted indefinitely has no security downside (both are LAN-local) and avoids disrupting any client still using the old URL. Cleanup is out of scope. |
| D-005 | Caddy binary replacement strategy (custom build) | Replace the APT-installed stock Caddy with a custom-built binary that includes the Domeneshop DNS module. The custom binary must be built reproducibly. | The stock Caddy from APT does not include third-party DNS provider modules. A custom build using `xcaddy` (or equivalent build tooling) is the standard approach documented by the Caddy project. |
| D-006 | How Caddy receives Domeneshop credentials at runtime | Inject via systemd environment file or environment override sourced from Ansible vault. Do not write plaintext credentials to Caddyfile or template files. | Aligns with the constitution's secrets policy and the reference document's explicit requirement. Systemd environment overrides are the standard approach for injecting secrets into services managed by systemd. |
| D-007 | Certificate type (individual vs wildcard) | Default to individual certificates per subdomain, unless the implementation finds wildcard certificates simpler with the Domeneshop DNS provider. | Individual certificates are the Caddy default when using named site blocks. Wildcard certificates require explicit configuration but reduce the number of ACME transactions. Either is acceptable; the implementation should choose based on the Caddy/Domeneshop module's capabilities. |

## Open Questions

None — all ambiguities have been resolved via the decision log above.
