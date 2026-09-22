# ~~A LAB-path `monitoring` deploy silently wipes production monitoring~~ — RESOLVED

**Status**: **RESOLVED 2026-09-20**, same day. Guards added at two layers, both tested.
**Impact while live**: one `gh workflow run lxc-deploy-lab.yml -f service=monitoring`
removed all 16 scrape jobs and 5 alert groups from the **production** Prometheus, and the
run reported success.

## What happened

Deploying `monitoring` through the LAB path rendered the Prometheus scrape config and the
service alert rules with **zero services**, and wrote them to the production monitoring
host at `192.168.1.214`.

```
BEFORE: blackbox-exporter, blackbox-https(7), caddy,
        fail2ban-exporter-{jellyfin,nextcloud,reverse-proxy}, financial-scenario-gui,
        immich-api, immich-microservices, jellyfin-exporter, llm-router,
        llm-router-readiness, nextcloud-exporter, node-exporter(7), prometheus, telegraf-snmp
AFTER:  blackbox-exporter, blackbox-https(7), node-exporter(1), prometheus, telegraf-snmp
```

Alert groups `llm-router_alerts`, `immich_alerts`, `nextcloud_alerts`,
`reverse_proxy_alerts` and `financial-scenario_alerts` all disappeared. Confirmed after the
fact with `count_over_time(prometheus_rule_group_rules[20h])`: 2396 samples against 2400
for the three static groups.

No service was down. Monitoring was blind for roughly 40 minutes; the blackbox HTTPS probes
kept working throughout because they are defined statically, not from contracts.

## Root cause

`scripts/lab/pve-service-deploy` already guarded against this and said so in a comment:

```bash
# A per-service deploy only generates a single-host inventory, so without this the
# monitoring stack silently drops every other service's targets/alerts/dashboards.
local committed_inventory="${REPO_ROOT}/ansible/inventories/${ENVIRONMENT}/hosts.yml"
```

**The guard keys on `${ENVIRONMENT}`.** With `--environment lab` it resolves to
`ansible/inventories/lab/hosts.yml`, which holds only `lab-pve-01` and has **no `services`
group at all**. The layering therefore added nothing, and `groups['all']` reached the
templates with no service hosts in it.

Measured: `services.hosts` is **8** under the prod inventory and **1** under the lab one.

### Why it destroyed rather than no-opped

| consumer | kind | effect with an empty loop |
|---|---|---|
| `templates/prometheus.yml.j2` | template | renders an empty config **over** the working one |
| `templates/service_alerts.yml.j2` | template | same — `groups:` with nothing beneath it |
| `tasks/provision_dashboards.yml` | copy loop | harmless no-op — which is why all 8 dashboards survived |

A template does not skip when its loop is empty. It renders emptiness.

### Why nothing caught it

1. **`verify.yml` cannot see it.** It checks containers are `Up`, ports listen and
   `/-/ready` returns 200 — all true of a Prometheus monitoring nothing. The deploy was
   green.
2. **A LAB run can reach the PROD host.** `inventories/generated/hosts.yml` is built from
   Terraform state and read `monitoring: 192.168.1.214`. This is
   [`067`](./067-lab-prod-same-address-space.md) — LAB ≡ PROD address space — causing real
   damage rather than hypothetical. **Treat this as evidence when 067 is revisited:** a run
   explicitly labelled LAB reconfigured production.

## The fix

### Layer 1 — `scripts/lab/pve-service-deploy`

Keep the layering; then **verify it worked** rather than assuming a readable file implies a
useful one. After building `inventory_args`, enumerate with `ansible-inventory` and `die`
unless the `services` group holds more than the target host alone.

Group membership is the signal here, not `monitoring_contract`: `ansible-inventory` has no
playbook context and will not resolve `ansible/host_vars/`, so a contract-based count at
that point always reads zero. A failed enumeration is also fatal, with its own message —
deploying blind is the thing being prevented.

### Layer 2 — `ansible/roles/monitoring_stack/tasks/main.yml`

Independent of any script, and placed **before** `compose_stack` so it stops while the live
config is intact. Inside the role `hostvars` is fully populated, so it asserts on the thing
that actually matters: at least one host besides the monitoring host declaring
`monitoring_contract.enabled`. Escape hatch `monitoring_allow_empty_contracts` defaults
false.

One wrinkle worth keeping: `assert` resolves **both** `fail_msg` and `success_msg` eagerly,
so an unset fact turns the careful explanation into a Jinja `undefined` error at exactly
the wrong moment. The list is initialised in its own task for that reason.

