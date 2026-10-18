# Research: Confidence Suite Trim

## R1 — Is `hypervisor-nested-workload` really a superset of the other two profiles?

**Decision**: Yes, so the confidence suite runs only that profile.

**Rationale** (from the code):
- `parse_profile` (`scripts/lab/pve-lab`) sets three values per profile:
  - `bootstrap` = tier 1, `min`, `standard`
  - `control-plane` = tier 2, `min`, `standard`
  - `nested-workload` = tier 2, `plus`, `strict`
- `cmd_test` behaves the same way for each tier:
  - Every tier runs Tier 0 (`terraform fmt`, Ansible syntax check) and then Tier 1 (`lab_bootstrap.yml`).
  - Tier 2 also runs `lab_tier2_pve.yml`.
- `plus` only enables the `Tier 2 Plus - Nested Workload` block (`when: tier2_mode == 'plus'`). Nothing is gated on `min`.
- `strict` safety adds orphan-VM and host-memory checks on top of `standard` (`validate_safety_profile`). The standard checks still run.
- The guardrails and cleanup verification are the same for every profile.

**Lost**: CI no longer runs the tier-1 template (VMID 9001) or a cold clone of it. That template isn't used for anything outside the lab. The profile stays available via `pve-lab suite bootstrap`.

**Alternatives considered**:
- Keep `bootstrap` as a fast fail-first step. Rejected: nested-workload runs the same bootstrap first and fails at the same point, so this adds about 2m40 for nothing.

## R2 — What does the suite actually read from the repo?

**Decision**: The path list below.

| Path | Why |
|---|---|
| `scripts/lab/pve-lab` | entrypoint |
| `scripts/lab/lib/{checks,jsonl,provenance,evidence,artifacts,sudo,cleanup,rebuild}.sh` | sourced directly by `pve-lab` |
| `scripts/lab/lib/state.sh` | sourced by `rebuild.sh` and `guardrails.sh` |
| `scripts/lab/checks.d/` | `deps.sh` is sourced; `catalog.json` is read by `ci-verify.sh` |
| `scripts/lab/guardrails.sh` | run by `cmd_run` |
| `scripts/lab/profiles.d/` | `ci-sudoers.conf` and the profile files |
| `scripts/lab/contracts/` | schemas checked by `verify_evidence.py` |
| `scripts/lab/{ci-verify.sh,verify_evidence.py,fetch_evidence_pack.sh,render_failure_evidence.sh,render_github_annotations.sh}` | run by the suite job itself |
| `scripts/lab/create_tier2_template.sh` | builds the template the suite clones |
| `ansible/playbooks/lab_*.yml` | the playbooks |
| `ansible/inventories/lab/` | `-i` inventory, also grepped by `guardrails.sh` |
| `ansible/group_vars/{all,proxmox_hosts,lab}/` | loaded through the `ansible/playbooks/group_vars -> ../group_vars` symlink. The lab host is in `lab` and `proxmox_hosts`. |
| `ansible/roles/assertion_utils/` | `include_role` in both playbooks |
| `ansible/ansible.cfg` | `ANSIBLE_CONFIG` is exported by `pve-lab` |
| `ansible/requirements.yml` | conservative: Galaxy content |
| `.github/workflows/lxc-promote-prod.yml`, `scripts/ci/confidence-suite-paths.txt` | changes to the gate itself |

**Not read** (so they no longer trigger the suite):
- `terraform/**`: only `fmt -check` runs on it, which PR CI already does.
- `ansible/inventories/{prod,generated}/`
- `ansible/roles/lxc_base/` and the other service roles
- `ansible/group_vars/{services,monitoring}`
- `scripts/lab/pve-service-deploy` and the plan renderers
- `lib/{tfvars,snapshot,rebuild_state,promotion_tokens,evidence_paths}.sh`
- `lib/{check_record,ansible-check-bridge}.sh`: nothing the suite runs references them.

**Replay** (2026-07-01 → 2026-10-18 promotes): fab0723 matches through `group_vars/all`. Every other promote misses.

**Alternatives considered**:
- Record a manifest of the files the suite actually opens, using `strace`/`openat` during a run. Deferred: it's more precise, but needs harness changes and a place to store the manifest. The static closure test below catches the main drift risk.
- Broad `scripts/lab/` match. Rejected: about 60% of that directory isn't used by the suite.

## R3 — Where should the list live, and how does the gate read it?

**Decision**: `scripts/ci/confidence-suite-paths.txt` holds one ERE per line, with `#` comments and blank lines allowed. The gate strips comments and blanks into a temporary pattern file and runs `grep -qEf`. If the cleaned list is empty or missing, the gate decides `run=true`.

**Rationale**:
- An empty pattern line in `grep -f` matches everything. That fails safe, but the comment and blank lines still need stripping so the list is meaningful.
- A plain text file is readable by both bash and Python without any parsing library.

**Alternatives**:
- Keep the regex inline and have the test parse the workflow YAML. Rejected: it's brittle, and a one-line regex for about 16 alternatives isn't reviewable.

## R4 — How should the drift guard find dependencies?

**Decision**: A static parse in pytest:
- **Bash**: the regex `(?:source|bash)\s+"\$\{(LIB_DIR|SCRIPT_DIR|REPO_ROOT)\}/([^"]+)"`, applied to `pve-lab`, `guardrails.sh` and `lib/rebuild.sh`. The variable is resolved to its directory, and only plain path tails count (variable-free).
- **Ansible roles**: `include_role`/`import_role` `name:` values in `ansible/playbooks/lab_*.yml`, resolved to `ansible/roles/<name>/`. Collection roles (names with dots) are ignored.
- **Group vars**: for every group in `ansible/inventories/lab/hosts.yml`, plus `all`, check `ansible/group_vars/<group>/` when it exists.

Each resolved path, plus a probe file inside each directory, must match at least one list pattern.

**Rationale**: This covers the three ways a new dependency can be added in practice, and fails with the uncovered path named.
