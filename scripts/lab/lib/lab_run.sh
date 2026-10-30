#!/usr/bin/env bash
# lab_run.sh - building blocks of an isolated LAB rehearsal (067).
#
# A LAB run creates a copy of one service on vmbr99, configures and checks it, destroys it, and
# proves production did not change. The orchestrator (pve-service-deploy) calls these in the
# order in specs/067-isolated-lab/contracts/pve-service-deploy-lab.md. Needs ct_conflicts.sh and
# fingerprint.sh sourced first.
#
# Env: STATE_ROOT, SCRATCH_ROOT (default /var/lib/homelab-proxmox/lab-scratch), MEMINFO_PATH,
# LAB_MEMORY_MARGIN_MIB (6144), TFVARS_DIR.

LAB_BRIDGE="vmbr99"
LAB_SCRATCH_ROOT_DEFAULT="/var/lib/homelab-proxmox/lab-scratch"

lab_scratch_root() { echo "${SCRATCH_ROOT:-${LAB_SCRATCH_ROOT_DEFAULT}}"; }
lab_state_root() { echo "${STATE_ROOT:-/var/lib/homelab-proxmox/state}/lab"; }

# --- lock -------------------------------------------------------------------------------------

# Take the lab run lock on fd 8 for the life of the process. Refuses when another run holds it.
lab_lock_acquire() {
    local lock="$(lab_state_root)/.lock"
    mkdir -p "$(dirname "${lock}")"
    exec 8>"${lock}"
    if ! flock -n 8; then
        echo "lab: another LAB run holds ${lock}" >&2
        return 1
    fi
}

# --- sweep ------------------------------------------------------------------------------------

# Remove leftover lab copies (identity rule), scratch dirs and lab states.
# Usage: lab_sweep <report.json>
lab_sweep() {
    local report="${1:?lab_sweep requires a report path}"
    local scratch state_root vmid hostname ip entries="" ok=true
    scratch="$(lab_scratch_root)"
    state_root="$(lab_state_root)"

    local copies=() line
    while IFS= read -r line; do [[ -n "${line}" ]] && copies+=("${line}"); done < <(list_lab_copies)
    for line in "${copies[@]}"; do
        IFS=$'\t' read -r vmid hostname ip <<<"${line}"
        sudo -n pct stop "${vmid}" >/dev/null 2>&1 || true
        if sudo -n pct destroy "${vmid}" --purge >/dev/null 2>&1 || sudo -n pct destroy "${vmid}" >/dev/null 2>&1; then
            entries+="{\"kind\":\"container\",\"vmid\":${vmid},\"hostname\":\"${hostname}\",\"removed\":true},"
        else
            entries+="{\"kind\":\"container\",\"vmid\":${vmid},\"hostname\":\"${hostname}\",\"removed\":false},"
            ok=false
        fi
    done

    local path
    shopt -s nullglob
    for path in "${scratch}"/* "${state_root}"/*/; do
        [[ -d "${path}" ]] || continue
        sudo -n chown -R "$(id -un):$(id -gn)" "${path}" 2>/dev/null || true
        rm -rf "${path}"
        entries+="{\"kind\":\"path\",\"path\":\"${path%/}\",\"removed\":true},"
    done
    shopt -u nullglob

    mkdir -p "$(dirname "${report}")"
    printf '{"ok":%s,"removed":[%s]}\n' "${ok}" "${entries%,}" >"${report}"
    [[ "${ok}" == true ]]
}

# --- scratch ----------------------------------------------------------------------------------