### Tested, both directions

The two guard tasks are tagged `always`, so a non-matching `--tags` exercises them with no
possibility of rendering anything:

```
lab  inventory -> FAILED: "no host besides monitoring declares monitoring_contract.enabled
                 ... Inventory visible to this run: 2 host(s) — lab-pve-01, monitoring"
prod inventory -> ok:     "6 service contract(s) visible: financial-scenario, immich,
                 jellyfin, llm-router, nextcloud, reverse_proxy"
```

Then a full idempotent re-run: `ok=101 changed=0 failed=0`.

## Restored state

16 jobs, 28 targets, 0 unhealthy, 8 rule groups, `llm-router_alerts` at 6 rules.

Restoring meant running the monitoring play with the prod inventory layered first. Note for
anyone repeating it: vault files are gitignored and live in a store on `pve`
(`/var/lib/homelab-proxmox/vault/group_vars/<group>/vault.yml`); `pve-service-deploy`
symlinks them into the tree for the run and removes them after
(`link_vault_file_if_needed`). A hand-run playbook must do the same or it fails on the
Pushover credential assertion.

## Still open — the `verify.yml` gap

`verify.yml` still reports success on a Prometheus that monitors nothing. Layer 2 checks
the **inputs** before rendering; a post-deploy check on active target count and loaded rule
groups would check the **outcome**, and would catch any future cause rather than this one.
Not built — the two guards close the known path, and this is the belt to their braces.

## Also open — the PROD promote pipeline trips its own guard, and reports success

Found 2026-09-22 deploying `080`, and **measured** rather than predicted — the first
reading of this was wrong in the direction that matters, so the evidence is below.

`.github/workflows/lxc-promote-prod.yml:196` runs the LAB stage with no per-service
branching:

```
./pve-service-deploy apply --environment lab --service '${service}'
```

For `service=monitoring` that is precisely the invocation Layer 1 refuses. Run
[35739864863](https://github.com/lightenup/homelab-proxmox/actions/runs/35739864863),
`Apply (LAB)` step, in order:

```
module.monitoring_lxc.proxmox_lxc.this: Refreshing state... [id=pve/lxc/103]
    "monitoring" = "192.168.1.214/24"
PLAY [Bootstrap Ansible User]  ...  monitoring : ok=5 changed=0 ... failed=0
ERROR: Refusing to deploy monitoring: the layered inventory exposes 1 host(s) in
the 'services' group, so every other service's scrape targets, alert rules and
dashboards would render EMPTY over the live config.
##[error]Process completed with exit code 1.
##[error]LAB apply failed. See evidence pack for details (RUN_ID=lab-monitoring-...)
```

The guard works. `monitoring.yml` never ran — only a Terraform refresh and the bootstrap
play (5 tasks, `changed=0`) got that far. Production was verified intact afterwards: 31
active targets across 17 jobs, 9 rule groups, 26 rules.

**The problem is the reporting, not the guard.** `continue-on-error: true` at line 181
means that failed step, its job `Apply (LAB)`, and the **entire promote run** all report
`success`. Every one of the job's 13 steps shows `success` in the API. The failure survives
only in two places an operator has to go looking for: the step summary (`## LAB apply
failed`) and the job's `ok` output, which is what `Prod 2 - LXC Apply` actually gates on —
it refuses without `allow_override_failed_lab_gate: true`.

So the trap is a **green promote run that certifies nothing**. Read at a glance it says
"LAB verified, safe to promote"; in fact the LAB stage deployed nothing at all for this
service and never can. The override flag then has to be set on every single monitoring
deploy, which makes it indistinguishable in the run history from overriding a gate that
failed for a real reason — the failure mode `074` already demonstrated for a different
always-on condition.

Note the second sighting of [`067`](./067-lab-prod-same-address-space.md) in the log above:
the *LAB* stage refreshed the LXC holding **192.168.1.214**, the production monitoring host.
Nothing was written, because the guard stopped the play — but the address the lab path
resolves to is still the production one.

Three ways out, cheapest first:

1. Skip the LAB stage for `monitoring` (`if: inputs.service != 'monitoring'`), so the run
   is honestly green and the override flag keeps meaning what it says.
2. Substitute a LAB **plan** for the LAB apply on this service — exercises rendering
   without writing.
3. Give the lab inventory the service hosts, which is really `067`'s problem and the only
   option that removes the special case rather than encoding it.
