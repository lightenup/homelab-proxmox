# Future Network Architecture

## 0. Current State (Interim)

As of **Iteration 1 (Bootstrap)**, the network is flat to simplify initial adoption.

- **Network**: `192.168.1.0/24` (Default LAN)
- **Gateway**: `192.168.1.1`
- **Domain**: `hus-sky.no` (Domeneshop), wildcard `*.hus-sky.no → 192.168.1.211` via public DNS
- **Service IPs**:
  - AdGuard: `192.168.1.210` (`adguard.hus-sky.no`)
  - Reverse Proxy: `192.168.1.211` (HTTPS termination, Let's Encrypt via DNS-01)
  - Home Assistant: `192.168.1.212` (`ha.hus-sky.no`)
  - Immich: `192.168.1.213` (`immich.hus-sky.no`)
  - Monitoring (Grafana): `192.168.1.214` (`grafana.hus-sky.no`)
  - Jellyfin: `192.168.1.215` (`jellyfin.hus-sky.no`)
  - Nextcloud: `192.168.1.216` (`nextcloud.hus-sky.no`)

### Remote Access

Remote access is provided by **Tailscale** running on the Proxmox host (`pve`).

- **Mode**: Subnet Router
- **Advertised Routes**: `192.168.1.0/24`
- **ACL Policy**: Default Deny (see `docs/tailscale-acl.example.json`)
- **Tags**: `tag:proxmox` applied to the host.

*The sections below describe the target architecture to be implemented in future iterations.*

## 1. Goals

This document describes the **target state** for the home network that supports the Proxmox homelab:

- Isolate **management**, **services**, **clients**, and **IoT**.
- Make it easy to **rebuild** Proxmox/services without breaking the rest of the house.
- Give a clean place to:
  - Run **AdGuard** as central DNS.
  - Expose **Immich** and **Home Assistant** safely (primarily via VPN, optionally via reverse proxy later).
  - Route one SSID’s traffic out via **VPN**.
- Keep the design simple enough to **retrofit gradually** from an initially flat network.

This is a *target* design. The physical router/switch capabilities and migration pace will determine how quickly it’s implemented.

## 2. High-level layout

Conceptually there are 5 logical networks (VLANs):

- **VLAN 10 – Management**
  Proxmox host, Synology NAS, Raspberry Pi (CI runner), router management.
- **VLAN 20 – Services**
  LXCs / VMs providing services like Immich, AdGuard, Home Assistant, reverse proxy.
- **VLAN 30 – LAN (Normal clients)**
  Laptops, desktops, phones, TV etc.
- **VLAN 40 – VPN egress**
  Devices whose outbound traffic should always go via VPN (dedicated SSID).
- **VLAN 50 – IoT** (optional, but planned)
  IoT gadgets (bulbs, switches, sensors, etc.) that Home Assistant needs to talk to.

### Logical picture

```text
                  ┌────────────────────────────────────────┐
                  │              Router/Firewall           │
                  │                                        │
                  │  VLAN 10  (Mgmt)   192.168.10.0/24     │
WAN ──────────────┤  VLAN 20  (Services) 192.168.20.0/24   │
                  │  VLAN 30  (LAN)     192.168.30.0/24    │
                  │  VLAN 40  (VPN)     192.168.40.0/24    │
                  │  VLAN 50  (IoT)     192.168.50.0/24    │
                  └──────┬──────────────┬────────┬─────────┘
                         │              │        │
                 trunk (VLAN-aware)     │        │
                         │              │        │
                 ┌───────┴───────┐   WiFi AP  WiFi AP
                 │   Proxmox     │    SSID(s) SSID(s)
                 │   (vmbr0.*)   │
                 └───────────────┘
```

Proxmox will use a **VLAN-aware bridge** (e.g. `vmbr0`) and per-VLAN subinterfaces like `vmbr0.10`, `vmbr0.20`, etc. LXCs/VMs connect to the appropriate tagged interface.

## 3. VLANs / Subnets in more detail

> Note: subnet sizes and exact addressing can be adjusted; these are examples.

### 3.1 VLAN 10 – Management (`192.168.10.0/24`)

**Purpose:**
Keep critical infrastructure separate from user traffic and IoT noise.

**Typical devices:**

- Proxmox host (hypervisor)
- Synology NAS
- Raspberry Pi (GitHub Actions runner / misc infra)
- Router/firewall management IP
- Optional: management IPs for switches/APs (if supported)

**Access rules (intention):**

- Only **admin devices** (e.g. your laptop) can reach VLAN 10, either:
  - Directly (if connected on a tagged port), or
  - Via VPN into the management subnet.
- Other VLANs should **not** have direct access to management, except tightly controlled cases (e.g. backup traffic from services to NAS).

### 3.2 VLAN 20 – Services (`192.168.20.0/24`)

**Purpose:**
Dedicated network for homelab services.

**Planned LXCs/VMs:**

- `immich-lxc`
- `adguard-lxc`
- `homeassistant-lxc`
- `reverse-proxy-lxc` (Caddy with DNS-01 HTTPS)
- Future services (e.g. Gitea, monitoring, etc.)

**Traffic patterns:**

- **From LAN (VLAN 30)**:
  - HTTP(S) to services via reverse proxy.
  - DNS queries to AdGuard.
- **From IoT (VLAN 50)**:
  - Connections to Home Assistant (MQTT, integrations).
- **To NAS (mgmt VLAN 10)**:
  - NFS/iSCSI from Immich LXC, backup traffic, etc. (tightly controlled).

### 3.3 VLAN 30 – LAN / Normal clients (`192.168.30.0/24`)

**Purpose:**
Everyday devices with “normal” internet access.

**Devices:**

- Laptops, desktops
- Phones & tablets
- Smart TV, consoles, etc.

**Routing / DNS:**

- Default route: directly out to WAN.
- Default DNS: **AdGuard LXC** (VLAN 20) as primary DNS.
- Access to management VLAN is restricted (ideally none, except when explicitly allowed from an admin device).

### 3.4 VLAN 40 – VPN egress (`192.168.40.0/24`)

**Purpose:**
A dedicated network/SSID where **all outbound traffic is forced through VPN** (e.g. commercial VPN provider or self-hosted WireGuard).

**Devices:**

- Devices that should always appear from another country/exit node.
- Potentially a “guest” SSID that you want to protect / segregate.

**Routing:**

- Default route for VLAN 40 goes through VPN.
- Firewall prevents bypassing the VPN to WAN directly.

### 3.5 VLAN 50 – IoT (`192.168.50.0/24`) – optional but planned

**Purpose:**
Contain “untrusted” IoT devices while still allowing Home Assistant to control them.

**Devices:**

- Smart bulbs, plugs, switches, sensors
- Cameras and other random IoT gadgets

**Routing:**

- IoT devices have limited outbound internet (only what’s strictly needed).
- They do **not** reach management or services directly.
- **Home Assistant** (in VLAN 20) gets specific firewall rules to talk into VLAN 50 on the ports/protocols required (e.g. MQTT, vendor APIs).

## 4. Service placement

### 4.1 Proxmox & storage

- **Proxmox host** lives in VLAN 10.
- **Synology NAS** also in VLAN 10; exports NFS/iSCSI to services in VLAN 20.
- **Raspberry Pi** (CI runner) is in VLAN 10 and reaches:
  - Proxmox API (for Terraform),
  - Services in VLAN 20 as needed (e.g. Ansible SSH).

### 4.2 LXCs (VLAN 20)

Each major service gets its **own LXC**:

- `immich-lxc`
  - OS: Debian stable.
  - Data: Synology NFS mount inside the LXC for photo storage.
  - App: Immich stack run via containers (Docker/Compose or Podman), managed by Ansible.
- `adguard-lxc`
  - Provides DNS for LAN/Services/IoT.
  - Router’s DNS points here.
- `homeassistant-lxc`
  - Integrates with IoT devices in VLAN 50.
  - Accessed from LAN and remotely via VPN.
- `reverse-proxy-lxc`
  - Fronts all services with HTTPS termination via `*.hus-sky.no`.
  - Custom Caddy binary with `caddy-dns/domainnameshop` for automated Let's Encrypt DNS-01 certificates.
  - Services are not publicly exposed; DNS resolves to LAN IP `192.168.1.211`.

## 5. Remote access

Initial plan:

- **Primary remote access:** VPN (WireGuard or Tailscale).
  - Phone and laptops join “inside” the network.
  - Immich and Home Assistant are accessed via internal hostnames, not publicly exposed ports.

- **Future option:**
  Expose only the **reverse proxy** to the internet via port-forward, with:
  - TLS termination,
  - Auth where necessary,
  - Integration with a real domain name once purchased.

## 6. Migration path from a flat network

The network does **not** have to be fully segmented from day one. A realistic migration:

1. **Phase 0 – Flat network**
   - Everything is in a single subnet.
   - Proxmox + services + clients all share that network.
   - DNS still via AdGuard if possible.

2. **Phase 1 – Introduce VLANs on the router and Proxmox**
   - Enable VLAN-aware bridge on Proxmox (e.g. `vmbr0`).
   - Create VLAN 10 (mgmt) and move Proxmox host, NAS, Pi there.
   - Create VLAN 20 and move service LXCs there.
   - Leave clients on the original flat LAN (which effectively becomes VLAN 30).

3. **Phase 2 – Add IoT & VPN egress VLANs**
   - Create VLAN 50 for IoT and start moving devices over gradually.
   - Create VLAN 40 and bind one SSID to it; configure VPN egress on the router.

4. **Phase 3 – Tighten firewall rules**
   - Restrict access from LAN/IoT to management.
   - Explicitly allow only the needed flows:
     - LAN → Services (HTTP/S, DNS)
     - Services → NAS
     - HA → IoT
     - Admin/VPN → Management.

During all phases, access services via **hostnames** (e.g. using AdGuard for DNS overrides) so IP changes and subnet moves don’t break client configs.

## 7. Open questions / placeholders

- Exact VLAN IDs and subnets may be adjusted when the new router is selected.
- Decisions still to be made on:
  - Which VPN solution to standardize on (WireGuard vs. Tailscale vs. router-native).
  - Whether to manage switch/AP VLAN configuration purely manually or via Ansible/other tooling.
- ~~Once a domain is acquired, update reverse proxy configuration, internal DNS overrides, this document.~~ **Done** — `hus-sky.no` acquired via Domeneshop (2026-03-01). Wildcard DNS points to reverse proxy. All services accessible via HTTPS with valid Let's Encrypt certificates. Split-horizon DNS not yet needed (public DNS resolves to LAN IP).
