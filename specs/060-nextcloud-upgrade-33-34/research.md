# Research: Nextcloud Major Upgrade 32 → 34

**Feature**: `060-nextcloud-upgrade-33-34` | **Date**: 2026-07-09
**Phase 0** — resolves the open questions carried from the spec/backlog.

## R1. How an upgrade is actually triggered (image auto-upgrade)

**Decision**: Drive each major hop by bumping the centrally-pinned `nextcloud_version`
(`ansible/group_vars/services/vars.yml`) by exactly one major and re-running the `nextcloud` role.
The role deploys `image: nextcloud:{{ nextcloud_version }}` (Apache variant) and runs
`community.docker.docker_compose_v2` with `pull: always, state: present`, which recreates the
`nextcloud_app` container on the new image. The official Nextcloud image entrypoint **auto-runs
`occ upgrade`** when the on-disk data is exactly one major behind the image.

**Rationale**: Mechanism already exists; no new tooling. It also gives us FR-001 for free — the
official image **refuses to skip a major** (a 32→34 jump aborts at container start before touching
data), so a mis-set pin fails safe.

**Alternatives considered**: Manual `occ upgrade` orchestration outside the image (rejected —
duplicates what the entrypoint already does, violates Code Economy). A dedicated upgrade playbook
separate from the role (rejected — the role is the single deploy path; extend it).

**Gap to close in the plan**: the role currently only waits for `status.php` `installed:true` and
`/login` 200 — it does **not** assert `occ status` (`versionstring`, `maintenance:false`,
`needsDbUpgrade:false`). A major upgrade can leave maintenance mode on or indices pending. → Add an
explicit post-recreate verification step (idempotent `occ upgrade`, `occ maintenance:mode --off` if
stuck, then assert `occ status`) **before** the app-config occ steps (which would otherwise fail in
maintenance mode). Satisfies FR-004/FR-005.

## R2. Target version and image tags

**Decision**: Hop to `nextcloud:33` then `nextcloud:34` (Apache tags, matching the current
`nextcloud:32` convention). End state pin = **34**; never exceed **35**.

**Rationale**: The Euro-Office connector `eurooffice` (v11.0.0/v11.0.1) requires
`<nextcloud min-version="33" max-version="35"/>` (verified via `gh api` on the connector repo). 34 is
mid-window and matches the official Euro-Office docs' "34+".

**Alternatives considered**: Stop at 33 (rejected — 34 is the docs-recommended floor and buys
headroom); jump to 35 (rejected — max supported, no margin if the connector lags).

**Open for the plan**: confirm `nextcloud:33`/`nextcloud:34` Apache tags exist at deploy time and note
the bundled PHP baseline each ships (informational; the image carries its own PHP).

## R3. Sequential hops through the gated pipeline

**Decision**: Two pipeline cycles. Each hop = (a) pre-hop backup + restore drill, (b) bump
`nextcloud_version` one major, (c) promote→apply `nextcloud`, (d) verify. Hop 1: 32→33. Hop 2:
33→34. The feature is "done" only after hop 2 verifies.

**Rationale**: The gated pipeline deploys whatever version is pinned; sequential majors are
image-enforced, so we cannot collapse the hops. Keeping each hop a full promote→apply preserves
Dual-Provisioning Parity (works in CI and from a laptop, constitution V) and the LAB gate.

**Note**: the two pin bumps are two commits/PRs (or one branch applied twice). Because `git push` is
blocked on this workstation (Zscaler), pins land via the `gh`-API push path; the deploy itself is
unaffected.

## R4. Backup + restore drill

**Decision**: Reuse the existing `nextcloud_backup` mechanism to produce the pre-hop artefact, and
add an **on-demand restore drill** that restores that artefact's DB dump into a throwaway MariaDB and
verifies it, before each hop.

**What the existing backup captures** (`backup_nextcloud.sh.j2`): enables maintenance mode →
`mysqldump` of the DB → copies `config.php` → `tar.gz` to `/mnt/nextcloud/backups` (Synology NFS).
It does **not** tar the user files — those already live on Synology NFS (`/mnt/nextcloud/data`,
durable). So the artefact = **DB dump + config.php**; user data is the live NFS tree.

