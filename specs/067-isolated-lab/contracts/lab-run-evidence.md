# Contract: LAB run evidence additions

The evidence pack layout stays `service-deploy-runs/lab-<svc>-<sha>-<ts>/` (fetched and verified by
`fetch_evidence_pack.sh` and `ci-verify.sh`). The lab path adds `reports/lab/`:

| File | Content | Required |
|---|---|---|
| `sweep.json` | containers, scratch dirs and lab states removed by the pre-run sweep | always |
| `fingerprint.before.json` / `fingerprint.after.json` | data-model *Production fingerprint* | always (after: even on failure) |
| `fingerprint.diff.txt` | unified diff; written only when the fingerprints differ | on difference |
| `capacity.json` | `{mem_available_mib, copy_memory_mib, margin_mib: 6144, ok}` | when a plan exists |
| `scratch.json` | `{mount_key: path}` | when the service has mounts |
| `copy.json` | `{vmid, hostname, ip}` | when created |
| `isolation.json` | probe results (see `lab-network.md`) | when created |
| `teardown.json` | `{destroyed_by: "terraform"\|"pct"\|"none", vmid, scratch_removed, lab_state_removed, ok}` | always |
| `skipped-checks.txt` | checks skipped in lab, with the reason (dependency unavailable, no user data) | when any |

`reports/apply/summary.txt` gains `reason=` values for the new failures: `capacity`, `isolation`,
`teardown` and `fingerprint`. `lxc-promote-prod.yml` treats any `status=failed` as
`lab_gate_failed=true` (unchanged logic, wider input).

`ci-verify.sh` (offline) requires, for `environment=lab`: both fingerprint files, `teardown.json`
with `ok: true`, and no `fingerprint.diff.txt`. Otherwise verification fails.
