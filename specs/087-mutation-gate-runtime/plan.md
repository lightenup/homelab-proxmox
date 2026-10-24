# Implementation Plan: Mutation Gate Runtime

**Branch**: `087-mutation-gate-runtime` | **Date**: 2026-10-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/087-mutation-gate-runtime/spec.md`

## Summary

Make the mutation gate fast enough that it no longer blocks the only runner, and make the nightly
work again. The work ships as two PRs:

- **PR 1, the nightly fix (FR-002)**: remove the `run_on_pve` and `run_mutmut` inputs and the
  runner-local mutation steps from `nightly-deeper-verification.yml`, so a scheduled run does the
  PVE path. Still on mutmut 2. PR 1 changes only that workflow file, so today's `^python/` gate
  does not fire. Its guard test lands with PR 2.
- **PR 2, the migration**: move to mutmut 3.8. Both the PR gate and the nightly do a fresh full run,
  which took 39 s on `pve` in the planning trial (research R1). The nightly publishes `main`'s results
  to the NAS with an atomic swap, and alerts through a new ntfy publisher when the score is below
  the gate line. A Taskfile task pulls the results to the Mac. The floor is reset from a measured run
  (61.81% on `9d80372`, proposed floor 61.0).

Planning changed the spec in two places. The PR gate scores from scratch instead of seeding from
`main` (owner, 2026-10-24), which withdrew FR-005. And the alert test uses a manual floor override,
because the nightly runs only on `main` (SC-005).

## Technical Context

**Language/Version**: Bash, GitHub Actions YAML, Python 3.11 (gate venv on `pve` and in CI), Python
3.15 (Mac `.venv`), INI (`setup.cfg`), Taskfile v3, Ansible YAML (one `ntfy_users` entry).

**Primary Dependencies**: mutmut `3.8.0` (replaces `2.5.1`; adds libcst, textual, setproctitle,
coverage, click), pytest 9 (pytest-xdist and pytest-cov are no longer used by the gate), `uv` for the
venv and lock, `curl`, `rsync`, `act`.

**Storage**: NAS share `/mnt/nas/homelab_ci` on `pve`: new `mutmut/` tree (about 1.2 MB per set, two
sets kept). The old `mutmut-cache/` is pruned (FR-011).

**Testing**: pytest guard tests under `python/tests/workflows/` (path list, nightly inputs, report
script). `act -l` and `act -n` for the two workflows. The gate script run on the Mac against the
same commit as CI. The quickstart scenarios.

**Target Platform**: `pi-ci` self-hosted runner (orchestrates), `pve` (runs mutmut over SSH as
`ci`), the dev Mac.

**Project Type**: CI and tooling for an infrastructure repo. No service and no LXC.

**Performance Goals**: PR mutation job under 5 minutes from start (SC-002). Measured: 39 s for
mutmut itself. The rest is rsync and `uv pip sync`, as today. Mac module re-test under 1 minute
(SC-004).

**Constraints**: one self-hosted runner. `git push` is blocked on the Mac (land through `gh api`,
see `AGENTS.md`). PVE has no `.git` in its synced copy. Self-hosted jobs need the existing
owner/fork guard (memory: public repo). No new third-party actions.

**Scale/Scope**: 18 orchestrator modules, 4,117 mutants, 158 tests in the mutation run.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Spec-driven | ✅ | `specs/087-*`. Both PRs reference `tasks.md`. The spec was updated in this planning cycle. |
| II. Secrets | ✅ | `ntfy_mutation_token` and its hash live only in vault. The token is read on the runner, masked, and sent only in the `Authorization` header. It never reaches PVE (R8). |
| III. Separation | ✅ | No Terraform. One Ansible data change (`ntfy_users` in role defaults). Nothing provisions machines. |
| IV. Code economy | ✅ | Net removal: the inputs, runner-local steps, `.mutmut-cache` logic and `mutmut.ini` go. New files each have one current consumer and are required: `setup.cfg` (mutmut reads only root config), the `src` symlink (mutmut finds source only there), `scripts/ci/mutation-gate-paths.txt` (follows `086`'s tested path-list pattern), `scripts/ci/mutmut_report.py` (moves the score and report logic out of inline shell so it can be unit-tested), and `docs/operations/mutation-testing.md`. No incremental mode, no seeding, no staleness logic (R2). |
| V. Parity | ✅ | `scripts/ci/mutmut-threshold.sh` is the single gate command on the Mac, on PVE and in CI. Documented one-context items, each with its local equivalent: the regression alert is CI-only (on the Mac the script prints the same summary); publishing to the NAS is CI-only, done by the nightly on `main` (the Mac reads the set with `task mutmut:pull`, or produces the same results with the gate script); `task mutmut:pull` is Mac-only (CI has no use for it). The nightly's `min_score` input is validated as a number before it reaches the remote shell. All three limitations are written in `docs/operations/mutation-testing.md`. |
| Local workflow testing | ✅ | `act -l` and `act -n` for both workflows (quickstart §0). |
| Test-driven changes | ✅ | Guard tests for the path list, the nightly's input independence and the report script. Non-destructive checks: the gate script on the Mac, a draft-PR run. |
| Token tiers | ✅ | Unaffected. The `ci` account and SSH as today. |

Re-check after Phase 1: unchanged. The design adds no indirection and no second code path.

## Project Structure

### Documentation (this feature)

```text
specs/087-mutation-gate-runtime/
├── spec.md
├── plan.md                      # this file
├── research.md                  # trial numbers, mutmut 3.8 behaviour, decisions R1–R11
├── data-model.md                # published set, floor, survivor report, score
├── quickstart.md                # validation scenarios per success criterion
├── contracts/
│   ├── published-results.md     # NAS layout, report.json, publish procedure
│   ├── gate-script.md           # mutmut-threshold.sh env, behaviour, exit codes
│   └── regression-alert.md      # ntfy publisher `mutation`, message format
├── checklists/requirements.md
└── tasks.md                     # /speckit-tasks
```

### Source Code (repository root)

```text
# PR 1 — nightly fix
.github/workflows/nightly-deeper-verification.yml   # drop inputs + runner-local steps
python/tests/workflows/test_workflow_inputs.py      # extend: no `if:` in the nightly depends on inputs

