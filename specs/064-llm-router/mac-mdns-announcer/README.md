# Mac mDNS announcer — making `xmjdvvw39y2t.local` resolvable from the homelab

FR-013 requires the gateway to address the Mac by its stable mDNS `.local` name,
never a DHCP-assigned IP. On 2026-09-19 that name did not resolve from anywhere in
the homelab, and this is what was wrong and what fixes it.

## What was actually broken

Measured from `pve` (192.168.1.112) against the Mac (`XMJDVVW39Y2T`, 192.168.1.177):

| test | result |
|---|---|
| `curl http://192.168.1.177:4000/health/liveliness` | `"I'm alive!"` — the LAN path was always fine |
| `getent hosts xmjdvvw39y2t.local` | **NO_RESOLVE** |
| mDNS query, multicast to `224.0.0.251:5353` | **no answer** |
| mDNS query, unicast to `192.168.1.177:5353` | **no answer** |
| same query against `pve`'s own avahi (control) | answered |
| `tcpdump` on `vmbr0` while the Mac registers a Bonjour service | the Mac's **announcement arrives**, carrying `XMJDVVW39Y2T.local. A 192.168.1.177` |
| `getent` immediately after that announcement | **resolves** |
| `getent` after `systemctl restart avahi-daemon` (cold cache) | **NO_RESOLVE** again |

So the Mac **announces** its records but **never answers a query**. A resolver that
happens to hear an announcement caches it and resolution works; a resolver with a
cold cache can never learn the name, because the query it sends to find out goes
unanswered. That is why this looked like "mDNS is completely broken" — it depends
entirely on whether anything had recently heard the Mac speak unprompted.

## Why we are not "fixing" the Mac's firewall

The app firewall already permits `/usr/sbin/mDNSResponder` inbound
(`socketfilterfw --getappblocked` → permitted), so the per-app allowlist is not the
blocker. What remains is **stealth mode, enforced by an MDM configuration profile**:

```
/Library/Managed Preferences/com.apple.security.firewall
    EnableFirewall    = 1
    EnableStealthMode = 1
```

Stealth mode drops unsolicited inbound probes, which is exactly the class of packet
an mDNS query is. The Zscaler network filter is the other candidate. Both are
corporate controls on a managed device, `sudo` on this Mac requires a policy
acknowledgement, and a locally-changed managed preference is reapplied anyway.
Neither is ours to change — **and neither needs changing**, because announcing is
the half that already works.

## The fix

Stop depending on the Mac answering; keep it announcing. Registering a Bonjour
service makes `mDNSResponder` emit an announcement burst that carries the host `A`
record as an additional record — precisely what a cold resolver needs. Re-register
on a cadence shorter than the resolver's hold time and the mapping stays live.

- `hermes-mdns-announce.sh` — registers the **real** service (the LiteLLM endpoint
  on `:4000`), holds it ~6 s to cover RFC 6762 §8.3's two announcements, then exits
  so the next cycle produces a fresh announcement. A long-lived registration would
  announce once and then go quiet, waiting for queries that never arrive.
- `no.hus-sky.hermes-mdns-announce.plist` — a **LaunchAgent** (no root) with
  `StartInterval 45`.

Killing the registration sends a goodbye for the *service* records only; the host
`A` record survives it. Verified.

### Install

```bash
cp specs/064-llm-router/mac-mdns-announcer/hermes-mdns-announce.sh ~/.local/bin/
chmod +x ~/.local/bin/hermes-mdns-announce.sh
cp specs/064-llm-router/mac-mdns-announcer/no.hus-sky.hermes-mdns-announce.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/no.hus-sky.hermes-mdns-announce.plist
launchctl list | grep hermes          # label present, last exit 0
```

### Verify — from `pve`, not from the Mac

The only honest test flushes the resolver first; querying a warm cache proves
nothing, which is what made this hard to see in the first place.

```bash
ssh root@192.168.1.112 'systemctl restart avahi-daemon'     # cold cache
ssh root@192.168.1.112 'getent hosts xmjdvvw39y2t.local'    # 192.168.1.177, within one cycle
ssh root@192.168.1.112 'curl -s -m5 http://xmjdvvw39y2t.local:4000/health/liveliness'
#   "I'm alive!"  ← the RUNBOOK § 4 gate, by name
```

Recorded result 2026-09-19: resolves from a cold cache in under 2 s and stayed
resolved across a 100 s poll; the `§ 4` gate returns HTTP 200.

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/no.hus-sky.hermes-mdns-announce.plist
rm ~/Library/LaunchAgents/no.hus-sky.hermes-mdns-announce.plist ~/.local/bin/hermes-mdns-announce.sh
```

## Consequences worth knowing

- **It is a LaunchAgent, so it dies with the login session** — as do Docker Desktop
  and oMLX. When the Mac cannot serve the local tier, the name stops resolving
  within one resolver hold and the gateway **fails clean**, which is the
  SC-001-withdrawn behaviour reached honestly rather than by a stale mapping
  pointing at a host that cannot answer.
- **It does not cross subnets.** mDNS is multicast; LAB (`192.168.20.0/24`) still
  cannot resolve or reach the Mac, by design (`deploy-plan.md` § *LAB and the local
  tier*). This buys PROD (`192.168.1.220`), which shares the Mac's subnet.
- **The container cannot resolve `.local` at all, by any container-side setting.** Docker's
  embedded DNS at `127.0.0.11` never consults host NSS, and `network_mode: host` does not
  help either — it shares the network namespace, not the filesystem, so the container keeps
  its own `nsswitch.conf` (`hosts: files dns`) and NSS libraries. A local resolver cannot
  bridge the gap either, because this Mac never *answers* a query: only avahi's cache on the
  LXC knows the mapping. So the role resolves the name on the LXC (hence `mdns_base`) and
  passes the result to the container as `extra_hosts`, refreshed on every deploy.
- **If the Mac's IP changes**, nothing here breaks: the name is announced with
  whatever address the Mac holds.
