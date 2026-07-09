# Feature Specification: Nextcloud Major Upgrade 32 → 34

**Feature Branch**: `057-nextcloud-upgrade-33-34`
**Created**: 2026-07-08
**Status**: Backlog — **prerequisite for [Euro-Office deploy](./058-eurooffice-deploy.md)**. Gating,
higher-risk (two sequential NC major upgrades against live user data).
**Input**: Upgrade the Nextcloud LXC (VMID 105) from major 32 to 34 in sequential steps
(32→33→34) through the gated pipeline, with a backup/restore drill around each hop, as the
prerequisite for adopting the Euro-Office document server (its connector requires Nextcloud 33–35).
Retire the flaky built-in CODE (`richdocumentscode`) as part of the app-compatibility pass.

## Summary

The Euro-Office integration connector (`eurooffice`, latest v11.0.1) declares
`<nextcloud min-version="33" max-version="35"/>`, so it will not install on the current deployment,
pinned at **Nextcloud 32** (`nextcloud_version: "32"` in `ansible/group_vars/services/vars.yml`).
This item raises Nextcloud to **34** — inside the connector's 33–35 window and matching the official
Euro-Office docs' "34+" guidance — so [`058-eurooffice-deploy`](./058-eurooffice-deploy.md) becomes
installable.

Nextcloud forbids skipping majors: an instance may only be upgraded one major at a time
(32 → 33 → 34). With the official Docker image, that means bumping the image tag one major, running
the upgrade (`occ upgrade`), confirming health, then repeating. Each hop is individually reversible.
Because a failed major upgrade can corrupt the instance, every hop is fenced by a fresh,
restore-verified backup — this item folds in a **backup/restore drill** rather than trusting the
scheduled backup alone.

The upgrade forces an **app-compatibility pass**. The built-in Collabora CODE server
(`richdocumentscode`) — unreliable and slated for replacement by Euro-Office — is dropped here so it
cannot block the upgrade or linger as dead weight; the `richdocuments` connector is removed pending
the Euro-Office connector in `058`. This item changes only the Nextcloud service; it does not deploy
Euro-Office and does not alter the reverse proxy.

## User Scenarios & Testing

### User Story 1 - Nextcloud reaches 34 healthy, with data intact (P1)

Operator advances the version pin one major and runs the gated pipeline for `nextcloud`; the
instance upgrades, exits maintenance mode, and serves all existing data.

**Acceptance**:
1. **Given** NC on 32, **When** the pin is set to 33 and the pipeline applies, **Then** `occ status`
   shows 33.x, maintenance off, no pending DB upgrade, and an existing user's files load.
2. **Given** NC on 33, **When** the pin is set to 34 and the pipeline applies, **Then** `occ status`
   shows 34.x with the same health checks green.
3. **Given** either hop, **When** the apply completes, **Then** `nextcloud.hus-sky.no` still returns
   302 to login with no reverse-proxy change.

### User Story 2 - Backup taken and restore proven before each hop (P1)

Before each major hop, a full backup (DB + data + config) is captured and a restore is exercised
into a scratch target, so a failed upgrade can roll back to a known-good instance.

**Acceptance**:
1. **Given** a pre-upgrade state, **When** the backup runs, **Then** a dated artefact (DB dump +
   data + `config.php`) exists on the backup target and its integrity check passes.
2. **Given** that artefact, **When** a restore drill runs, **Then** the DB imports without error and
   a sentinel file's checksum matches the source.
3. **Given** a hop that fails its post-upgrade health check, **When** the operator restores the
   pre-hop artefact, **Then** the instance returns to the prior major, healthy.

### User Story 3 - App compatibility reconciled; built-in CODE removed (P2)

**Acceptance**:
1. **Given** the app set on 32, **When** upgrading to 33, **Then** `richdocumentscode` and the
   `richdocuments` connector are removed from `nextcloud_apps_enable` and uninstalled.
2. **Given** NC on 34, **When** `occ app:update --all` runs, **Then** all enabled apps are at
   34-compatible versions and none is disabled-by-upgrade.

### Edge Cases

- **Skipped major** (pin 32 → 34 directly): must fail safely without touching data; must not leave
  the instance in maintenance mode.
- **Stuck in maintenance mode**: apply surfaces it; runbook defines the `occ maintenance:mode --off`
  / `occ upgrade` recovery.
