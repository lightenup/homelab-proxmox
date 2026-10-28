#!/usr/bin/env bash
# ct_conflicts.sh - refuse a plan that creates an LXC whose hostname or IP is already in use
# on this Proxmox host.
#
# Terraform only knows about containers in its own state. A container created by hand, or by
# a state that was lost, is invisible to it, so a plan for a service with empty state will
# happily create a second container with the same IP. That is what happened with Home
# Assistant on 2026-10-28 (stray VMID 104 + new VMID 112, both 192.168.1.212).
#
# Usage: enforce_no_ct_conflicts <plan.json> <report-file>
# Returns 0 when nothing conflicts (or nothing is created), 1 on a conflict.

# Print "<address>\t<hostname>\t<ip-without-prefix>" for every proxmox_lxc the plan creates
# from scratch. A replace (delete+create) reuses its own slot, so it is not a new container.
planned_lxc_creates() {
    local plan_json="${1:?planned_lxc_creates requires plan.json}"
    python3 - "${plan_json}" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as f:
    plan = json.load(f)
for rc in plan.get("resource_changes") or []:
    if rc.get("type") != "proxmox_lxc":
        continue
    actions = rc.get("change", {}).get("actions") or []
    if "create" not in actions or "delete" in actions:
        continue
    after = rc["change"].get("after") or {}
    ips = [str(n.get("ip") or "").split("/")[0] for n in after.get("network") or []]
    ips = [ip for ip in ips if ip and ip not in ("dhcp", "manual")] or ["-"]
    for ip in ips:
        print(f"{rc['address']}\t{after.get('hostname') or '-'}\t{ip}")
PY
}

# Print "<vmid>\t<hostname>\t<ip-without-prefix>" for every container on this host (one line
# per network interface). `pct list` columns are VMID Status [Lock] Name; only VMID is used.
ct_inventory() {
    local vmid config hostname ip
    for vmid in $(sudo -n pct list 2>/dev/null | awk 'NR>1 {print $1}'); do
        config="$(sudo -n pct config "${vmid}" 2>/dev/null)" || continue
        hostname="$(awk '/^hostname:/ {print $2; exit}' <<<"${config}")"
        local found=false
        while read -r ip; do
            [[ -z "${ip}" ]] && continue
            printf '%s\t%s\t%s\n' "${vmid}" "${hostname:--}" "${ip}"
            found=true
        done < <(grep -E '^net[0-9]+:' <<<"${config}" | grep -oE '(^|,)ip=[^,]+' | sed -E 's/^,?ip=//; s#/.*##' | grep -vE '^(dhcp|manual)$')
        [[ "${found}" == true ]] || printf '%s\t%s\t-\n' "${vmid}" "${hostname:--}"
    done
}

# Compare planned creates against the inventory. Prints one line per conflict.
# Args: <planned-tsv-file> <inventory-tsv-file>
find_ct_conflicts() {
    local planned="${1:?find_ct_conflicts requires planned tsv}"
    local inventory="${2:?find_ct_conflicts requires inventory tsv}"
    awk -F'\t' '
        NR == FNR { host[$2] = host[$2] " " $1; if ($3 != "-") ip[$3] = ip[$3] " " $1; next }
        {
            if ($2 != "-" && ($2 in host)) printf "%s: hostname %s already used by CTID(s)%s\n", $1, $2, host[$2]
            if ($3 != "-" && ($3 in ip))   printf "%s: IP %s already used by CTID(s)%s\n", $1, $3, ip[$3]
        }
    ' "${inventory}" "${planned}" | sort -u
}

enforce_no_ct_conflicts() {
    local plan_json="${1:?enforce_no_ct_conflicts requires plan.json}"
    local report="${2:?enforce_no_ct_conflicts requires a report path}"
    local tmp planned inventory conflicts
    tmp="$(mktemp -d)"
    planned="${tmp}/planned.tsv"
    inventory="${tmp}/inventory.tsv"

    if ! planned_lxc_creates "${plan_json}" >"${planned}"; then
        echo "DENY: could not read planned LXC creates from ${plan_json}" >"${report}"
        rm -rf "${tmp}"
        return 1
    fi
    if [[ ! -s "${planned}" ]]; then
        echo "ALLOW: plan creates no new LXC" >"${report}"
        rm -rf "${tmp}"
        return 0
    fi

    ct_inventory >"${inventory}"
    if [[ ! -s "${inventory}" ]]; then
        # An empty inventory on a host that runs a dozen containers means pct failed (sudo),
        # not that the host is empty. Fail closed: this check exists to stop silent duplicates.
        {
            echo "DENY: could not list existing containers (sudo -n pct list/config returned nothing)"
            echo "Planned creates:"
            cat "${planned}"
        } >"${report}"
        rm -rf "${tmp}"
        return 1
    fi

    conflicts="$(find_ct_conflicts "${planned}" "${inventory}")"
    if [[ -n "${conflicts}" ]]; then
        {
            echo "DENY: the plan creates an LXC whose hostname or IP is already in use on this host"
            echo "${conflicts}"
            echo
            echo "Terraform state does not track the existing container. Either import it:"
            echo "  terraform import -state=<state> <address> <node>/lxc/<vmid>"
            echo "or, if it is a stray, confirm it holds nothing and destroy it (pct destroy <vmid>)."
        } >"${report}"
        rm -rf "${tmp}"
        return 1
    fi

    {
        echo "ALLOW: no hostname/IP conflict for planned creates"
        cat "${planned}"
    } >"${report}"
    rm -rf "${tmp}"
    return 0
}
