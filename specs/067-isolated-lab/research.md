# Research: Real isolated lab for the gated pipeline (067)

**Date**: 2026-10-30 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

These are the findings from reading the code and the `pve` host on 2026-10-30. Each one is
recorded as a decision with its reason and the alternatives that were rejected. Nothing in the
Technical Context is still marked NEEDS CLARIFICATION.

## Facts measured on `pve` (2026-10-30)

| Fact | Value |
|---|---|
| Host memory | 31 GB, about 20 GB available, 8 cores. Configured LXC memory 36 GB, about 11 GB used |
| `vmbr99` | `10.99.0.1/24`, `bridge-ports none`, `post-up` MASQUERADE of `10.99.0.0/24` out of `vmbr0`; `ip_forward=1`. Managed by `ansible/playbooks/lab_setup.yml` (block `LAB NETWORK`) |
| Used on `vmbr99` | `.1` (host), `.10`, `.11` (lab-rig VMs). Mirrored lab addresses `.211`–`.222` are free |
| Firewall | No Proxmox firewall (`/etc/pve/firewall/` empty). `nft` and `iptables-nft` installed. No rule restricts `vmbr99` today |
| State today | `/var/lib/homelab-proxmox/state/services/<svc>`: 7 real directories (eurooffice, financial-scenario, hermes, llm-router, market-model, nextcloud, ntfy) and 5 symlinks into `/mnt/nas/homelab_ci/infra_state/lab/<svc>` (homeassistant, immich, jellyfin, monitoring, reverse_proxy), all **production**. `infra_state/prod/{immich,monitoring,reverse_proxy}` are unused leftovers from 2026-02-09 |
| Combined root | `terraform/main.tf` still declares 10 per-service `module "*_lxc"` blocks (the obsolete resources FR-013 names) |
| tfvars | `/var/lib/homelab-proxmox/tfvars/{lab,prod}.tfvars` (0600, `ci`). The lab file differs from prod only in comments and in missing mounts: same bridge, gateway and addresses |
| Fresh LXC | about 100 s; image pulls about 27 MB/s. Images: hermes 12.1 GB, eurooffice 7.2, immich 5.0, homeassistant 3.5, monitoring 3.5, llm-router 3.35, nextcloud 2.6, the rest under 0.5 |
| `ci` sudo | NOPASSWD only for `pct`, `qm`, `pvesm`, `pvesh`, `systemctl`, `journalctl`, `mkdir`, `chown`, `chmod`, `tee`. **Not** `nft`/`iptables`: firewall rules are installed by root Ansible, never by the pipeline |

## R-001 Lab copy identity: name, address, VMID

**Decision**: Each service root gets one new variable, `hostname_prefix` (default `""`). The lab
tfvars set it to `"lab-"`, so a lab copy is `lab-ntfy` on `vmbr99` at `10.99.0.222/24`, gateway
`10.99.0.1`. The VMID is left to Proxmox (next free), as it is today. No module change is needed:
`bridge`, `ip` and `gateway` are already variables.

**Rationale**: The duplicate-CT guard (`scripts/lab/lib/ct_conflicts.sh`) compares hostname and IP.
A lab copy with the production hostname would be denied as a clash. A distinct hostname and a
distinct address keep the guard unchanged and still let it deny a second `lab-ntfy` (FR-016). The
`lab-` prefix plus bridge `vmbr99` together also identify a lab copy for the sweeper (R-006).

**Alternatives**: Teaching the guard to ignore `vmbr99`. Rejected: that weakens the guard, and a
leftover lab copy would then slip past. Fixed lab VMIDs (for example 9100+). Rejected: the provider
would need a `vmid` variable in all 12 roots, and the hostname-plus-bridge identity already works.

## R-002 Lab tfvars: derived from prod, not maintained by hand

**Decision**: `pve-service-deploy` writes a per-run lab tfvars file into the run's evidence
(redacted copy) and a 0600 temp file. It starts from `prod.tfvars` and overrides only:
`services_bridge = "vmbr99"`, `network_gateway = "10.99.0.1"`, `hostname_prefix = "lab-"`,
`service_ips` with every entry mirrored (`192.168.1.N/24` → `10.99.0.N/24`), and
`service_mountpoints` with each `volume` replaced by the run's scratch directory (R-005). The
hand-kept `lab.tfvars`, `lab.tfvars.template` and `lab.tfvars.example` are removed.

