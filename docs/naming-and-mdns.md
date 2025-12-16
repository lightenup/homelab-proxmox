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
| `adguard.local` | `192.168.1.210` | AdGuard Home (DNS) |
| `homeassistant.local` | `192.168.1.212` | Home Assistant |

### How it works

- **Linux (LXCs/VMs)**: Uses `avahi-daemon` to broadcast and resolve names.
- **macOS / iOS**: Native support via Bonjour.
- **Windows**: Native support in Windows 10/11.

### Limitations

- **Android**: Android does **not** natively support `.local` mDNS resolution in the browser (Chrome) or most apps. You must use the IP address or a specific app that supports mDNS.
- **Subnets**: mDNS works via multicast, which typically does not cross subnet boundaries (routers). Since we are on a flat LAN (`192.168.1.0/24`), this works fine.

## Future Plan (DNS)

Once a new router is introduced (e.g., OPNsense/pfSense) or the existing router allows custom DNS settings:

1.  **Domain**: We will migrate to `home.arpa` (RFC 8375) or `*.lan`.
2.  **Resolver**: AdGuard Home (`192.168.1.210`) will become the primary DNS for the network.
3.  **DHCP**: The router will assign AdGuard as the DNS server via DHCP.
4.  **Static Leases**: We will configure static leases or DNS rewrites in AdGuard to map hostnames to IPs.

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
