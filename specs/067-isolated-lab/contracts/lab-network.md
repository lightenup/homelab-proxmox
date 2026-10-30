# Contract: lab network isolation

**Owner**: root Ansible, `ansible/playbooks/lab_setup.yml` (the `LAB NETWORK` block, tag
`lab-network`). The pipeline never changes these rules (R-004).

## Network

| Item | Value |
|---|---|
| Bridge | `vmbr99`, `bridge-ports none` |
| Host address / lab gateway | `10.99.0.1/24` |
| Lab-copy range | `10.99.0.200`–`10.99.0.254` (mirrored last part of the production address) |
| Reserved | `.1` (host), `.10`, `.11` (lab-rig VMs) |
| Egress | MASQUERADE out of `vmbr0` (existing) |
| DNS | `1.1.1.1` (tfvars `nameserver`), over the internet |

## nftables table `inet lab_isolation`

```nft
table inet lab_isolation {
  set lan_private { type ipv4_addr; flags interval;
    elements = { 10.0.0.0/8, 100.64.0.0/10, 172.16.0.0/12, 192.168.0.0/16 } }
  chain forward { type filter hook forward priority filter; policy accept;
    iifname "vmbr99" ct state established,related accept
    iifname "vmbr99" ip daddr 10.99.0.0/24 accept
    iifname "vmbr99" ip daddr @lan_private drop
  }
  chain input { type filter hook input priority filter; policy accept;
    iifname "vmbr99" ct state established,related accept
    iifname "vmbr99" drop
  }
}
```

The rules are loaded on `vmbr99` `post-up` from `/etc/nftables.d/lab-isolation.nft` and removed on
`post-down`. Rendering the file is idempotent.

## Isolation exceptions

| Destination | Source | Reason |
|---|---|---|
| *(none)* | | |

Adding a row requires a reason, and the change must update the isolation probe's expectations.

## Isolation probe (FR-008), run from inside every lab copy

| Target | Expected |
|---|---|
| `192.168.1.214:9090` (Prometheus) | refused or timed out |
| `192.168.1.222:80` (ntfy) | refused or timed out |
| `192.168.1.109:2049` (NAS NFS) | refused or timed out |
| `192.168.1.112:8006` (host API via LAN address) | refused or timed out |
| `10.99.0.1:22` (host via lab gateway) | refused or timed out |
| `deb.debian.org:443` | TCP connect succeeds |

The probe is `timeout 3 bash -c '</dev/tcp/<host>/<port>'` via `pct exec`, so it needs no tool in
the container. A target counts as reachable only when its TCP
connect succeeds. The output `reports/lab/isolation.json` holds one object per target with
`expected`, `observed` and `ok`.