**Rationale**: Today's lab tfvars is a stale near-copy of prod. It has already drifted (missing
mounts), and nothing keeps the two in step. Deriving the lab values means a new service gets a lab
copy automatically (FR-001 edge case "first run for a brand-new service"). The mirror rule is
deterministic, so FR-002 is satisfied by construction. Lab addresses collide only if `.N` is
already used on `vmbr99`. The check refuses `.1`, `.10` and `.11`, and the lab-rig range.

**Alternatives**: Keep a committed `lab.tfvars.template` with lab values. Rejected: it duplicates
12 addresses and every mount, and it drifts. Generate it in Ansible. Rejected: the script already
owns tfvars provisioning (`lib/tfvars.sh`), and Ansible does not run before Terraform here.

## R-003 State layout and location (absorbs 096)

**Decision**:

```text
/var/lib/homelab-proxmox/state/
├── prod/<svc>/terraform.tfstate   # durable; backed up nightly (proxmox_backup)
└── lab/<svc>/terraform.tfstate    # exists only during a LAB run; removed after teardown
```

Both live on the host's local disk. `lib/state.sh` resolves `state/<env>/<svc>`. The
`USE_NAS_STATE` branch, the `state/services` legacy root, the 5 symlinks and the whole
`/mnt/nas/homelab_ci/infra_state/{lab,prod}` tree are removed after migration (R-012). The
`proxmox_backup` role collects `state/prod/**`. Its NAS `infra_state` collector and its
symlink-skipping logic go away.

**Rationale**: The constitution's State Management baseline is "local on the PVE host, backed up to
Synology". The NAS-resident half of today's layout breaks that rule, and it is the half that is
misnamed `lab/`. A single local layout with honest names meets FR-012 and the constitution. The
nightly config backup already copies local state (verified 2026-10-30, manifest 22→39 files).

**Alternatives**: `infra_state/{lab,prod}` on the NAS for everything. Rejected: it contradicts the
constitution, and a NAS outage would block every deploy. Keep lab state for debugging. Rejected:
a lab state outliving its copy is exactly the "tracked by a state but no container" drift FR-014
reports. The evidence pack keeps the plan and a state pull for debugging.

## R-004 LAN isolation mechanism (FR-007, FR-008)

**Decision**: Root Ansible installs a dedicated nftables table, `inet lab_isolation`, from
`lab_setup.yml`'s network block, which already owns `vmbr99`. It is loaded by `post-up` on
`vmbr99` and persisted as `/etc/nftables.d/lab-isolation.nft`. Rules:

- `forward`, `iifname "vmbr99"`: `ct state established,related accept`; drop `ip daddr` in
  `192.168.0.0/16`, `172.16.0.0/12`, `10.0.0.0/8` (except `10.99.0.0/24` itself) and
  `100.64.0.0/10` (Tailscale CGNAT); accept the rest (internet, through the existing MASQUERADE).
- `input`, `iifname "vmbr99"`: `ct state established,related accept`; drop the rest. The host
  connects *to* lab copies (SSH, health checks); lab copies never open connections to the host.

**Isolation exceptions (the list FR-007 asks for): none.** Name resolution uses `1.1.1.1`
(`nameserver` in tfvars), so DNS needs no LAN exception. Package and image downloads go to the
internet. If implementation finds a dependency on a LAN address, it is added to
[contracts/lab-network.md](./contracts/lab-network.md) with its reason, in the same change.

**Verification (FR-008)**: every LAB run, after the deploy, runs inside the lab copy:
a 3-second TCP connect (`bash /dev/tcp`) to `192.168.1.214:9090` (monitoring), `192.168.1.222:80` (ntfy), `192.168.1.109:2049`
(NAS) and `192.168.1.112:8006` (host API). Each must fail. It also runs one internet fetch, which
must succeed. Results go to `reports/lab/isolation.json`. Any reachable production target fails
the run.

