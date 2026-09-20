#!/bin/bash
# Re-announce this Mac's .local A record on the LAN, so the homelab gateway can
# resolve the name FR-013 requires it to address the local tier by.
#
# WHY THIS EXISTS. Measured on XMJDVVW39Y2T 2026-09-19: this Mac *announces* its
# mDNS records (unsolicited, on registration and network change) and those
# announcements reach the homelab, where avahi caches them. It never *answers* an
# mDNS query — not multicast to 224.0.0.251:5353, not unicast to its own
# 192.168.1.177:5353. Proven by flushing avahi on pve and re-resolving: the name
# resolves while the cached announcement is held, and never resolves from a cold
# cache. The app firewall already permits /usr/sbin/mDNSResponder inbound, so the
# drop is the MDM-enforced stealth mode
# (/Library/Managed Preferences/com.apple.security.firewall: EnableStealthMode = 1)
# or the Zscaler network filter. Both are corporate controls; neither is ours to
# change, and neither needs changing for this.
#
# So: stop relying on the Mac answering, and keep it announcing. Registering a
# Bonjour service makes mDNSResponder emit an announcement burst that carries the
# host A record as an additional record, which is exactly what a cold resolver
# needs. Re-register on a cadence shorter than the resolver holds the record and
# the mapping stays live.
#
# The service registered is the real one — the TLS terminator on :4443 that the
# gateway actually calls — not a dummy. It is accurate, self-documenting on the
# LAN, and its announcement carries the A record either way.
#
# Corrected 2026-09-20: this advertised _http._tcp :4000 until the local tier moved
# behind TLS. Nothing consumed the SRV record, so nothing broke — only the A record
# in the announcement is load-bearing — but an inaccurate service record on the LAN
# is a trap for the next reader.
#
# Lifetime is deliberately tied to the login session (this runs as a LaunchAgent,
# not a daemon). Docker Desktop and oMLX are session-scoped too, so when the Mac
# cannot serve the local tier the name stops resolving within one resolver TTL and
# the gateway fails clean — the SC-001-withdrawn behaviour, arrived at honestly
# rather than by a stale mapping pointing at a host that cannot answer.

set -u

PORT="${HERMES_MDNS_PORT:-4443}"
HOLD="${HERMES_MDNS_HOLD:-6}"
NAME="Mac LiteLLM (homelab local tier)"
SVC="${HERMES_MDNS_SVC:-_https._tcp}"

# RFC 6762 §8.3: a responder sends at least two announcements one second apart.
# Holding the registration ~6s covers the burst with margin, then we exit so
# launchd can start a fresh cycle — a long-lived registration would announce once
# and then go quiet, waiting for queries that never arrive.
/usr/bin/dns-sd -R "$NAME" "$SVC" local "$PORT" >/dev/null 2>&1 &
pid=$!
sleep "$HOLD"
kill "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true
