#!/usr/bin/env bash
# fingerprint.sh - prove a LAB run left production untouched (067, R-009, SC-001).
#
#   prod_fingerprint <out.json> <phase>        phase: before | after
#   fingerprint_diff <before> <after> <diff.txt>   exit 0 when equal; writes <diff.txt> only on a difference
#
# A fingerprint holds the sha256 of every production state and of prod.tfvars, and for every
# container that is not a lab copy: status, net lines, a hash of `pct config` without `lock:`
# (a backup lock must not look like a change), and the workload identity of its Docker containers.
# Needs ct_conflicts.sh sourced first (ct_inventory, is_lab_copy).
# Env: STATE_ROOT (default /var/lib/homelab-proxmox/state), TFVARS_DIR (default .../tfvars).

prod_fingerprint() {
    local out="${1:?prod_fingerprint requires an output path}"
    local phase="${2:?prod_fingerprint requires a phase}"
    local work vmid
    work="$(mktemp -d)"

    : >"${work}/containers.tsv"
    while read -r vmid; do
        [[ -n "${vmid}" ]] || continue
        is_lab_copy "${vmid}" && continue
        local config status workload
        config="$(sudo -n pct config "${vmid}" 2>/dev/null)" || config=""
        status="$(sudo -n pct list 2>/dev/null | awk -v v="${vmid}" '$1 == v {print $2}')"
        if [[ "${status}" == "running" ]]; then
            workload="$(set -o pipefail; sudo -n pct exec "${vmid}" -- sh -c \
                "command -v docker >/dev/null 2>&1 || { echo __NODOCKER__; exit 0; }; docker ps -a --no-trunc --format '{{.ID}} {{.CreatedAt}} {{.Names}}'" \
                2>/dev/null | sort)" || workload="__UNREADABLE__"
            [[ -n "${workload}" ]] || workload="__NODOCKER__"
        else
            workload="__NOTRUNNING__"
        fi
        printf '%s\n' "${config}" >"${work}/${vmid}.config"
        printf '%s\n' "${workload}" >"${work}/${vmid}.workload"
        printf '%s\t%s\n' "${vmid}" "${status:-unknown}" >>"${work}/containers.tsv"
    done < <(ct_inventory | awk -F'\t' '!seen[$1]++ {print $1}')

    python3 - "${work}" "${out}" "${phase}" "${STATE_ROOT:-/var/lib/homelab-proxmox/state}" \
        "${TFVARS_DIR:-/var/lib/homelab-proxmox/tfvars}" <<'PY'
import glob, hashlib, json, os, re, sys
from datetime import datetime, timezone

work, out, phase, state_root, tfvars_dir = sys.argv[1:6]

def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def file_sha(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return sha(f.read())
    except OSError:
        return "missing"

states = {
    os.path.basename(os.path.dirname(p)): file_sha(p)
    for p in sorted(glob.glob(os.path.join(state_root, "prod", "*", "terraform.tfstate")))
}
containers = []
with open(os.path.join(work, "containers.tsv"), encoding="utf-8") as f:
    rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]
for vmid, status in sorted(rows, key=lambda r: int(r[0])):
    config = open(os.path.join(work, f"{vmid}.config"), encoding="utf-8").read()
    kept = [l for l in config.splitlines() if l.strip() and not l.startswith("lock:")]
    workload = [l for l in open(os.path.join(work, f"{vmid}.workload"), encoding="utf-8").read().splitlines() if l]
    mapped = {"__NODOCKER__": ["none"], "__UNREADABLE__": ["unreadable"], "__NOTRUNNING__": ["not-running"]}
    hostname = next((l.split(None, 1)[1] for l in kept if l.startswith("hostname:")), "-")
    containers.append({
        "vmid": int(vmid),
        "hostname": hostname,
        "status": status,
        "net": [l for l in kept if re.match(r"net\d+:", l)],
        "config_sha256": sha("\n".join(kept).encode()),
        "workload": mapped.get(workload[0], workload) if workload else ["none"],
    })

doc = {
    "schema_version": "1.0.0",
    "taken_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "phase": phase,
    "states": states,
    "tfvars_prod": file_sha(os.path.join(tfvars_dir, "prod.tfvars")),
    "containers": containers,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2, sort_keys=True)
    f.write("\n")
PY
    rm -rf "${work}"
}

fingerprint_diff() {
    local before="${1:?fingerprint_diff requires before}"
    local after="${2:?fingerprint_diff requires after}"
    local diff_out="${3:?fingerprint_diff requires an output path}"
    local rc=0
    python3 - "${before}" "${after}" "${diff_out}" <<'PY' || rc=$?
import json, sys

before, after, diff_out = sys.argv[1:4]
a, b = (json.load(open(p, encoding="utf-8")) for p in (before, after))
lines = []

def cmp(label, x, y):
    if x != y:
        lines.append(f"{label}: {x} -> {y}")

for svc in sorted(set(a["states"]) | set(b["states"])):
    cmp(f"states.{svc}", a["states"].get(svc, "absent"), b["states"].get(svc, "absent"))
cmp("tfvars_prod", a["tfvars_prod"], b["tfvars_prod"])

ca = {c["vmid"]: c for c in a["containers"]}
cb = {c["vmid"]: c for c in b["containers"]}
for vmid in sorted(set(ca) | set(cb)):
    x, y = ca.get(vmid), cb.get(vmid)
    if x is None:
        lines.append(f"container {vmid} ({y['hostname']}): appeared")
        continue
    if y is None:
        lines.append(f"container {vmid} ({x['hostname']}): disappeared")
        continue
    for key in ("hostname", "status", "net", "config_sha256", "workload"):
        cmp(f"container {vmid} ({x['hostname']}) {key}", x[key], y[key])
    # An unreadable workload proves nothing about production, so it always fails.
    if "unreadable" in y["workload"]:
        lines.append(f"container {vmid} ({x['hostname']}) workload: unreadable (cannot prove unchanged)")

lines = list(dict.fromkeys(lines))
if lines:
    open(diff_out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    sys.exit(1)
PY
    return "${rc}"
}
