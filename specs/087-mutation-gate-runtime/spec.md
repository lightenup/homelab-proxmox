# Feature Specification: Mutation Gate Runtime

**Feature Branch**: `087-mutation-gate-runtime`

**Created**: 2026-10-24

**Status**: Implemented (2026-10-24). All required code tasks are done and merged (or in review);
`tasks.md`'s Rollout record tracks what remains: two owner-only steps (T027: vault secrets for the
`mutation` ntfy account; T033: deploy ntfy from `main` once T027 is done) and the live/time-gated
checks that depend on them or on a nightly run actually happening (T034, T035, T038, T040, T042,
T043).

**Input**: User description: "087-mutation-gate-runtime.md Prompt me". The source is the backlog item
[`docs/backlog/087-mutation-gate-runtime.md`](../../docs/backlog/087-mutation-gate-runtime.md)
(raised 2026-10-18, revised 2026-10-22, refreshed 2026-10-23).

## Context

The mutation gate checks how well the orchestrator's tests catch deliberate faults. It runs on the
only self-hosted runner, and while it runs nothing else can use that runner, including production
promotes. Measured against `main` and the run history (2026-10-18 to 2026-10-23):

1. **It is slow, and getting slower.** Real PR runs take 34–133 minutes. Four of the nine long runs
   since 2026-10-18 were cancelled to free the runner, and each cancelled PR merged with no mutation
   result. `090` and `091` added modules and tests, so the number of mutants keeps growing.
2. **It runs when it cannot matter.** Any change under `python/` starts a full run. That includes
   guard tests that only read repo files and import nothing from the orchestrator (PR #259 and
   `091`).
3. **Its baseline is three months old.** The nightly job that refreshes `main`'s results has failed
   every scheduled run since 2026-07-20. A scheduled run gets no `workflow_dispatch` input defaults,
   so its steps take the runner path that has no NAS mount.
4. **The tool is the main cost.** mutmut 2 re-runs every surviving mutant when any test file
   changes, and it runs the whole test suite for each mutant. mutmut 3 runs only the tests that reach
   each mutated function. On `pve` (2026-10-24, planning trial) a fresh full run of all 4,117 mutants
   took **39 seconds**. The backlog item lists the changes the migration needs; the trial found one
   more (see [research.md](research.md)).

The owner decided the Mac results loop and the regression alert on 2026-10-22. The PR gate's shape
was decided then too, but was changed on 2026-10-24 once the trial showed a full run takes under a
minute (see Clarifications).

## Clarifications

### Session 2026-10-24

- Q: mutmut 3 reports mutants that no test reaches ("no tests"). How do they count in the score?
  → A: They are excluded. Score = killed / (killed + survived), the same formula as today. The
  no-tests count is reported next to the score so it stays visible.
- Q: How does the nightly fix ship? → A: As its own PR first, under this spec, so the nightly goes
  green before the migration. The migration follows as a second PR.
- Q: A fresh full run takes 39 s on `pve`. The 2026-10-22 decision was an incremental PR gate seeded
  from `main`'s nightly results. Which PR gate? → A: **A fresh full run on every PR.** No seeding
  from `main`, so there is no stale-baseline fallback, and edits to tests are scored on the PR
  itself. The nightly still publishes `main`'s results, for the Mac and for the regression alert.
- Superseded by the answer above, kept for the record: the PR gate was to fall back to a full run
  when `main`'s results were stale; PR runs were to be ephemeral; test-only edits were to be scored
  by the nightly only. A fresh full run makes all three moot. PR runs keep nothing.

### Session 2026-10-24 (analysis)

- PR 1 must not touch `python/`, or today's mutmut 2 gate holds the only runner for about an hour.
  PR 1 changes only the nightly workflow. Its guard test is written and seen to fail during PR 1,
  and lands at the start of PR 2.
- The ntfy `mutation` account is deployed to production only from `main`, after PR 2 merges. A
  deploy from the PR branch would be undone by the next deploy from `main`.
