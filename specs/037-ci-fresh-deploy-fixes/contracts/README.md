# Contracts: CI Fresh-Deploy Pipeline Fixes

This feature does not introduce API contracts (no REST/GraphQL endpoints).

All changes are internal to the bash orchestrator (`scripts/lab/pve-service-deploy`).

## Evidence Artifact Schemas

The new evidence artifacts follow the existing flat-text key-value format
established by `lxc-features.txt` and `lxc-mountpoints.txt`.

See `data-model.md` for field definitions.