- **DB migration timeout**: apply must not report success while `needsDbUpgrade: true`.
- **Connector ceiling**: NC MUST NOT be advanced past **35** while the Euro-Office connector caps at
  35.
- **Backup target unavailable** (NFS not mounted): pre-hop backup fails closed and blocks the hop.

## Requirements

- **FR-001**: Upgrade one major at a time (32 → 33 → 34); MUST NOT skip a major.
- **FR-002**: Before each hop, capture a full, integrity-checked backup (DB + data + `config.php`);
  MUST NOT begin the hop if the backup fails.
- **FR-003**: Exercise + verify a restore of the pre-hop backup (drill); record the artefact id as
  the rollback point.
- **FR-004**: Each hop runs the NC upgrade routine (image tag bump + `occ upgrade`), leaves
  maintenance off on success, and reports `needsDbUpgrade: false`.
- **FR-005**: After each hop the post-apply healthcheck passes and `occ status` reports the expected
  `versionstring`.
- **FR-006**: Remove `richdocumentscode` and the `richdocuments` connector from the enabled set and
  uninstall them.
- **FR-007**: Verify remaining enabled apps are compatible with the target major; MUST NOT report
  success while any enabled app is disabled-by-incompatibility.
- **FR-008**: `nextcloud_version` ends at **34** and MUST NOT exceed **35** (connector `max-version`).
- **FR-009**: Run through the gated LAB→PROD pipeline (no out-of-band manual upgrade); leave the
  reverse proxy unchanged.
- **FR-010**: On a failed hop, the runbook defines restore-from-artefact rollback to the prior major.

## Success Criteria

- **SC-001**: `occ status` → `versionstring 34.x`, `maintenance: false`, `needsDbUpgrade: false`.
- **SC-002**: A pre-existing user's files + a sentinel document are intact/openable (byte-identical
  sentinel).
- **SC-003**: For each hop, a restore drill of the pre-hop artefact succeeded before the hop ran.
- **SC-004**: `richdocumentscode` absent from `occ app:list`; `occ upgrade` is a no-op; no enabled
  app incompatible with 34.
- **SC-005**: `nextcloud.hus-sky.no` returns 302 unchanged; reverse proxy untouched.
- **SC-006**: `eurooffice` (v11.0.1) is installable on the result (dependency `min-version=33` met) —
  verified by a dry `occ app:install eurooffice` in `058`.

## Research & decisions

**Version gate (verified via `gh api`)**: the connector repo `Euro-Office/eurooffice-nextcloud`
`appinfo/info.xml` at tags **v11.0.0** and **v11.0.1** both declare
`<nextcloud min-version="33" max-version="35"/>`. Current pin is 32 → connector uninstallable; no
pre-v11 connector exists. **Target 34** = mid-window, matches docs, stays under the 35 ceiling.

**No-skip constraint**: NC upgrades must be sequential majors. With the Docker image: bump tag one
major → `occ upgrade` → verify → repeat.

**Backup posture**: a major upgrade against irreplaceable files is the highest-risk op; fence every
hop with a restore-verified backup (existing `nextcloud_backup` role + NFS target), not just the
nightly job. Fail closed if the target is unavailable.

**App set today** (`nextcloud_apps_enable`): `richdocuments`, `richdocumentscode`, `deck`,
`twofactor_totp`, `bruteforcesettings`, `calendar`, `weather_status`. Remove the two office apps
here; confirm the rest have 33/34-compatible releases.

**Open questions for the plan**: exact official image tags to pin for 33/34 (+ PHP baseline);
whether the `nextcloud` role invokes `occ upgrade` on tag change or needs an explicit task; live DB
migration duration (maintenance window + apply timeout); confirm the `nextcloud_backup` NFS mount is
the rw path (avoid the earlier financial-scenario nolock/bind-mount pitfall).

**Sources**: connector `info.xml` @ v11.0.0/v11.0.1 (33–35); Euro-Office NC integration docs
(https://euro-office.github.io/documentation/integration/nextcloud/); Nextcloud upgrade policy
(no skipping majors).

## Dependencies

- **Blocks**: [`058-eurooffice-deploy`](./058-eurooffice-deploy.md).
- **Assumes**: instance healthy on 32 (restored 2026-07-08); NFS backup target reachable; official
  `nextcloud` image tags for 33/34 available.
- **Out of scope**: deploying Euro-Office; any reverse-proxy change; upgrading beyond 34.