# Create <scratch>/<run_id>/<mount-key> for every mount of <service> in the derived tfvars.
# Usage: lab_scratch_create <run_id> <service> <derived.tfvars> <report.json>
lab_scratch_create() {
    local run_id="${1:?}" service="${2:?}" tfvars="${3:?}" report="${4:?}"
    local base keys key
    base="$(lab_scratch_root)/${run_id}"
    keys="$(python3 - "${tfvars}" "${service}" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
svc = re.escape(sys.argv[2])
m = re.search(r"service_mountpoints\s*=\s*\{(.*)\n\}", text, re.S)
if m:
    s = re.search(rf"^ {{2}}{svc}\s*=\s*\{{(.*?)^ {{2}}\}}\s*$", m.group(1), re.S | re.M)
    if s:
        for k in re.findall(r"^\s{4}([\w-]+)\s*=\s*\{", s.group(1), re.M):
            print(k)
PY
)" || return 1
    mkdir -p "${base}"
    local json=""
    for key in ${keys}; do
        mkdir -p "${base}/${key}"
        sudo -n chown 100000:100000 "${base}/${key}" || return 1
        json+="\"${key}\":\"${base}/${key}\","
    done
    if [[ -n "${json}" ]]; then
        mkdir -p "$(dirname "${report}")"
        printf '{%s}\n' "${json%,}" >"${report}"
    fi
}

# --- plan guards ------------------------------------------------------------------------------

# A lab plan may only hold LXCs on vmbr99; a prod plan none on vmbr99.
# Usage: lab_bridge_invariant <env> <plan.json>
lab_bridge_invariant() {
    local env="${1:?}" plan="${2:?}"
    python3 - "${env}" "${plan}" <<'PY'
import json, sys
env, plan = sys.argv[1:3]
bad = []
for rc in json.load(open(plan, encoding="utf-8")).get("resource_changes") or []:
    if rc.get("type") != "proxmox_lxc" or rc["change"].get("actions") == ["delete"]:
        continue
    for net in (rc["change"].get("after") or {}).get("network") or []:
        on_lab = net.get("bridge") == "vmbr99"
        if (env == "lab") != on_lab:
            bad.append(f"{rc['address']} bridge={net.get('bridge')}")
if bad:
    which = "must all be on vmbr99" if env == "lab" else "must not be on vmbr99"
    print(f"bridge invariant ({env}): LXCs {which}: " + ", ".join(bad), file=sys.stderr)
    sys.exit(1)
PY
}

# Refuse when the host cannot keep the margin free after the copy starts.
# Usage: lab_capacity_check <plan.json> <report.json>
lab_capacity_check() {
    local plan="${1:?}" report="${2:?}"
    python3 - "${plan}" "${report}" "${MEMINFO_PATH:-/proc/meminfo}" "${LAB_MEMORY_MARGIN_MIB:-6144}" <<'PY'
import json, re, sys
plan, report, meminfo, margin = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
need = 0
for rc in json.load(open(plan, encoding="utf-8")).get("resource_changes") or []:
    if rc.get("type") == "proxmox_lxc" and "create" in (rc["change"].get("actions") or []):
        need += int((rc["change"].get("after") or {}).get("memory") or 0)
avail = int(re.search(r"^MemAvailable:\s+(\d+) kB", open(meminfo, encoding="utf-8").read(), re.M).group(1)) // 1024
ok = avail - need >= margin
json.dump({"mem_available_mib": avail, "copy_memory_mib": need, "margin_mib": margin, "ok": ok},
          open(report, "w", encoding="utf-8"))
if not ok:
    print(f"lab copy needs {need} MiB; host has {avail} MiB available; at least {margin} MiB must stay free",
          file=sys.stderr)
    sys.exit(1)
PY
}

