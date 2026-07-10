# Quickstart / Runbook: Nextcloud Major Upgrade 32 → 34

**Feature**: `060-nextcloud-upgrade-33-34`

The upgrade is **two identical hops** (32→33, then 33→34). Do not start a hop until the previous one
is verified healthy. `git push` is blocked on this workstation (Zscaler) — land the pin bump via the
`gh`-API push path; the deploy itself is unaffected.

Conventions: `NC=192.168.1.216` (LXC 105); run `occ` as `docker exec -u www-data nextcloud_app php occ ...`.

## Per-hop procedure (run for N=32→33, then N=33→34)

### 1. Pre-hop backup + restore drill  (FR-002, FR-003)

```bash
# force a fresh artefact and prove it restores into a scratch DB; prints the artefact path
scripts/nextcloud/restore_drill.sh
```
- Expect: `Verification Status: PASS`, sentinel matches, and a printed
  `ROLLBACK_ARTEFACT=/mnt/nextcloud/backups/nextcloud-backup-<ts>.tar.gz`.
- **Record** that artefact path — it is this hop's rollback point.
- If the NFS backup target is unreachable → the drill fails closed; **stop**, fix the mount, retry.

### 2. Bump the version pin one major

Edit `ansible/group_vars/services/vars.yml`: `nextcloud_version: "<N>"` → `"<N+1>"` (33, then 34).
Never skip a major; never exceed `"35"`. Land via `gh`-API push → PR → merge.

### 3. Deploy through the gated pipeline

```
Prod 1 - LXC Promote   (service=nextcloud, ref=main)      # LAB deploy + gate
Prod 2 - LXC Apply     (promotion_run_id=<id>, confirm_apply_prod=deploy-prod)
```
The container is recreated on `nextcloud:<N+1>`; the image auto-runs `occ upgrade`. The role's new
verification step then asserts a clean landing (or fails the apply).

### 4. Verify  (FR-004, FR-005, FR-007 → SC-001, SC-004, SC-005)

```bash
docker exec -u www-data nextcloud_app php occ status                # versionstring N+1.x, maintenance:false, needsDbUpgrade:false
docker exec -u www-data nextcloud_app php occ app:update --all
docker exec -u www-data nextcloud_app php occ app:list | grep -i richdocuments   # expect: absent
curl -s -o /dev/null -w "nextcloud=%{http_code}\n" https://nextcloud.hus-sky.no/  # expect 302
```
- All green → hop complete. Record the observed migration duration (sizes the next hop's timeout).
- Confirm a **sentinel file** opens and matches (SC-002).

### 5. Rollback (only if step 4 fails)  (FR-010)

```bash
# 1) restore the recorded pre-hop DB dump into the live MariaDB (procedure in restore_drill.sh --help)
# 2) revert the pin: nextcloud_version "<N+1>" -> "<N>" ; re-run Prod 1/2 for nextcloud
# 3) occ maintenance:mode --off ; occ status  -> back to N.x healthy
```

## After hop 2 (on 34): hand-off to Euro-Office (SC-006)

```bash
# dependency dry-check — the eurooffice connector needs NC >= 33
docker exec -u www-data nextcloud_app php occ app:install eurooffice --keep-disabled 2>&1 | head
```
Success (no "not compatible with this version" error) confirms feature `058-eurooffice-deploy` is
unblocked. Do **not** enable the connector here — that is `058`'s job.

## Definition of done

- `occ status` → `34.x`, `maintenance:false`, `needsDbUpgrade:false` (SC-001).
- Pre-existing users/files/shares intact; sentinel byte-identical (SC-002).
- A verified restore drill preceded **each** hop (SC-003).
- Built-in office editor absent; `occ upgrade` a no-op; no incompatible enabled app (SC-004).
- `nextcloud.hus-sky.no` 302; reverse proxy untouched (SC-005).
- `eurooffice` dependency satisfiable (SC-006).