- The nightly's `min_score` input is checked as a number before it reaches the remote shell.
- US4 and SC-004 now separate the two Mac re-test cases: a source change (plain re-run, changed
  functions only) and a test edit (re-test the module by name).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The nightly refreshes main's results again (Priority: P1)

The owner relies on a nightly full run to keep `main`'s mutation results current. Today it fails
every night within a minute. After this story, each scheduled run does the full run on the PVE host
and publishes the results, or fails loudly when it cannot.

**Why this priority**: The Mac loop and the alert depend on it, and it has been broken for three
months. It is also the smallest change, and it ships first on its own (see Clarifications), still on
mutmut 2.

**Independent Test**: Trigger the nightly with the same event a scheduled run uses, with no inputs.
Check that the mutation run executes on PVE and that `main`'s results on the NAS carry today's date.

**Acceptance Scenarios**:

1. **Given** a scheduled nightly run with no inputs, **When** it reaches the mutation step, **Then**
   the step runs on the PVE host, not on the runner without the NAS mount.
2. **Given** the NAS share is not mounted on PVE, **When** the nightly tries to write results,
   **Then** the job fails red with a message that names the missing mount.
3. **Given** a manual run, **When** it runs, **Then** it does the same as a scheduled run.

---

### User Story 2 - A PR gets a mutation result in minutes (Priority: P1)

The owner opens a PR that changes orchestrator code or its tests. The gate scores the branch from
scratch and reports pass or fail within 5 minutes. The runner is free again soon after, so a promote
no longer waits behind it.

**Why this priority**: This is the reason the item exists: cancelled runs leave PRs with no result
and block production promotes.

**Independent Test**: On a throwaway branch, change one orchestrator function and one test. Check
that the gate finishes in under 5 minutes and that its score matches a full run of the same commit
on the Mac.

**Acceptance Scenarios**:

1. **Given** a branch that changes orchestrator source or tests, **When** the gate runs, **Then** it
   scores every mutant against the branch's own tests and finishes in under 5 minutes.
2. **Given** a branch whose score is below the floor minus the margin, **When** the gate runs,
   **Then** the required `result` check fails and the summary shows score, floor and margin.
3. **Given** a branch that adds a test which kills survivors, or weakens one so mutants survive,
   **When** the gate runs, **Then** the score reflects the change on that PR.
4. **Given** the nightly has not run for days, **When** the gate runs, **Then** its result is the
   same as it would be with a fresh nightly. The gate reads nothing from `main`'s results.

---

### User Story 3 - PRs that cannot change the score skip the gate (Priority: P2)

The owner opens a PR that changes only guard tests, workflow tests, other workflows or docs. The
mutation job is skipped, the required `result` check still passes, and the runner stays free.

**Why this priority**: It removes runs for PRs like #259 and `091`, but at under a minute per run
it saves less than Story 2.

**Independent Test**: Open a PR that changes only a file under `python/tests/guardrails`. Check that
the mutation job is skipped and `result` reports success.

**Acceptance Scenarios**:

1. **Given** a PR that changes only guard tests, workflow tests, other workflows or docs, **When**
   the gate evaluates paths, **Then** the mutation job is skipped and `result` passes.
2. **Given** a PR that changes orchestrator source, tests that can exercise the orchestrator, the
   mutation configuration, the dependency locks, the floor file, the gate script or the gate's own
   workflow, **When** the gate evaluates paths, **Then** the mutation job runs.

---

### User Story 4 - The owner inspects survivors on the Mac (Priority: P2)

The owner wants to improve a weak module. One task pulls `main`'s published results to the Mac
through the PVE host. The owner then browses current survivors, edits a test, and re-tests only that
module locally in under a minute.

**Why this priority**: It turns the score into something the owner can act on. It depends on
Story 1's published results.

**Independent Test**: Run the pull task on the Mac, open the survivor browser, then re-test one
module and time it.

**Acceptance Scenarios**:

1. **Given** published `main` results, **When** the owner runs the pull task, **Then** the local
   results match the published ones, the task prints their commit and age, and the browser lists
   current survivors.
2. **Given** pulled results and a local change to one module's source, **When** the owner re-runs
   mutation testing, **Then** only the changed functions are re-tested.
