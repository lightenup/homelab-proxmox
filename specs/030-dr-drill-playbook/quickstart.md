# Quickstart: DR Drill Playbook

Use this quickstart to execute the DR drill using the dedicated runbook.

## Prerequisites
- NAS share `/volume1/homelab_dr_test` mounted on PVE at `/mnt/nas/homelab_dr_test`.
- Free space >= 2× rclone size estimate for the backup set.
- rclone configuration and Hetzner S3 credentials available in secure storage.
- DSM Hyper Backup Explorer installed and access to the encryption key.

## Steps
1. Read the DR drill runbook at `docs/runbooks/dr-drill-playbook.md`.
2. Run the readiness checks described in the runbook (mount, permissions, free space).
3. Use the Taskfile helpers to list and download Hetzner backup objects:
   - `task dr:hetzner:list -- <args>`
   - `task dr:hetzner:download -- <args>`
4. Confirm the Pool directory structure exists under `/mnt/nas/homelab_dr_test`.
5. Open DSM Hyper Backup Explorer and validate decryption/browsing.
6. Record the outcome in the drill report template referenced by the runbook.

## Expected Result
- Full download completed to the DR test share.
- DSM Hyper Backup Explorer can decrypt and browse the backup.
- Drill report captured with outcomes and evidence.
