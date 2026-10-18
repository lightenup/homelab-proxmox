# Local DNS & Naming

## Overview

This document describes the local naming strategy for the homelab. Currently, we use **mDNS** (Multicast DNS) to provide `.local` hostnames for all services and the Proxmox host. This allows for human-readable names without modifying the central router or DHCP settings.

## Current Setup (mDNS)

All managed hosts broadcast their hostname on the local network via the `.local` domain.

### Addressing

| Hostname | IP Address | Service |
|----------|------------|---------|
| `pve.local` | `192.168.1.112` | Proxmox VE Host |
| `proxy.local` | `192.168.1.211` | Nginx Reverse Proxy |
| `immich.local` | `192.168.1.213` | Immich Photo Backup |
| `homeassistant.local` | `192.168.1.212` | Home Assistant |
| `nextcloud.local` | `192.168.1.216` | Nextcloud Cloud Storage |
| `llm-router.local` | `192.168.1.220` | LiteLLM gateway (spec `064`) |
| `xmjdvvw39y2t.local` | `192.168.1.177` | dev Mac — local LLM backend. **Announce-only, see below.** |

### How it works

- **Linux (LXCs/VMs)**: Uses `avahi-daemon` to broadcast and resolve names.
- **macOS / iOS**: Native support via Bonjour.
- **Windows**: Native support in Windows 10/11.

### Limitations

- **Android**: Android does **not** natively support `.local` mDNS resolution in the browser (Chrome) or most apps. You must use the IP address or a specific app that supports mDNS.
- **Subnets**: mDNS works via multicast, which typically does not cross subnet boundaries (routers). Since we are on a flat LAN (`192.168.1.0/24`), this works fine. The one place it bites is the LAB subnet (`192.168.20.0/24`), which therefore cannot resolve or reach the dev Mac — deliberate, see spec `064`.
- **Containers cannot resolve `.local` at all.** Docker's embedded DNS at `127.0.0.11` never consults host NSS, and `network_mode: host` does **not** help — it shares the network namespace, not the filesystem, so the container keeps its own `nsswitch.conf` (`hosts: files dns`) and its own NSS libraries, with no `libnss-mdns`. The pattern that works is to resolve the name on the **host** at deploy time and pass the result into the container as `extra_hosts`; `ansible/roles/llm_router/tasks/main.yml` does this and is the reference implementation.

### The dev Mac announces but never answers

This one cost hours to find and will catch the next service that has to reach the Mac, so
it is recorded here rather than only in `064`.

`xmjdvvw39y2t.local` resolves **sometimes**, from some hosts, and never from a resolver
with a cold cache. Measured from `pve`:

| test | result |
|---|---|
| mDNS query → multicast `224.0.0.251:5353` | **no answer** |
| mDNS query → unicast `192.168.1.177:5353` | **no answer** |
| same query against `pve`'s own avahi (control) | answered |
| `tcpdump` while the Mac registers a Bonjour service | the Mac's **announcement arrives**, carrying its `A` record |
| `getent hosts` right after that announcement | resolves |
| `getent hosts` after `systemctl restart avahi-daemon` | **NO_RESOLVE** again |

The Mac **announces** its records but **never answers a query**. A resolver that happens
to overhear an announcement caches it and works; a resolver with a cold cache can never
learn the name, because the query it sends goes unanswered. That is why this reads as
"mDNS is completely broken" one minute and fine the next — it depends entirely on whether
anything had recently heard the Mac speak unprompted.

The cause is **stealth mode, enforced by an MDM profile**
(`/Library/Managed Preferences/com.apple.security.firewall`, `EnableStealthMode = 1`),
which drops unsolicited inbound probes — exactly the class of packet an mDNS query is.
The per-app firewall already permits `mDNSResponder`, so the allowlist is not the blocker.
Neither the MDM profile nor the Zscaler network filter is ours to change.

**The fix is to stop depending on the Mac answering and keep it announcing**: a LaunchAgent
re-registers a Bonjour service every 45 s, and each registration emits an announcement
burst carrying the host `A` record. See
[`specs/064-llm-router/mac-mdns-announcer/README.md`](../specs/064-llm-router/mac-mdns-announcer/README.md).

**Any test of this from a warm cache proves nothing.** Flush first:

```bash
ssh root@192.168.1.112 'systemctl restart avahi-daemon && sleep 2 && getent hosts xmjdvvw39y2t.local'
```

## Future Plan (DNS)

Once a new router is introduced (e.g., OPNsense/pfSense) or the existing router allows custom DNS settings:

1.  **Domain**: We will migrate to `home.arpa` (RFC 8375) or `*.lan`.
2.  **Resolver**: The new router will provide LAN DNS.
3.  **Static Leases**: We will configure static leases or DNS entries on that router to map hostnames to IPs.

This will solve the Android limitation and provide a more robust naming system.

## Troubleshooting

If you cannot resolve a `.local` name:

1.  **Check Service**: Ensure `avahi-daemon` is running on the target host.
    ```bash
    systemctl status avahi-daemon
    ```
2.  **Check Firewall**: Ensure UDP port 5353 is allowed (should be open by default on trusted LAN).
3.  **Restart mDNS**:
    ```bash
    sudo systemctl restart avahi-daemon
    ```
4.  **Check you are not reading a warm cache.** A name can resolve because the resolver
    overheard an announcement, not because a query works. Restart `avahi-daemon` and retry
    before concluding anything — see *The dev Mac announces but never answers* above.
5.  **Resolving from inside a container?** It will not work, by any container-side setting.
    Resolve on the host and inject `extra_hosts`.