3. **Given** pulled results and an edited test, **When** the owner re-tests that module by name,
   **Then** every mutant in that module is re-tested, in under a minute. (mutmut keeps cached
   verdicts when only tests change, so a test edit needs the re-test by name.)
4. **Given** the PVE host is unreachable or no results are published, **When** the owner runs the
   pull task, **Then** it fails with a clear message and leaves any existing local results
   untouched.

---

### User Story 5 - A score regression reaches the owner's phone (Priority: P3)

When a nightly run scores below the floor minus the margin, the job fails red and a short message
arrives through ntfy: title, score, floor, and the modules with the most survivors.

**Why this priority**: Useful, but the red nightly already shows the regression. This only makes it
impossible to miss.

**Independent Test**: Run the nightly by hand on `main` with the floor raised above `main`'s score
for that run only. Check that it fails and a message arrives.

**Acceptance Scenarios**:

1. **Given** a nightly score below the floor minus the margin, **When** the run ends, **Then** the
   job fails and one ntfy message arrives with title, score, floor and the top modules by survivors.
2. **Given** a score at or above that line, **When** the run ends, **Then** no message is sent.
3. **Given** ntfy is unreachable, **When** the job tries to publish, **Then** the job still fails
   red and its log says the alert was not delivered.

---

### Edge Cases

- **The Mac pulls while the nightly publishes.** The pull gets either the old complete set or the
  new one, never a mix. Publishing replaces the old set as one step.
- **A nightly is cancelled or crashes mid-run.** Nothing is published, and the last complete set
  stays in place with its own commit and time.
- **A run scores below the floor.** The results are still published (they show the regression), and
  the job still fails.
- **A branch adds a new module.** Its mutants are scored like any other. The gate stays within its
  5-minute target.
- **A mutant hangs.** mutmut's timeout ends it. A timeout is excluded from the score, as today, and
  does not block the gate.
- **Tests that start a subprocess.** They must run the mutated code, not an unmutated copy outside
  the run. Otherwise they report "killed" or "survived" for the wrong code.
- **A PR deletes a test.** The gate must not run the deleted test from a copy left by an earlier
  run.
- **Pruning removes something still in use.** Only the old mutmut 2 caches are pruned, once, after
  the migration lands. `main`'s current results are never pruned.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 — Migrate to mutmut 3.** The gate, the nightly and the local workflow all use mutmut 3.x,
  pinned in the nightly lock file. The mutation configuration moves to the repository root. The
  layout, configuration, subprocess-test and guard-test changes listed under "What the migration
  needs" in the backlog item are made, plus the fifth subprocess caller found in planning. The gate
  script reads mutmut 3's results. Parity (Constitution V): the same command and arguments run the
  gate on the Mac, on PVE and in CI.
- **FR-002 — Nightly full run on PVE.** Every nightly run, scheduled or manual, does the full
  mutation run on the PVE host. A scheduled run's behaviour must not depend on `workflow_dispatch`
  input defaults. A manual run may take one optional input, a floor override for testing the alert
  (FR-009); left empty, as on a scheduled run, the committed floor applies. The job fails red if it
  cannot run or cannot publish. This ships as its own PR
  before FR-001, and works with mutmut 2 until the migration lands.
