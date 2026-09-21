# Backlog: consolidate the five near-identical backup roles into one

**Status**: Backlog — raised 2026-09-20 while closing spec `065-hermes-ai-workspace`.
**Impact**: none yet (five working roles); this is a maintainability call, not a bug.

## What exists today

Five Ansible roles, each ~50-60 lines, each doing the same four things for a different
service: verify the backup destination is the bind-mounted NAS share (`findmnt --target`),
render a `backup_<service>.sh` script from a template, install a systemd service + timer
from the same schedule/retention variables, enable and start the timer.

| Role | Service |
|---|---|
| `financial_scenario_backup` | financial-scenario |
| `immich_backup` | immich |
| `nextcloud_backup` | nextcloud |
| `hermes_backup` | hermes (spec 065, this feature) |

(A fifth consumer — `proxmox_backup` — backs up the PVE host's own `/etc` and
`/var/lib/pve-cluster` rather than a service LXC, and may or may not fit the same shape;
check before assuming it is a trivial fifth case.)

The `tasks/main.yml` files are structurally identical modulo variable names. The
`backup_<service>.sh.j2` templates differ only in *how the online-consistent snapshot is
taken* (a `docker exec ... sqlite3` dump for financial-scenario and hermes, something
Postgres-specific for immich presumably) and in what paths get archived — the GFS
retention/pruning logic at the bottom of each script is byte-for-byte the same across at
least `financial_scenario_backup` and `hermes_backup`.

## Why this wasn't done as part of 065

Adding `hermes_backup` as a fifth copy was the right call **for this feature specifically**:
consolidating the other four roles is a refactor of other services' already-working,
already-deployed code, which is out of this feature's scope and a strictly larger, riskier
change to review than "add one more file that looks like the other four" (spec
065's plan.md § Complexity Tracking).

**With a fifth consumer, the refactor now passes Constitution IV's own bar** (">1 concrete
consumer" — there are four, soon five). That test was not met when
`financial_scenario_backup` was the only one; it clearly is now.

## Shape of the fix, roughly

One `service_backup` role parameterised on: service name, backup path, install dir, retention
settings, and a snapshot strategy (sqlite-via-docker-exec vs. Postgres vs. whatever immich
and nextcloud actually do — read those two before assuming they match). The GFS
prune/retention logic becomes one shared template fragment or a shared script called with
arguments, not five copies.

## Why this is a backlog item and not done now

Touching four other services' backup roles to prove out the parameterisation is real,
already-relied-upon work, and doing it as a side effect of an unrelated feature (065) is the
wrong place to take that risk. It deserves its own change, its own review, and its own
restore-drill re-verification for every service it touches — a backup role that "still works"
after a refactor is a claim, not a given (the same principle 065's own SC-006 acts on: a
backup that has never been restored is a belief).