**Rationale**: The pipeline user cannot run `nft` (no sudo), which is right: rules are host
configuration, so Ansible owns them (constitution III). A separate table leaves the existing
`iptables-nft` MASQUERADE untouched and is easy to inspect (`nft list table inet lab_isolation`).

**Risk to check in implementation**: the lab-rig VMs (`.10`, `.11`) share `vmbr99`. Their workflow
(`lab-rig.yml`) must still pass with the isolation in place. If it needs a LAN destination, it gets
a source-scoped exception for `.10`/`.11` only, never for the lab-copy range.

**Alternatives**: Proxmox firewall (`pve-firewall`). Rejected: it is not enabled on this host, and
enabling it changes every container's filtering. Per-container firewall in the lab copy. Rejected:
root in the lab copy could undo it. A second NAT-less bridge with no uplink. Rejected: lab copies
need the internet for image pulls.

## R-005 Scratch storage instead of NAS mounts (FR-006)

**Decision**: For each `service_mountpoints[<svc>]` entry, the lab tfvars point `volume` at
`/var/lib/homelab-proxmox/lab-scratch/<run_id>/<mount-key>`. That is an empty directory created by
the script (`sudo mkdir`, `sudo chown 100000:100000` for the unprivileged idmap). The bind-mount
policy (`enforce_bind_mount_policy`) becomes environment-aware. For `prod`, the allowed prefix
stays `/mnt/nas/`. For `lab`, the only allowed prefix is `/var/lib/homelab-proxmox/lab-scratch/`,
and `/mnt/nas/` is **denied**. Read-only mounts stay read-only. The run directory is removed in
teardown, and the sweeper removes stale run directories.

**Rationale**: The roles' "mount is present" checks pass because a directory is mounted. A lab copy
can never see a share, because the policy refuses any `/mnt/nas/` path in lab, not merely because
the tfvars happen to avoid one.

**Constitution impact**: The constitution's Tier-2 enforcement text names the allowlist as "rejects
host paths outside `/mnt/nas/`". The new rule for lab is narrower (it rejects `/mnt/nas/` and allows
only the scratch root). The constitution's sentence needs a one-line amendment (plan,
Complexity Tracking).

## R-006 Teardown, leftovers and the scheduled sweep (FR-003)

**Decision**:

1. **In-run teardown**: an `EXIT` trap in the lab path runs `terraform destroy` against the lab
   state. If that fails, it runs `pct stop` + `pct destroy` on the VMID recorded in the lab state.
   It then removes the scratch directory and the lab state directory. Teardown runs on pass, fail
   and `SIGTERM`.
2. **Destroy guard**: before any destroy, the script asserts that every `proxmox_lxc` in the lab
   state has bridge `vmbr99`, an address in `10.99.0.0/24` and a hostname starting with `lab-`.
   Otherwise it refuses to destroy and fails loudly. This is the barrier the constitution's
   CI/CD Expectations ask of destructive automation.
3. **Pre-run sweep**: before creating a lab copy, the run removes every container that matches
   **all** of: hostname `lab-*`, `net0` on `vmbr99`, address in the mirrored range
   (`10.99.0.200`–`.254`). It also removes every `lab-scratch/*` and `state/lab/*` left behind.
