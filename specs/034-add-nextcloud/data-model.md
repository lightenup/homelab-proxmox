# Data Model: Self-Hosted Nextcloud Deployment

**Branch**: `034-add-nextcloud` | **Date**: 2026-02-22

## Overview

This feature does not introduce custom application code — Nextcloud is a third-party application. The data model here describes the **infrastructure entities** managed by Terraform and Ansible, and the **Nextcloud-managed entities** that exist within the application database (MariaDB).

## Infrastructure Entities (IaC-Managed)

### LXC Container (`nextcloud`)

| Field | Type | Value / Source | Notes |
|-------|------|----------------|-------|
| hostname | string | `nextcloud` | Terraform `lxc_service` module |
| name | string | `nextcloud-lxc` | Proxmox display name |
| cores | int | 4 | Sufficient for Nextcloud + MariaDB + Redis |
| memory | int (MB) | 4096 | Covers all three Docker containers |
| disk_gb | int | 32 | Local disk for OS + Docker images + MariaDB data |
| ip | string (CIDR) | `192.168.20.216/24` | Next available in `service_ips` map |
| features_mount | string | `nfs` | Required for in-guest NFS if host bind-mount is used |
| onboot | bool | true | Auto-start on host reboot (FR-015) |
| unprivileged | bool | true | Security baseline |

### NFS Mount (Host-side Bind Mount)

| Field | Type | Value | Notes |
|-------|------|-------|-------|
| host_volume | string | `/mnt/nas/homelab_nextcloud` | Proxmox host NFS mount from Synology |
| container_mp | string | `/mnt/nextcloud` | Bind-mounted into LXC |
| purpose | string | User data + backups | Nextcloud `/data` directory + backup output |

### Docker Compose Stack

Three services running inside the LXC:

| Container | Image | Persistent Storage | Port |
|-----------|-------|--------------------|------|
| `nextcloud_app` | `nextcloud:30` | `/mnt/nextcloud/data` (NAS), `/opt/nextcloud/html` (local) | `8080:80` |
| `nextcloud_db` | `mariadb:11` | `/opt/nextcloud/mariadb` (local disk) | internal only |
| `nextcloud_redis` | `redis:7-alpine` | `/opt/nextcloud/redis` (local disk) | internal only |

## Nextcloud Application Entities (App-Managed)

These entities are managed by Nextcloud in MariaDB. They are not created by IaC but are relevant for understanding data flow and backup requirements.

### User Account

| Field | Type | Notes |
|-------|------|-------|
| uid | string | Username (primary key) |
| displayname | string | Display name |
| email | string | Optional email |
| quota | string | `none` (quotas disabled per spec) |
| enabled | bool | Account active/disabled |
| totp_enabled | bool | 2FA status |

**Relationships**: Owns Files, Shares, Boards.

### File / Folder

| Field | Type | Notes |
|-------|------|-------|
| fileid | int | Internal ID |
| path | string | Relative path in user's storage |
| name | string | File/folder name |
| size | int | Bytes |
| mimetype | string | MIME type |
| mtime | timestamp | Last modified |
| storage | int | Storage backend reference |

**Relationships**: Belongs to User, has Versions, can have Shares.

**Storage location**: Physical files on NAS at `/mnt/nextcloud/data/<user>/files/`.

### Share

| Field | Type | Notes |
|-------|------|-------|
| id | int | Share ID |
| share_type | enum | user, group, link |
| share_with | string | Target user or null (link) |
| file_source | int | File/folder ID |
| permissions | int | Bitmask (read/write/share/delete) |
| token | string | Public link token (if link share) |
| password | string | Optional, hashed |
| expiration | date | Optional expiry |

### Board (Deck)

| Field | Type | Notes |
|-------|------|-------|
| id | int | Board ID |
| title | string | Board name |
| owner | string | Owner user UID |
| color | string | Board color |
| archived | bool | Archived status |

**Relationships**: Contains Stacks (columns), shared with Users.

### Card (Deck)

| Field | Type | Notes |
|-------|------|-------|
| id | int | Card ID |
| title | string | Card title |
| description | text | Markdown description |
| stack_id | int | Column (stack) reference |
| order | int | Position in column |
| duedate | datetime | Optional due date |
| owner | string | Creator user UID |

## State Transitions

### Container Lifecycle

```
Terraform Apply → LXC Created (started, onboot)
    → Ansible Bootstrap (lxc_base, docker)
    → Ansible Nextcloud Role (compose up)
    → First-run install (admin user created, DB initialized)
    → Operational
    → [Reboot] → Auto-start → Operational (FR-015)
    → [Rebuild] → Terraform Destroy+Apply → Ansible → Operational (data on NAS preserved)
```

### Backup / Restore Flow

```
Operational → Maintenance Mode ON
    → mysqldump → NAS backup directory
    → config.php copy → NAS backup directory
    → Maintenance Mode OFF
    → Prune old backups (retention: 7 daily, 4 weekly, 6 monthly)

Restore:
    NAS backup → Import SQL → Restart services → Verify
```

## Validation Rules

| Rule | Source | Enforcement |
|------|--------|-------------|
| Database on local disk only | Research/NFS gotchas | Docker Compose volume mapping |
| User data on NAS only | FR-014 | Docker Compose volume mapping to NFS mount |
| DB survives container rebuild | FR-014a | Backup to NAS + documented restore procedure |
| UID 33 ownership on NFS | NFS compatibility | NAS export config + Ansible preflight check |
| Redis required for NFS setups | NFS file locking | Docker Compose `depends_on` + config.php |