**Rollback semantics** (important): a Nextcloud major upgrade mutates the **DB schema** and the **app
code** (image tag), not the user files. Therefore a rollback = restore the pre-hop **DB dump** +
pin the **previous image tag** + keep the (forward-compatible) NFS data. The restore drill proves the
DB dump is importable; the image-tag revert is a one-line pin change.

**Restore-drill design**: an on-demand target that (1) runs `nextcloud-backup.service` to force a
fresh artefact, (2) spins a scratch `mariadb:11` container, (3) imports the dump, (4) asserts the
import exits 0 and a sentinel (e.g. row count of `oc_users`, or a known file's checksum on the NFS
tree) matches, (5) records the artefact path as the hop's rollback point, (6) tears down the scratch
DB. Fail-closed if the NFS backup target is unreachable (FR-002 edge case).

**Alternatives considered**: Trust the nightly timer artefact (rejected — FR-003 requires a
*verified* restore, and a fresh pre-hop artefact); full data-tree backup (rejected — data is already
durable on NFS and re-copying tens of GB per hop is wasteful; Code Economy).

**Open for the plan**: pick the sentinel (favour `occ` user/file count over raw checksum — cheap and
meaningful); decide whether the drill is a script under `scripts/` (parity: runnable in CI + laptop)
vs an Ansible play — lean script for a self-contained, dual-runnable check.

## R5. Removing the built-in office editor (richdocuments / richdocumentscode)

**Decision**: Remove `richdocuments` and `richdocumentscode` from `nextcloud_apps_enable` and add an
explicit **uninstall** (`occ app:disable` + `occ app:remove`) via a new `nextcloud_apps_remove` list
+ a task mirroring the existing disable loop.

**Rationale**: The role today only `app:install`/`app:enable`/`app:disable` — a disabled app still
lingers and can still trip an upgrade compatibility check. `app:remove` uninstalls it. Extending the
existing loop pattern (not a new role) honours Code Economy (constitution IV).

**Alternatives considered**: Only remove from the enable list (rejected — leaves the app installed,
FR-006 wants it gone); disable only (rejected — same).

**Interaction**: `richdocumentscode` is the flaky built-in CODE this whole office-suite track is
replacing; removing it here also unblocks the Euro-Office connector adoption in `058` (single office
connector, no conflict).

## R6. App compatibility for the remaining apps

**Decision**: Before each hop, confirm `deck`, `calendar`, `weather_status`, `twofactor_totp`,
`bruteforcesettings` have releases compatible with the target major; after the hop run
`occ app:update --all` and assert no enabled app is disabled-by-incompatibility (FR-007).

**Rationale**: Incompatible enabled apps are the most common cause of a stuck upgrade. These are all
mainstream apps that track NC majors closely, so the risk is low — but it must be checked per hop,
not assumed.

**Open for the plan**: none blocking; the check is a per-hop `occ app:list` / `occ app:update`
assertion added to the verification step.

## R7. DB migration duration / maintenance window

**Decision**: Treat duration as **measured on hop 1**, not pre-guessed. Raise the role's
post-recreate readiness timeout to tolerate a longer `occ upgrade`, and rely on the existing
`maintenance_window_start` setting. Record the observed hop-1 duration to size hop 2.

**Rationale**: Migration time scales with data/row counts we haven't measured; a fixed guess would be
arbitrary. The instance is a small household deployment, so minutes not hours is expected.

**Alternatives considered**: Hard-coded long timeout (rejected — arbitrary; measure instead).

## Resolved unknowns summary

| Spec open item | Resolution |
|---|---|
| Upgrade auto-run on bump? | Yes (image entrypoint); add explicit `occ status` verification. |
| Image tags for 33/34 | `nextcloud:33`, `nextcloud:34` (Apache), pin ends at 34, ≤35. |
| DB migration duration | Measure on hop 1; raise readiness timeout. |
| Backup mechanism + drill | Existing DB+config artefact on NFS; add on-demand restore-drill (scratch MariaDB). |
| Remove built-in CODE | Add `nextcloud_apps_remove` (disable + remove); drop from enable list. |