4. **Scheduled sweep**: the same sweep runs nightly from the drift-check timer (R-008) before the
   comparison. Leftovers it removes are still counted and reported (FR-014: "lab copies found
   outside a running LAB run count as leftovers"). A run lock prevents it from sweeping during an
   active LAB run (R-007).

**Rationale**: An aborted runner cannot run its own trap, so the next run (or the nightly timer)
must clean up. Matching on three attributes means the sweeper cannot hit a production container or
a lab-rig VM: those are `qm` VMs, and the sweep uses `pct` only.

**Alternatives**: Proxmox tags as the marker. Rejected: telmate 2.9.11's `proxmox_lxc` support for
`tags` is unverified, and hostname plus bridge plus address is already unambiguous.

## R-007 One lab copy at a time, and the 6 GB memory margin (FR-004)

**Decision**: The lab path takes an exclusive `flock` on `/var/lib/homelab-proxmox/state/lab/.lock`
for the whole run, and the nightly sweep takes the same lock. After the plan and before the apply,
it reads `MemAvailable` from `/proc/meminfo` and the planned container's `memory` (MiB) from the
plan JSON. It refuses when `MemAvailable − memory < 6144 MiB`, with the message
`lab copy needs <M> MiB; host has <A> MiB available; at least 6144 MiB must stay free`. The figures
go to `reports/lab/capacity.json`.

**Rationale**: There is a single runner today, but the lock also covers a laptop run racing the
pipeline (constitution V). The memory figure comes from the plan, so it is always the configured
size, never a guess.

## R-008 Nightly CT-vs-state check (FR-014)

**Decision**: A script `scripts/lab/state-drift-check` (Bash, sourcing `ct_conflicts.sh`'s
`ct_inventory`) runs from a systemd timer on `pve` as `ci`, nightly at 06:30, after the 05:xx
backups. It:

1. takes the lab lock and runs the scheduled sweep (R-006);
2. lists containers (`ct_inventory`) and, for each `state/prod/<svc>/terraform.tfstate`, the
   `proxmox_lxc` VMIDs it tracks (from `vmid` in the state; read-only `jq`, no Terraform call);
3. reports untracked containers (on the host, in no prod state), double-tracked containers (in
   two or more prod states) and leftover lab copies (swept by step 1), by name and VMID, in its
   journal output and in `/var/lib/homelab-proxmox/artifacts/state-drift/latest.json`;
4. writes a node_exporter textfile `/var/lib/node_exporter/textfile_collector/state_drift.prom`:

   ```text
   homelab_state_drift_containers{kind="untracked"} 0
   homelab_state_drift_containers{kind="double_tracked"} 0
   homelab_state_drift_containers{kind="lab_leftover"} 0
   homelab_state_drift_last_success_timestamp_seconds 1.7619e+09
   ```

Two rules join `backup_alerts.yml.j2`'s file (same path to the phone):
`StateDriftContainers` (`sum by (kind) (homelab_state_drift_containers) > 0`, for 0m) and
`StateDriftCheckStale` (`time() - homelab_state_drift_last_success_timestamp_seconds > 26*3600`).
Production containers that are deliberately outside Terraform (if any) are listed in
`scripts/lab/state-drift-ignore.txt` with a reason. The expected list is empty.

**Rationale**: This copies the backup-staleness pattern that already works end to end (091): a
textfile metric on the host, an alert in the existing rule file, delivered to the phone. Reading
VMIDs from state files avoids Terraform calls and credentials in a nightly timer.

**Alternatives**: A GitHub Actions scheduled workflow. Rejected: it competes with the single runner
(mutation jobs) and needs SSH. A Terraform `plan` per service. Rejected: it is slow (12 inits), it
needs the API token, and it does not see containers that no state tracks.

## R-009 Production fingerprint (FR-021)

**Decision**: A function `prod_fingerprint <out.json>` in a new `scripts/lab/lib/fingerprint.sh`
records:

- `sha256` of every `state/prod/<svc>/terraform.tfstate`;
- for every container that is **not** a lab copy (R-006 match): VMID, status, and the `sha256` of
  `pct config <vmid>` with the volatile `lock:` line removed, plus the hostname and `net*` lines in
  clear text;
- `sha256` of `prod.tfvars`.

It is taken after the pre-run sweep and before the lab plan (`reports/lab/fingerprint.before.json`),
and again after teardown (`fingerprint.after.json`). Any difference writes `fingerprint.diff.txt`
and fails the run with `reason=production changed during LAB run`, which sets `lab_gate_failed`.

**Rationale**: It covers exactly what FR-021 lists. `pct config` is static unless something changes
the container, so it does not flap. Status catches a stop or restart. A tfstate checksum catches
any write to production state, including a `serial` bump from a refresh.

**Alternatives**: Comparing `terraform show` output. Rejected: it needs init and credentials, and
a refresh could itself write state.

## R-010 Ansible in lab: inventory and address overrides (FR-005, FR-009, FR-010, FR-017)

**Decision**:

- `ansible/inventories/lab/hosts.yml` lists the 12 services under `services` at their mirrored
  lab addresses, keeps `lab_inventory: true`, and keeps the lab-rig hosts as they are. The main
  play's layered inventory (`-i inventories/lab/hosts.yml -i inventories/generated/hosts.yml`)
  then gives the monitoring lab copy real targets (FR-017).
- A committed vars file, `ansible/inventories/lab/lab-overrides.yml`, passed as
  `-e @inventories/lab/lab-overrides.yml`, sets `deploy_environment: lab` and overrides every `<svc>_ip`, `monitoring_host_ip` and
  `reverse_proxy_ip` to the mirrored lab address. A role that waits on `{{ homeassistant_ip }}`, or
  a config that points at `{{ llm_router_ip }}`, then targets the lab network, never production.
  A test asserts that every `*_ip` in `group_vars/services/vars.yml` has a lab override, so a new
  service cannot forget one.
- `-e deploy_environment=lab` stays on the command line too, because existing gates read it
  (`lxc_base`, `alloy`, `monitoring_stack`, `hermes_agent_operational`).
- New gates with the existing idiom `(deploy_environment | default('prod')) != 'lab'`:
  `service_backup` role invocations in the 6 playbooks that use it (FR-009: no backup timers);
  the reverse proxy's DNS-01/ACME block (FR-011, R-011); the llm-router's Tailscale sidecar
  (FR-011); Alertmanager receivers (FR-011).
- Health checks already resolve the target from the generated inventory (`healthcheck.py` →
  `ansible_host` + `healthcheck_url`/`healthcheck_path`), which the lab state fills with the lab
  address. `host_vars/llm-router.yml` and `host_vars/market-model.yml` contain literal
  `192.168.1.x` URLs in `monitoring_contract`. Those are Prometheus targets (not deployed in lab,
  and rendered only for prod), so they are left alone. The lab-overrides test excludes
  `monitoring_contract`.

**Rationale**: The `*_ip` values live in `ansible/group_vars/services/vars.yml`. Group vars next to
the lab inventory would lose to them under Ansible's precedence rules, so they cannot reliably
override them. Extra-vars always win, so the overrides go in one file passed with `-e @…`, kept
under `inventories/lab/` so it is plainly lab-only. With the overrides, a forgotten
cross-service reference resolves to a non-existent lab address, which the isolation (R-004)
blocks anyway, instead of to production.

**Alternatives**: Templating every role on `deploy_environment`. Rejected: it touches every role,
while one overrides file covers every reference.

## R-011 Per-service lab switches (FR-011)

| Service | Production integration | Lab behaviour | Switch |
|---|---|---|---|
| reverse_proxy | Caddy `acme_dns domeneshop` (public certs, DNS-01 via Domeneshop API) | Global `local_certs` (Caddy's internal CA); no `acme_dns`; `domeneshop.env` not written | `Caddyfile.j2` + `tasks/main.yml` on `deploy_environment` |
| llm-router | Tailscale userspace sidecar (auth key); paid provider keys | No `tailscale` service in compose; provider keys present (FR-010) but no calls are made: the lab check is `/health/liveliness` only, not readiness (which calls providers) | `docker-compose.yml.j2` on `deploy_environment`; lab health path |
| monitoring | Alertmanager → email + Pushover | Only the `null` receiver, and every route goes to it | `alertmanager.yml.j2` on `deploy_environment` |
| hermes | ntfy push, heartbeat, Home Assistant MCP | Already PROD-only via `hermes_agent_operational` (083/095) | none new |
| others | none that act on the internet with prod credentials | unchanged | none |

A guardrail test lists the vault variables that are internet credentials (`domeneshop_*`,
`tailscale_*`, `pushover_*`, `smtp_*`, provider API keys). It fails if a template that uses one is
not covered by a `deploy_environment` gate or by an entry in this table. This enforces "a service
added later MUST declare its lab switch" (FR-011).

## R-012 State migration procedure (FR-013)

**Decision**: There is one supervised script, `scripts/lab/migrate-state-067`, run once by the
operator on `pve` as `ci`. It replaces the obsolete `migrate-state-to-nas.sh` and is deleted again
in the clean-up PR. For each of the 12 services, in a fixed order (small services first, then
nextcloud, immich, hermes, and finally monitoring and reverse_proxy):

1. Copy the resolved current state (following symlinks) to
   `/var/lib/homelab-proxmox/state-backup-067-<date>/<svc>/`.
2. Copy it into `state/prod/<svc>/terraform.tfstate` (0600, `ci`).
3. Run `pve-service-deploy plan --environment prod --service <svc>` (new layout).
4. Require `No changes` (`-detailed-exitcode` 0). If the result is anything else, stop:
   services already done stay done, and the rest are untouched.

After all 12 report no changes in the same session:

- remove `state/services/` (5 symlinks and 7 directories), `infra_state/lab`, and `infra_state/prod`;
- remove the 10 `module "*_lxc"` blocks from `terraform/main.tf` and `terraform state rm` them
  from the combined root's state (no destroy). Their real resources are managed by the per-service
  roots. The combined-root state location is confirmed at the start of implementation;
- trigger the PVE config backup and check that the manifest lists `state/prod/<svc>` for all 12.

The procedure is in [quickstart.md](./quickstart.md), section M.

**Rationale**: It meets the owner decision (all 12 at once, each verified). The copy-first rule
means no step is destructive until every service is proven. The combined-root step is a
`state rm`, so even a wrong address cannot delete a container.

## R-013 Pipeline and workflow changes (FR-015, FR-018, FR-020)

**Decision**:

- `lxc-promote-prod.yml`: the job "Apply (LAB, changes prod)" becomes "LAB rehearsal (isolated)".
  It calls the same `pve-service-deploy apply --environment lab`, which now runs the ephemeral
  path. Its timeout grows for large images (SC-004): the job timeout is 90 minutes. "Plan (PROD)"
  is unchanged in its call, but it now plans against `state/prod` and shows the real change.
  `lab_gate_failed` also turns true on a fingerprint diff or a failed isolation check.
- `lxc-deploy-lab.yml` and `lxc-promote-lab.yml` are deleted. References are removed from the live
  docs (`README.md`, `AGENTS.md`, `docs/**`, runbooks, `scripts/**`, `python/tests/**`, other
  workflows). Historical `specs/0NN-*/` documents are records of past features and stay as they
  are. A guardrail test fails on any reference outside `specs/`.
- `lxc-lifecycle.yml`: for `environment=lab`, `add` and `change` call the lab path. `delete` fails
  in the first step with "no standing lab copy exists; LAB is an ephemeral rehearsal (067)".
- `lab-integration-tests.yml` and `nightly-deeper-verification.yml` are checked for calls into
  the removed workflows and for assumptions about `state/services`.
- The 2026-10-28 "LAB changes prod" wording in workflow names, summaries and docs is replaced.

## R-014 Laptop parity (FR-019)

**Decision**: The lab path stays inside `pve-service-deploy`, which already runs from a laptop by
SSH to `pve` (constitution V; `AGENTS.md`). The documented laptop command is the same
`ssh pve 'cd ~/homelab-proxmox/scripts/lab && … ./pve-service-deploy apply --environment lab
--service <svc>'` with the vault password and token passed on stdin, exactly as the workflow does.
These parts are host-only and are documented as such: the nftables isolation and the nightly
drift-check timer (both root Ansible, `host_proxmox`/`lab_setup`). Their laptop equivalent is
`ansible-playbook playbooks/lab_setup.yml --tags lab-network` from the laptop against `pve` as
root (password SSH, as with `backup_proxmox.yml`).

## R-015 Time budget (SC-004)

Measured: about 100 s for a fresh LXC, plus the image pull at about 27 MB/s, plus the role run.
That is at most 2 + 7.5 + ~5 ≈ 15 minutes for hermes (12.1 GB). The 90-minute job timeout leaves
headroom. `pve-service-deploy`'s own Ansible and health-check retry windows are unchanged.
Teardown takes about 20 s.
