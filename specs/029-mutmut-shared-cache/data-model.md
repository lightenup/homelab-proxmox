# Data Model: Mutmut Shared Cache

## Entities

### Mutation Cache

- **Path**: `/mnt/nas/homelab_ci/mutmut-cache/<branch>`
- **Contents**: `.mutmut-cache` SQLite file storing mutation results and metadata.
- **Access**: Read/write on PVE; read on developer laptops.

### Shared Storage

- **Mount path**: `/mnt/nas/homelab_ci`
- **Type**: NFS share
- **Ownership/permissions**: Must allow CI and local users to write cache files.

## Relationships

- **Mutation Cache** resides within **Shared Storage**.
- Cache is **scoped per branch** to prevent cross-branch contamination.

## Validation Rules

- Cache file must exist (or be creatable) and be writable before mutation run.
- Missing or unwritable cache paths must fail with a clear error message.