# Bind-mount policy: prod allows only /mnt/nas/, lab only the lab scratch root.
# Usage: bind_mount_policy_check <env> <plan.json> <report.txt>   (prints violations to stderr)
bind_mount_policy_check() {
    local env="${1:?}" plan="${2:?}" report="${3:?}"
    python3 - "${env}" "${plan}" "${report}" "$(lab_scratch_root)" <<'PY'
import json, sys
env, plan, report, scratch = sys.argv[1:5]
prefix = scratch.rstrip("/") + "/" if env == "lab" else "/mnt/nas/"
bad = []
for rc in json.load(open(plan, encoding="utf-8")).get("resource_changes") or []:
    after = (rc.get("change") or {}).get("after") or {}
    for mp in after.get("mountpoint") or []:
        vol = mp.get("volume")
        if isinstance(vol, str) and vol.startswith("/") and not vol.startswith(prefix):
            bad.append((rc["address"], vol))
with open(report, "w", encoding="utf-8") as f:
    if bad:
        f.write(f"DENY: Host-path bind mount(s) outside allowed prefix {prefix}\n")
        f.writelines(f"{a}\t{v}\n" for a, v in bad)
    else:
        f.write(f"ALLOW: host-path bind mounts (if any) are under {prefix}\n")
if bad:
    for _, vol in bad:
        label = "lab" if env == "lab" else "prod"
        print(f"bind-mount policy ({label}): {vol} is not under {prefix}", file=sys.stderr)
    sys.exit(1)
PY
}

# --- teardown ---------------------------------------------------------------------------------

# Refuse to destroy anything in a lab state that is not a lab copy.
# Usage: lab_destroy_guard <lab state file>
lab_destroy_guard() {
    local state="${1:?}"
    [[ -f "${state}" ]] || return 0
    python3 - "${state}" <<'PY'
import json, re, sys
path = sys.argv[1]
for res in json.load(open(path, encoding="utf-8")).get("resources") or []:
    for inst in res.get("instances") or []:
        a = inst.get("attributes") or {}
        if res.get("type") != "proxmox_lxc":
            ok = False
        else:
            nets = a.get("network") or [{}]
            ip = str((nets[0] or {}).get("ip") or "").split("/")[0]
            m = re.fullmatch(r"10\.99\.0\.(\d+)", ip)
            ok = (
                str(a.get("hostname") or "").startswith("lab-")
                and (nets[0] or {}).get("bridge") == "vmbr99"
                and bool(m) and 200 <= int(m.group(1)) <= 254
            )
        if not ok:
            addr = f"{res.get('module') + '.' if res.get('module') else ''}{res.get('type')}.{res.get('name')}"
            print(f"refusing to destroy: lab state {path} contains a resource that is not a lab copy ({addr})",
                  file=sys.stderr)
            sys.exit(1)
PY
}

# Destroy the lab copy and everything the run made. Always writes <report>.
# Usage: lab_teardown <service> <run_id> <tfvars> <report.json> [terraform-destroy-cmd...]
# The destroy command (default: terraform destroy) is a parameter so callers pin their root.
lab_teardown() {
    local service="${1:?}" run_id="${2:?}" tfvars="${3:?}" report="${4:?}"
    shift 4
    local state="$(lab_state_root)/${service}/terraform.tfstate"
    local destroyed_by=none vmid="" ok=true scratch_removed=false state_removed=false

    if [[ -f "${state}" ]]; then
        vmid="$(python3 - "${state}" <<'PY'
import json, sys
for r in json.load(open(sys.argv[1], encoding="utf-8")).get("resources") or []:
    if r.get("type") == "proxmox_lxc":
        for i in r.get("instances") or []:
            print(str(i["attributes"].get("id", "")).split("/")[-1]); raise SystemExit
PY
)"
        if ! lab_destroy_guard "${state}"; then
            ok=false
        else
            if (("$#" > 0)) && "$@" -state="${state}" -var-file="${tfvars}" >/dev/null 2>&1; then
                destroyed_by=terraform
            elif [[ -n "${vmid}" ]]; then
                sudo -n pct stop "${vmid}" >/dev/null 2>&1 || true
                sudo -n pct destroy "${vmid}" --purge >/dev/null 2>&1 && destroyed_by=pct || true
            fi
            if [[ -n "${vmid}" ]] && sudo -n pct config "${vmid}" >/dev/null 2>&1; then
                ok=false
            fi
        fi
    fi

    local scratch="$(lab_scratch_root)/${run_id}"
    if [[ -d "${scratch}" ]]; then
        sudo -n chown -R "$(id -un):$(id -gn)" "${scratch}" 2>/dev/null || true
        rm -rf "${scratch}" && scratch_removed=true
    else
        scratch_removed=true
    fi
    if [[ "${ok}" == true ]]; then
        rm -rf "$(lab_state_root)/${service}" && state_removed=true
    fi

    mkdir -p "$(dirname "${report}")"
    printf '{"destroyed_by":"%s","vmid":"%s","scratch_removed":%s,"lab_state_removed":%s,"ok":%s}\n' \
        "${destroyed_by}" "${vmid}" "${scratch_removed}" "${state_removed}" \
        "$([[ "${ok}" == true && "${scratch_removed}" == true && "${state_removed}" == true ]] && echo true || echo false)" \
        >"${report}"
    [[ "${ok}" == true && "${scratch_removed}" == true && "${state_removed}" == true ]]
}

