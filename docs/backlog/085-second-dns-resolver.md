# Backlog: a second, independent DNS resolver for everything we manage

**Status**: Backlog — raised 2026-10-18 after the `EndpointDown` DNS bursts. Spec only; the
technical solution is chosen at implementation time.
**Order**: Low priority, **after [`081`](./081-externalise-prod-topology.md)**. `081` moves the
same nameserver values out of the repo, so doing this afterwards avoids editing them twice.

## Why this exists

On 2026-10-15 and 2026-10-16, three DNS outages of 2–3 minutes made every `*.hus-sky.no` probe
fail at once and page `EndpointDown` at critical. Caddy and the services were healthy throughout;
only name resolution failed (`probe_dns_lookup_time` hit its 8s timeout). The alerting side is
fixed: blackbox now pins the estate's names in `/etc/hosts`, and public DNS has its own
warning-level probe (`PublicDnsResolutionFailing`, PR #256).

The services themselves are still exposed. Every LXC resolves through **one** resolver,
Cloudflare's `1.1.1.1`, with no fallback. During an outage like those, every service's outbound
lookups fail: Nextcloud and Immich reaching external APIs, Hermes and its agent calling the
gateway or the web, Alertmanager delivering to Pushover and ntfy, image pulls during deploys. A
second resolver from a different provider removes Cloudflare as a single point of failure.

## Current state (verified 2026-10-18)

| What | Resolver today | Managed by |
|---|---|---|
| All 12 LXCs (`pct config`: jellyfin, immich, eurooffice, monitoring, homeassistant, nextcloud, financial-scenario, market-model, proxy, llm-router, hermes, ntfy) | `1.1.1.1` only | Terraform `nameserver` (`prod.tfvars.template`, `lxc_service` module) |
| Docker containers inside the LXCs | Docker's embedded DNS, forwarding to the LXC's `/etc/resolv.conf` | Inherited from the LXC |
| PVE host (`pve`, runs the pipeline) | Tailscale MagicDNS (`100.100.100.100`), whose upstream is whatever the tailnet's global nameservers are | Tailscale admin console, outside the repo |
| Synology NAS | **Unknown** — not reachable over SSH from the dev box when checked | DSM, set by hand |
| Blackbox `blackbox-dns` probe | Queries `1.1.1.1` only (`blackbox_dns_resolvers`) | `group_vars/monitoring` |

Out of scope: the Mac (managed in the `local-llm` repo) and client devices on the LAN (set by the
ISP router's DHCP).

## Requirements

- **FR-001 — Coverage.** Every machine whose DNS configuration this estate manages resolves
  through at least two resolvers: all LXCs, the PVE host and the Synology. For a machine whose
  resolver is set outside the repo (the PVE host via Tailscale, the Synology via DSM), the
  required configuration is still written down in the repo, and the place it is set is named.
- **FR-002 — Provider independence.** At least one resolver on every machine is run by a
  different provider from the others, so that one provider's outage cannot take out all of
  them. Which provider is decided at implementation.
- **FR-003 — Failover without intervention.** When the primary resolver stops answering,
  lookups succeed through the other one with no manual step. An occasional slower lookup during
  failover is acceptable; a lookup that fails while another configured resolver is healthy is not.
- **FR-004 — No change to answers.** Every resolver returns the same records for the estate's
  own names (`*.hus-sky.no` → the reverse proxy). Adding a resolver must not change what any
  service connects to.
- **FR-005 — Single source of truth.** The resolver list is defined once and used by every
  consumer (LXC config, monitoring probes, documentation), so the monitored resolvers can't
  drift from the configured ones. This must fit whatever `081` decides about topology living
  outside the repo.
- **FR-006 — No-downtime rollout.** Applying the change to an existing LXC does not destroy or
  rebuild it, and does not interrupt the services running in it beyond a restart where one is
  unavoidable.

## Monitoring requirements

- **MR-001 — Probe each resolver.** The public-DNS probe checks every configured resolver
  separately, with the same pass criteria as today: answers in time, NOERROR, and the A record
  is the reverse proxy.
- **MR-002 — Warn only when all fail.** `PublicDnsResolutionFailing`, or its successor, fires at
  `warning` only when **every** configured resolver has failed for the sustained window (5m
  today). One resolver down is the case the fallback exists for, so it does not page.
- **MR-003 — Make a degraded fallback visible.** A single resolver failing for a sustained
  period is recorded at `info` (silent on Pushover and ntfy), so lost redundancy can be seen
  without causing noise.

## Success criteria

- **SC-001**: With the primary resolver blocked on a test LXC, its services' outbound lookups
  keep succeeding, and `getent hosts` for an external name resolves.
- **SC-002**: A drill that blocks one resolver produces no `warning` or `critical` alert, only
  the `info` from MR-003. Blocking both produces exactly one `PublicDnsResolutionFailing`.
- **SC-003**: Every LXC's live config (`pct config`), the PVE host's effective upstream and the
  Synology's DNS settings all list two resolvers from different providers. These values are
  recorded in the item's resolution.
- **SC-004**: The rollout recreates no LXC (FR-006): the Terraform plan shows only in-place
  updates.

## Open questions for implementation time

- Which second provider (Quad9, Google, another), and whether to prefer one with a published
  no-logging policy.
- Whether the PVE host should keep MagicDNS (with redundant global nameservers set in the
  tailnet) or resolve directly.
- How LXC resolver changes reach containers that are already running (does Docker pick up a
  changed `/etc/resolv.conf` without a restart?).
- How the Synology is configured and verified, given there is no SSH path from the dev box.
- Whether IPv6 resolvers are wanted alongside IPv4.

## Dependencies

- **After [`081`](./081-externalise-prod-topology.md)**: the nameserver is part of the topology
  `081` moves out of the repo; FR-005's single source should be the one `081` creates.
- Builds on PR #256 (`blackbox-dns` job, `dns_public` module, `PublicDnsResolutionFailing`).