- **FR-003 — Published results.** After each nightly run that completes, whatever its score, PVE
  publishes `main`'s results to the NAS: the per-function results, the score, the no-tests count, a
  survivor report (survivors per module, worst first), the commit SHA and the time. The new set
  replaces the old one as a single step, so readers never see a partial set. A run that crashes or is
  cancelled publishes nothing. A manual run with the floor override (FR-002) also publishes nothing:
  it is an alert test, and its results carry the overridden floor (amended 2026-10-24 after the first
  alert test replaced `main`'s published floor with 99).
- **FR-004 — Fast PR gate.** The PR gate does a fresh full run of the branch: it starts from no
  earlier results and reads nothing from `main`'s published set. It keeps the path guard and the
  skip-as-pass `result` check. It fails if the branch's score is below the floor minus the margin
  (today 1.0 point). It keeps no results after it ends.
- **FR-005 — Withdrawn.** It was the stale-baseline fallback. FR-004 no longer reads a baseline.
- **FR-006 — Narrow trigger.** The mutation job runs only when a PR changes orchestrator source,
  tests that can exercise the orchestrator, or what decides the outcome: the mutation configuration,
  the dependency locks, the pytest configuration, the floor file, the gate script or the gate's own
  workflow. Changes only to guard tests, workflow tests, other workflows or docs skip it.
- **FR-007 — Guard tests out of the run.** Tests that read repo files and do not import the
  orchestrator are excluded from the mutation run. Copying fixtures for the run must not break any
  test that still runs in it.
- **FR-008 — Pull results to the Mac.** A Taskfile task pulls `main`'s published results through
  `ssh ci@pve` into the local results directory. The Mac needs no NAS mount. After a pull, the owner
  can browse survivors and re-test one module locally. The loop is documented under `docs/`.
- **FR-009 — Regression alert.** When the nightly score is below the floor minus the margin, the job
  fails and posts title, score, floor and the top modules by survivors to an ntfy topic, as a
  publisher under the `082` publisher contract. A failed delivery is logged and does not turn the
  job green.
- **FR-010 — Score and re-baseline.** The score is killed / (killed + survived). No-tests, timeout,
  suspicious, skipped and segfault mutants are excluded, and the no-tests count is reported with
  every score. The floor in `python/mutmut-threshold.txt` is reset from a measured mutmut 3 full run
  on `main`, and the file records the formula. It is ratcheted up by hand afterwards.
- **FR-011 — Prune old caches.** Once the migration lands, the mutmut 2 caches under
  `/mnt/nas/homelab_ci/mutmut-cache/` (14 files on 2026-10-23, `main` included) are removed. PR runs
  keep nothing (FR-004), so no ongoing pruning is needed.

### Key Entities

- **Published main results**: the mutation results for one `main` commit: per-function outcomes,
  score, no-tests count, survivor report, commit SHA and time. There is exactly one current set,
  written by the nightly and read by the Mac pull.
- **Floor**: the committed minimum score, with a margin subtracted before comparing. It is changed
  only by hand in a PR.
- **Survivor report**: surviving mutants per module, worst first. It is the input for the regression
  alert and for the owner's local work.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A PR that changes only guard tests, workflow tests, other workflows or docs skips the
  mutation job, and its `result` check passes.
- **SC-002**: A PR that changes orchestrator code finishes the mutation job in under 5 minutes, from
  job start to result.
- **SC-003**: The nightly is green on 7 runs in a row, and after each one the published results name
  the commit that run tested.
- **SC-004**: After the pull task, re-testing one module by name on the Mac takes under a minute.
  A plain re-run after a source change re-tests only the changed functions.
- **SC-005**: A manual nightly run with the floor raised above `main`'s score fails, and an ntfy
  message arrives. (The nightly runs only on `main`, so a weakened test on a branch is checked on the
  PR gate instead, SC-007.)
- **SC-006**: In the first two weeks after the migration, no mutation run is cancelled to free the
  runner for a promote.
- **SC-007**: A PR that weakens a test, so that its score drops below the floor minus the margin,
  fails the PR gate.

## Assumptions

- The margin stays at today's default, 1.0 point, so FR-004 and FR-009 use the same line.
- The layout is fixed with a link at the repository root, not by moving the package. Moving it is
  out of scope (see the backlog item).
- PVE runs the gate with Python 3.11 from `uv`, as today. mutmut 3.8 needs 3.10 or newer.
- The 39 s full run was measured on an idle `pve` at nice 19. Under load, and as the code grows, it
  will take longer. SC-002 allows for that.
- The ntfy publisher token and topic for the alert are added to vault like other `082` publishers.
  No new service is needed.
- The NAS share `/mnt/nas/homelab_ci` stays mounted on PVE and has room (8.2 TB, 26% used on
  2026-10-23).
- Out of scope: moving the package to a root `src/` layout, and adding a second self-hosted runner.
