# DR Drill Report

**Drill ID**: drill-20260117
**Date**: 2026-02-03
**Operator(s)**: Andreas Jacobsen
**Execution Host**: pve
**Working Directory**: /mnt/nas/homelab_dr_test/drill-20260117
**tmux Session**:

## Summary

- **Outcome**: ☑ Success ☐ Partial ☐ Failed
- **Backup Set**: Hetzner Object Storage (Synology Hyper Backup)
- **Target Share**: /volume1/homelab_dr_test (mounted at /mnt/nas/homelab_dr_test)
- **Total Size Estimate**:
- **Free Space at Start**:
- **Time Started**:
- **Time Finished**:

## Steps Completed

- [x] Hetzner list verified
- [x] Metadata downloaded (Config/Control/Guard/_Syno_TaskConfig)
- [x] Pool data downloaded in full
- [x] Pool structure verified (Pool/0/0 ...)
- [x] DSM Hyper Backup Explorer validation
- [ ] Sample extraction completed
- [ ] verify_restore.sh executed

## Evidence

- Logs/commands output:
- Screenshots:
- Hash reports:
- rclone.log path:

## Issues / Blockers

- Missing root metadata files at drill root; manual download required before DSM validation.

## Follow-ups

- Add explicit download step for root metadata files (`SynologyHyperBackup.bkpi`, `synobkpinfo.db`, `storage_statistics.db.*`).

## Notes

- Manual remediation completed by copying missing root metadata files into the drill root. Hyper Backup Explorer then decrypted and browsed successfully.