# PR 2 — migration
setup.cfg                                           # NEW: [mutmut] config (research R4)
src -> python/src                                   # NEW: symlink (research R4)
python/mutmut.ini                                   # DELETE
python/requirements-nightly.txt                     # mutmut>=3.8,<4
python/requirements-nightly.lock.txt                # recompiled, same uv command as its header
python/mutmut-threshold.txt                         # new floor + formula comment (R6)
scripts/ci/mutmut-threshold.sh                      # rewrite (contracts/gate-script.md)
scripts/ci/mutmut_report.py                         # NEW: stats + .meta -> report.json, survivors.txt
scripts/ci/mutation-gate-paths.txt                  # NEW: trigger include/exclude list (R9)
.github/workflows/mutation.yml                      # path list, drop cache steps, fresh run
.github/workflows/nightly-deeper-verification.yml   # fresh run, publish, alert, min_score input
python/tests/orchestrator/test_cli.py               # sys.executable + package PYTHONPATH (R4)
python/tests/orchestrator/test_runner_plan_apply.py # same
python/tests/orchestrator/test_provenance_mismatch.py # same
python/tests/orchestrator/test_exec.py              # sys.executable
python/tests/task_smoke/helpers.py                  # package PYTHONPATH (R4, fifth caller)
python/tests/workflows/test_mutation_gate_paths.py  # NEW: drift guard for the path list
python/tests/workflows/test_mutmut_report.py        # NEW: score/report on fixture .meta files
Taskfile.yml                                        # NEW task mutmut:pull
.gitignore                                          # + mutants/  (drop .mutmut-cache lines)
ansible/roles/ntfy/defaults/main.yml                # + ntfy_users entry `mutation`
ansible/group_vars/services/vault.yml               # + ntfy_mutation_token/_password_hash (owner, vault edit)
docs/operations/mutation-testing.md                 # NEW: the Mac loop, the gate, the alert
docs/operations/README.md                           # link the new doc
docs/backlog/087-mutation-gate-runtime.md           # status → specified/implemented
```

**Structure Decision**: No new directories. CI logic stays in `scripts/ci/` beside the existing
gate script and the `086` path list. Tests go in `python/tests/workflows/`, which the mutation run
excludes (they import nothing from the package).

## Design

### PR 1: nightly fix (US1, FR-002)

1. Delete the `run_mutmut` and `run_on_pve` inputs. Keep `workflow_dispatch:` with no inputs.
2. Remove every `if: ${{ inputs.run_on_pve }}` guard, so those steps always run. Delete the steps
   guarded by `!inputs.run_on_pve` (`Prepare mutmut shared cache`, `Mutation testing (mutmut)`).
3. Make the `gate` job's `no-new-commits` skip apply only to `schedule` events, so a manual run
   always runs (R5).
4. Add `timeout-minutes: 120` to the `deeper` job. A mutmut 2 run takes about an hour, and the
   133-minute PR run shows it can hang.
5. Guard test, written and seen to fail during PR 1 but committed at the start of PR 2: in `test_workflow_inputs.py`, assert that no `if:` in the nightly references
   `inputs.`, and that the workflow declares no inputs other than those an allowlist names (empty
   in PR 1, `min_score` in PR 2).

### PR 2: migration

**Configuration (R4)**. Add `setup.cfg` with the trial's `[mutmut]` values and the `src` symlink.
Delete `python/mutmut.ini`. Fix the five subprocess callers. Add `mutants/` to `.gitignore`.
Recompile the nightly lock with the command in its header.

**Gate script (contracts/gate-script.md)**. `mutmut-threshold.sh` reads the floor, deletes
`mutants/`, runs `mutmut run` and `mutmut export-cicd-stats`, then calls
`"$PYTHON_BIN" scripts/ci/mutmut_report.py` to write `report.json` and `survivors.txt`, print the
summary and return the exit code. `mutmut_report.py` uses only the standard library and reads
`mutmut-cicd-stats.json` and the `.meta` files. Its survived/killed/no-tests mapping follows
mutmut's `status_by_exit_code`, and the unit test pins it against fixture files.

**PR gate (`mutation.yml`, US2, US3)**:
- `gate` job: `git diff --name-only` against the merge base, minus the `!` exclude lines of
  `scripts/ci/mutation-gate-paths.txt`, matched against its include lines with `grep -qEf`. If the
  list is missing or empty, run (prefer a false run over a false skip, as `086`).
- `mutation` job: same owner/fork guard. Rsync the repo to PVE, excluding `.git`, `artifacts/`,
  `.venv` and `mutants/`. `uv pip sync` the venv. Run the gate script with
  `MUTMUT_COMMIT=${{ github.event.pull_request.head.sha || github.sha }}`. Copy `report.json` back
  and append the summary to `GITHUB_STEP_SUMMARY`. Remove both `.mutmut-cache` steps. Add
  `timeout-minutes: 20`.
- `result` job: unchanged.

**Nightly (US1, US5, FR-003, FR-009)**:
- Input `min_score` (string, optional). `MUTMUT_MIN_SCORE: ${{ inputs.min_score }}` is empty on a
  schedule, which leaves the committed floor in force. A runner-side step checks a non-empty value
  against `^[0-9]{1,3}(\.[0-9]+)?$` before it is used in the SSH command.
- Steps, in order:
  1. Check the NAS mount on PVE (the existing check).
  2. Run the gate script on PVE with `MUTMUT_COMMIT=${{ github.sha }}`, recording its exit code
     without failing the step.
  3. If the exit code is 0 or 1, publish (contracts/published-results.md) as a remote bash heredoc.
  4. If it is 1, read the token from vault the way `version-currency.yml` does, and post the alert
     (contracts/regression-alert.md).
  5. Fail the job if the exit code is not 0, or if the publish failed.
- Drop the steps nothing uses. The nightly does only mutation testing, so the Ansible Galaxy
  installs, `Setup Python (GitHub-hosted only)`, `Debug runner + mounts` and `Upload artifacts` (which
  uploaded the runner's empty workspace) all go. Keep the runner's `Install nightly dependencies`:
  the alert step needs `ansible-vault` from it.
- `timeout-minutes: 30` (was 120 in PR 1).

**Mac pull (US4, FR-008)**. `task mutmut:pull` (`MUTMUT_PULL_HOST` defaults to `ci@pve`):
1. `rsync -a "$host:/mnt/nas/homelab_ci/mutmut/main/"` into `mktemp -d`.
2. Check that `report.json` exists and has `schema` 1.
3. Delete the result files in `./mutants/`, copy the new set in, and print commit and age.

Any failure exits non-zero before step 3, so `./mutants/` is untouched.

**ntfy publisher (R8)**. Add the `ntfy_users` entry. The owner adds two vault values and deploys
ntfy following `docs/runbooks/ntfy-add-publisher.md`, which includes extending `082`'s SC-002 check
matrix. The nightly's alert step needs both.

**Floor (R6)**. On the migration PR's head, run the gate script on the Mac and take the PR's CI
score. Set the floor to that score rounded down to a whole point, and write the formula and the
no-tests rule as comments.

**Prune (FR-011)**. After PR 2 merges and one mutmut 3 nightly has published:
`ssh ci@pve 'rm -rf /mnt/nas/homelab_ci/mutmut-cache'`, listing the directory first (memory:
look before deleting). This is an operator task in `tasks.md`, not code.

### Rollout order

1. PR 1 → merge → manual nightly → next scheduled nightly green (quickstart §1).
2. ntfy publisher vault values (owner), before PR 2 merges. The ntfy **deploy** waits until after the merge and runs from `main` (step 4), so no later prod deploy from `main` drops the account.
3. PR 2 → CI gate on itself (it changes `mutation.yml` and `setup.cfg`, so it triggers) → floor from
   the measured score → merge.
4. Deploy ntfy from `main` (owner) → manual nightly on `main` → published set → `task mutmut:pull` → `min_score=99` alert test
   (quickstart §5, §6).
5. Prune the mutmut 2 caches (quickstart §7). Update the backlog item's status.

## Risks

| Risk | Mitigation |
|---|---|
| PR 2's own gate run runs the old `mutation.yml`. | No: `pull_request` workflows run from the PR's head, so the new workflow and script run. Its run is the first real measurement. |
| The `.meta` exit-code mapping changes in a mutmut release. | Pinned to 3.8.0 in the lock. `test_mutmut_report.py` pins the mapping, and a bump PR touches the lock, which triggers the gate. |
| Load on `pve` slows the run. | Measured at nice 19 on an idle host. A 5-minute target leaves about 7× headroom over 39 s, plus setup. |
| The score moves after the subprocess fixes. | The floor is set from the PR's own measurement, not from the trial (R6). |
| The `pi-ci` Python lacks a dependency for `mutmut_report.py`. | Stdlib only. It runs on PVE inside the gate venv anyway. |

## Complexity Tracking

No violations to justify.