# --- isolation probe --------------------------------------------------------------------------

# Prove the lab copy cannot reach production, from inside it. Targets: contracts/lab-network.md.
# Usage: lab_isolation_probe <vmid> <report.json>
lab_isolation_probe() {
    local vmid="${1:?}" report="${2:?}"
    local -a targets=(
        "192.168.1.214 9090 blocked" "192.168.1.222 80 blocked" "192.168.1.109 2049 blocked"
        "192.168.1.112 8006 blocked" "10.99.0.1 22 blocked" "deb.debian.org 443 open"
    )
    local t host port expected observed ok all_ok=true json="" broken=""
    for t in "${targets[@]}"; do
        read -r host port expected <<<"${t}"
        if sudo -n pct exec "${vmid}" -- timeout 3 bash -c "</dev/tcp/${host}/${port}" >/dev/null 2>&1; then
            observed=open
        else
            observed=blocked
        fi
        ok=true
        if [[ "${observed}" != "${expected}" ]]; then
            ok=false
            all_ok=false
            [[ "${expected}" == blocked ]] && broken+="${host}:${port} "
        fi
        json+="{\"target\":\"${host}:${port}\",\"expected\":\"${expected}\",\"observed\":\"${observed}\",\"ok\":${ok}},"
    done
    mkdir -p "$(dirname "${report}")"
    printf '[%s]\n' "${json%,}" >"${report}"
    if [[ -n "${broken}" ]]; then
        local first="${broken%% *}"
        echo "lab isolation broken: ${first} reachable from lab copy" >&2
    elif [[ "${all_ok}" != true ]]; then
        echo "lab isolation probe: the internet is unreachable from the lab copy" >&2
    fi
    [[ "${all_ok}" == true ]]
}

# --- inventory guard --------------------------------------------------------------------------

# Every ansible_host in a layered inventory must be in 10.99.0.0/24 (JSON from ansible-inventory --list).
# Usage: lab_inventory_guard <inventory.json> <report.txt>
lab_inventory_guard() {
    local inv="${1:?}" report="${2:?}"
    python3 - "${inv}" "${report}" <<'PY'
import ipaddress, json, sys
inv, report = sys.argv[1:3]
hv = json.load(open(inv, encoding="utf-8")).get("_meta", {}).get("hostvars", {})
net = ipaddress.ip_network("10.99.0.0/24")
bad = None
lines = []
for host, v in sorted(hv.items()):
    addr = v.get("ansible_host")
    if not addr:
        continue
    try:
        inside = ipaddress.ip_address(addr) in net
    except ValueError:
        inside = False
    lines.append(f"{host} {addr} {'ok' if inside else 'OUTSIDE'}")
    if not inside and bad is None:
        bad = (host, addr)
open(report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
if bad:
    print(f"lab inventory resolves {bad[0]} to {bad[1]}, outside 10.99.0.0/24", file=sys.stderr)
    sys.exit(1)
PY
}
