# Data Model: Nextcloud Major Upgrade 32 → 34

**Feature**: `060-nextcloud-upgrade-33-34` | **Phase 1**

This feature has no application data model — it manipulates the *operational state* of an existing
service. The "entities" below are operational states and the backup artefact used for rollback.

## Entity: Nextcloud instance (operational state)

The instance the pipeline drives. Observed via `occ status` (JSON) in the `nextcloud_app` container.

| Field | Source | Valid / expected values |
|---|---|---|
| `versionstring` | `occ status` | `32.x` → `33.x` → `34.x` (one major step at a time) |
| `maintenance` | `occ status` | `false` in a healthy resting state; may be transiently `true` during a hop |
| `needsDbUpgrade` | `occ status` | `false` in a healthy resting state |
| `installed` | `status.php` | `true` |
| enabled apps | `occ app:list` | all compatible with the current major; no app disabled-by-incompatibility |
| image tag | `nextcloud_version` pin | `"32"` → `"33"` → `"34"`; MUST NOT exceed `"35"` |

### State transitions (per hop)

```
[Healthy on N]  --pre-hop backup+restore drill (verified)-->  [Protected on N]
[Protected on N]  --pin bump N→N+1, promote→apply (image auto occ upgrade)-->  [Upgrading]
[Upgrading]  --occ upgrade completes, maintenance off, needsDbUpgrade=false-->  [Healthy on N+1]
[Upgrading]  --health/verify FAILS-->  [Rollback: restore pre-hop DB dump + revert pin to N]  -->  [Healthy on N]
```

Validation rules (map to FRs):
- A transition to `[Healthy on N+1]` is only asserted when `versionstring`=N+1, `maintenance:false`,
  `needsDbUpgrade:false`, and no enabled app is disabled-by-incompatibility (FR-004, FR-005, FR-007).
- The `[Protected on N]` precondition MUST hold before any pin bump — an *unverified* backup does not
  satisfy it (FR-002, FR-003).
- `N→N+2` is not a legal transition (image refuses; FR-001). Pin MUST NOT be set to skip a major.
- `N+1 > 35` is out of range (FR-008).

## Entity: Backup artefact (rollback point)

Produced by `nextcloud_backup` (`backup_nextcloud.sh`), consumed by the restore drill.

| Field | Value |
|---|---|
| Location | `/mnt/nextcloud/backups/nextcloud-backup-<timestamp>.tar.gz` (Synology NFS) |
| Contents | MariaDB dump (`mysqldump`) + `config.php` |
| Excluded | user file data — already durable on NFS (`/mnt/nextcloud/data`), not re-copied |
| Integrity | archive extracts cleanly; DB dump imports into a scratch `mariadb:11` without error |
| Sentinel | a known invariant survives a restore (e.g. `oc_users` row count, or a named file's checksum on the NFS tree) |
| Role in rollback | restore this DB dump + revert `nextcloud_version` to the prior major (image tag) |

**Rollback composition note**: because a major upgrade mutates the DB schema + app code (not user
files), a rollback = restore this artefact's DB dump **and** re-pin the previous image tag; the NFS
user data is retained.

## Entity: Upgrade target (control input)

The `nextcloud_version` value in `ansible/group_vars/services/vars.yml`. Monotonic single-major steps:
`"32"` → `"33"` → `"34"`. Bounded above by `"35"` (the office-connector `max-version`). This is the
single control the operator changes per hop; everything else is verification.
