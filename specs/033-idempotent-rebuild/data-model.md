# Data Model: Idempotent Rebuild Orchestrator

**Feature**: 033-idempotent-rebuild
**Date**: 2026-02-05

## Entities

### Rebuild Run

| Field | Type | Description |
| --- | --- | --- |
| id | string | Run identifier (timestamp-based) |
| environment | enum | lab, prod |
| mode | enum | plan, apply |
| phases | list | Ordered phases executed |
| status | enum | pending, running, completed, failed |
| evidence_path | string | Local artifacts path |
| state_path | string | Local state JSON path |

### Phase State

| Field | Type | Description |
| --- | --- | --- |
| name | string | Phase name (mounts, restore, infra, services, verify) |
| status | enum | pending, running, completed, failed |
| started_at | string | Timestamp |
| ended_at | string | Timestamp |
| notes | string | Optional notes/errors |

### Mount Requirement

| Field | Type | Description |
| --- | --- | --- |
| host_mount | string | Host mount path |
| export | string | NFS export |
| validation | enum | pass, fail |
| evidence | list | Evidence references |

### Restore Artifact

| Field | Type | Description |
| --- | --- | --- |
| name | string | Artifact name |
| type | enum | config, data, iac |
| source | string | Backup path |
| restored | boolean | Whether restored |

### Evidence Bundle

| Field | Type | Description |
| --- | --- | --- |
| path | string | Local path |
| created_at | string | Timestamp |
| summaries | list | Summary files |
