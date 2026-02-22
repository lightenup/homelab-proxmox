# Feature Specification: Self-Hosted Nextcloud Deployment

**Feature Branch**: `034-add-nextcloud`
**Created**: 2026-02-22
**Status**: Draft
**Input**: User description: "Add nextcloud"

## Overview

Replace Google Drive and Google Docs with a self-hosted Nextcloud instance running as a dedicated service in the homelab. The deployment must provide file sync and share, collaborative document editing, and optional project tracking — while integrating with existing storage infrastructure and reverse proxy. Functionality already covered by other homelab services (photo management via Immich) is explicitly excluded.

## Assumptions

- **Database engine**: The database engine will align with the one recommended by Nextcloud for best compatibility and performance. (Reasonable default; can be adjusted during planning.)
- **NFS storage for user files**: Nextcloud user-uploaded files will be stored on the Synology NAS via a dedicated NFS export, following the same pattern established for Immich. This keeps user files on resilient network storage rather than local container disk.
- **Database storage**: The database stores metadata, user accounts, and application state. Its placement (local container disk vs. NAS) is deferred to the planning phase, as network-mounted storage may introduce performance or data integrity risks for database workloads. The key requirement is that database contents MUST survive a container rebuild, whether through NAS storage, automated backups, or another mechanism.
- **Access pattern**: Nextcloud will be accessed through the existing reverse proxy, consistent with how other services (Immich) are exposed to the LAN.
- **Internal hostname**: An internal DNS name (e.g., `nextcloud.local`) will be configured through existing mDNS infrastructure, following the pattern of other homelab services (`immich.local`, `proxy.local`, etc.). When the planned migration to `home.arpa` DNS occurs, the hostname will follow suit.
- **Single-user / small household**: The deployment targets a single admin user and a small number of household members (< 5 users). Enterprise-grade multi-tenancy is not required.
- **Deck for project tracking**: Nextcloud Deck (Kanban boards) will be included in scope as a lightweight project tracking tool, since the reference plan flagged it for evaluation and it requires minimal additional resources.
- **E2E encryption**: End-to-end encryption is out of initial scope. It can be evaluated and added as a follow-up once the base deployment is stable.
- **Document editing deployment**: The collaborative document editing engine will run as an integrated component within the Nextcloud service container, not as a separate dedicated service. Rationale: for a household of fewer than 5 users, the integrated approach is operationally simpler, sufficient for the expected workload, and consistent with the one-service-per-container pattern. If performance proves inadequate during use, splitting it into a separate service can be revisited as a follow-up.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — File Sync and Share (Priority: P1)

As a household member, I want to store, sync, and share files through a private cloud service so that I no longer depend on Google Drive for personal file storage and sharing.

**Why this priority**: File storage and sync is the primary reason for deploying Nextcloud. Without this, there is no replacement for Google Drive.

**Independent Test**: Can be fully tested by uploading a file through the web UI, verifying it appears in storage, and downloading it from another device or browser session.

**Acceptance Scenarios**:

1. **Given** Nextcloud is deployed and a user account exists, **When** the user logs in via a web browser, **Then** the Nextcloud dashboard loads and the user can access their files area.
2. **Given** a logged-in user, **When** they upload a file through the web interface, **Then** the file is stored on the NAS-backed storage and is visible in the file list.
3. **Given** a user has uploaded files, **When** they access Nextcloud from a different device or browser, **Then** the same files are visible and downloadable.
4. **Given** a user has a file, **When** they create a public share link, **Then** another person (without an account) can download the file using that link.
5. **Given** a user has a file, **When** they share it with another registered user, **Then** the recipient sees the shared file in their files area.
6. **Given** a user deletes a file, **When** they check the trash bin, **Then** the deleted file is present and can be restored.
7. **Given** a user modifies a file multiple times, **When** they check the version history, **Then** previous versions are listed and can be restored.
8. **Given** a user has a desktop or mobile sync client configured with the Nextcloud server URL and valid credentials, **When** they place a file in the local sync folder, **Then** the file appears in the Nextcloud web interface within 1 minute, and vice versa.

---

### User Story 2 — Collaborative Document Editing (Priority: P2)

As a household member, I want to create and edit documents, spreadsheets, and presentations collaboratively so that I no longer depend on Google Docs for document work.

**Why this priority**: Document editing is the second core reason for the migration away from Google. Without this, users would still need Google Docs for collaborative work.

**Independent Test**: Can be tested by creating a new document in the Nextcloud web interface and verifying it opens in an in-browser editor where changes are saved.

**Acceptance Scenarios**:

1. **Given** a logged-in user in the files area, **When** they create a new document (word processing format), **Then** an in-browser editor opens for editing.
2. **Given** an open document in the editor, **When** the user types and saves, **Then** the changes persist and are visible when reopening the document.
3. **Given** a document shared between two users, **When** both users open it simultaneously, **Then** both can see each other's edits in near-real-time (within 5 seconds).
4. **Given** a user has existing office-format files (e.g., .docx, .xlsx, .pptx), **When** they upload and open these files, **Then** the documents render correctly and are editable.
5. **Given** a logged-in user, **When** they create a lightweight text note (Markdown), **Then** a simple text editor opens for quick note-taking without requiring the full office suite.

---

### User Story 3 — Secure Access and Account Management (Priority: P2)

As the homelab administrator, I want Nextcloud to be secured with strong authentication and accessible only through the reverse proxy so that household data is protected from unauthorized access.

**Why this priority**: Security is equally important as document editing. A cloud storage service holding personal files must be protected from unauthorized access, especially if remote access is added later.

**Independent Test**: Can be tested by attempting login with valid and invalid credentials, enabling two-factor authentication, and verifying brute-force lockout behavior.

**Acceptance Scenarios**:

1. **Given** a user navigating to the Nextcloud URL, **When** they enter valid credentials, **Then** they are authenticated and reach the dashboard.
2. **Given** a user with two-factor authentication enabled, **When** they log in with correct password, **Then** they are prompted for a second factor (time-based one-time password) before gaining access.
3. **Given** an attacker attempting repeated login failures, **When** the failure threshold is exceeded, **Then** further login attempts from that source are temporarily blocked.
4. **Given** the Nextcloud service is running, **When** a user accesses it through the reverse proxy URL, **Then** the service responds correctly with appropriate forwarded headers.
5. **Given** the administrator account, **When** the admin creates, modifies, or disables user accounts, **Then** the changes take effect immediately.
6. **Given** a client making excessive requests to the Nextcloud service, **When** the request rate exceeds the configured threshold, **Then** additional requests are throttled or rejected to protect service availability.

---

### User Story 4 — Project Tracking with Kanban Boards (Priority: P3)

As a household member, I want to use Kanban-style boards for personal project tracking so that I have a lightweight task management tool integrated with my file storage.

**Why this priority**: Nice-to-have that complements the file management experience. Can be deferred without impacting the core Google Drive/Docs replacement goal.

**Independent Test**: Can be tested by creating a board, adding cards, moving cards between columns, and verifying persistence.

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** they navigate to the Deck/boards area, **Then** they can create a new board with custom columns.
2. **Given** an existing board, **When** the user adds a card with a title and description, **Then** the card appears in the designated column.
3. **Given** a card on a board, **When** the user drags it to a different column, **Then** the card's position is saved and persists across page reloads.
4. **Given** a board, **When** the user shares it with another registered user, **Then** the other user can view and interact with the board.

---

### User Story 5 — Data Persistence on Network Storage (Priority: P1)

As the homelab administrator, I want all Nextcloud user data stored on the NAS so that files survive service rebuilds and are covered by existing backup infrastructure.

**Why this priority**: Data safety is foundational. If user files are lost on a container rebuild, the service is unreliable and unusable as a primary file storage solution.

**Independent Test**: Can be tested by uploading a file, destroying and recreating the service container, and verifying the file still exists after redeployment.

**Acceptance Scenarios**:

1. **Given** a user has uploaded files to Nextcloud, **When** the service container is destroyed and recreated, **Then** all previously uploaded files are still accessible after redeployment.
2. **Given** the service is running, **When** the NAS storage becomes temporarily unavailable, **Then** the service degrades gracefully (shows an error rather than silently losing data) and recovers when storage returns.
3. **Given** files are stored on the NAS via Nextcloud, **When** the administrator checks the NAS directly, **Then** the files are visible in the designated Nextcloud storage area.

---

### User Story 6 — Service Reliability and Manageability (Priority: P2)

As the homelab administrator, I want the Nextcloud service to start automatically, survive reboots, and be deployable/updatable through existing infrastructure-as-code workflows so that it is consistent with other homelab services.

**Why this priority**: Operational consistency ensures the service can be maintained long-term without special procedures. This aligns with the homelab's "rebuild from code" philosophy.

**Independent Test**: Can be tested by rebooting the container and verifying the service comes back up, and by re-running the deployment and verifying idempotency.

**Acceptance Scenarios**:

1. **Given** the Nextcloud container is rebooted, **When** the container finishes starting, **Then** the Nextcloud service is accessible without manual intervention within 3 minutes.
2. **Given** a working Nextcloud deployment, **When** the deployment automation is re-run, **Then** no unnecessary changes are made (idempotent behavior).
3. **Given** a new version of Nextcloud is available, **When** the administrator updates the version reference and re-runs deployment, **Then** the service is upgraded to the new version with data intact.
4. **Given** the Nextcloud service is running, **When** the administrator checks service health, **Then** the health status is observable through existing monitoring infrastructure.

---

### User Story 7 — Backup and Restore (Priority: P2)

As the homelab administrator, I want Nextcloud's critical state (database, configuration) to be backed up regularly so that I can recover the service after a failure without losing user data or settings.

**Why this priority**: The homelab has established backup practices for other services (Immich database backups, Proxmox config backups). Nextcloud holds personal files and documents — losing database state (user accounts, share links, file metadata) would effectively lose access to all stored data even if files remain on NAS.

**Independent Test**: Can be tested by triggering a backup, destroying the database, restoring from backup, and verifying the service recovers with all user accounts, shares, and file metadata intact.

**Acceptance Scenarios**:

1. **Given** a running Nextcloud service with user data, **When** a backup is triggered (manually or on schedule), **Then** the database contents and essential configuration are saved to a recoverable location.
2. **Given** a valid backup exists, **When** the administrator restores from that backup after a data loss event, **Then** user accounts, file metadata, shares, and application settings are restored.
3. **Given** backup is configured, **When** a backup fails, **Then** the failure is detectable through existing monitoring or logging infrastructure.

---

### Edge Cases

- **NAS unavailable at boot**: If the NAS is unreachable when the container starts, the service should fail gracefully rather than corrupting data or hanging the boot process.
- **Storage full**: If the NAS storage is full, uploads should fail with a clear error message to the user rather than silently failing or corrupting files.
- **Concurrent large uploads**: Multiple users uploading large files simultaneously should not crash the service or cause data corruption.
- **Reverse proxy down**: If the reverse proxy is unavailable, direct access to the Nextcloud service (if network allows) should still function for emergency administration.
- **Failed upgrade**: If a version upgrade fails mid-way, the system should provide a path to rollback or at minimum preserve the data directory intact.
- **Session expiry**: Long-running collaborative editing sessions should not lose unsaved work due to session timeouts.
- **Android mDNS resolution**: Android does not natively support `.local` mDNS resolution in browsers or most apps. Sync client configuration may require using the IP address directly until the planned DNS migration to `home.arpa` is completed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a web-based interface for uploading, downloading, organizing, and managing files and folders. *(traces to US-1)*
- **FR-002**: The system MUST support file versioning, allowing users to view and restore previous versions of files. *(traces to US-1)*
- **FR-003**: The system MUST provide a trash bin for deleted files, allowing recovery within a configurable retention period. *(traces to US-1)*
- **FR-004**: The system MUST support sharing files and folders with other registered users and via public links (with optional password protection and expiry). *(traces to US-1)*
- **FR-005**: The system MUST support WebDAV access for desktop and mobile sync clients. *(traces to US-1)*
- **FR-006**: The system MUST provide in-browser collaborative editing for common office document formats (word processing, spreadsheets, presentations). *(traces to US-2)*
- **FR-007**: Collaborative editing MUST support simultaneous multi-user editing with changes visible to all participants within 5 seconds. *(traces to US-2)*
- **FR-008**: The system MUST support lightweight Markdown/text editing without requiring the full office suite. *(traces to US-2)*
- **FR-009**: The system MUST support user account creation and management by the administrator. *(traces to US-3)*
- **FR-010**: The system MUST support two-factor authentication using time-based one-time passwords. *(traces to US-3)*
- **FR-011**: The system MUST include brute-force protection that temporarily blocks repeated failed login attempts. *(traces to US-3)*
- **FR-012**: The system MUST be accessible through the existing reverse proxy, with correct header forwarding. *(traces to US-3)*
- **FR-013**: The system MUST provide Kanban-style boards for task and project tracking, with support for custom columns, cards, and board sharing. *(traces to US-4)*
- **FR-014**: All user-uploaded files and documents MUST be stored on the NAS, not on local container disk. *(traces to US-5)*
- **FR-014a**: The database contents (user accounts, metadata, application state) MUST survive a full container rebuild, whether through NAS-backed storage, automated database backups, or another persistence mechanism. *(traces to US-5)*
- **FR-015**: The system MUST start automatically after container reboot without manual intervention. *(traces to US-6)*
- **FR-016**: Deployment MUST be idempotent — re-running the deployment automation on a healthy system MUST NOT break the service or cause unnecessary restarts. *(traces to US-6)*
- **FR-017**: The system MUST support controlled version upgrades through the deployment automation, preserving all user data across upgrades. *(traces to US-6)*
- **FR-018**: The system MUST run as a dedicated service in its own container, consistent with the one-service-per-container pattern. *(traces to US-6)*
- **FR-019**: The system MUST rate-limit requests to protect against abuse. *(traces to US-3, scenario 6)*
- **FR-020**: Excluded functionality (photo management, video/voice calling, email client) MUST be disabled or not installed, so that users are not confused by non-functional features and the attack surface is minimized. *(traces to Explicitly Excluded)*
- **FR-021**: The system MUST support regular backups of database contents and essential configuration to a recoverable location. *(traces to US-7)*
- **FR-022**: The system MUST support restoration from a backup, recovering user accounts, file metadata, shares, and settings. *(traces to US-7)*

### Key Entities

- **User Account**: A registered person who can log in and manage files. Attributes: username, display name, email, storage quota, group membership, 2FA status.
- **File/Folder**: A stored object in the user's personal space or shared space. Attributes: name, path, size, type, version history, sharing status, trash status.
- **Share**: A permission grant for a file or folder. Can be user-to-user or a public link. Attributes: target (user or link), permissions (read/write), expiry, password protection.
- **Document**: An office-format file opened for collaborative editing. Attributes: format, last modified, active editors, version.
- **Board**: A Kanban project board. Attributes: title, owner, columns (stacks), shared users.
- **Card**: A task item on a board. Attributes: title, description, assigned user, due date, position in column.

## Explicitly Excluded

- **Photo/video management**: Immich handles this. Nextcloud Photos, Memories, and Maps functionality is not needed and should be disabled.
- **Video/voice calling**: No Talk functionality. Would require a TURN server and adds complexity for no household benefit.
- **Email client**: Not needed. Email is handled by existing providers.
- **Calendar and Contacts**: Not in initial scope. Can be added as a follow-up feature if needed.
- **End-to-end encryption**: Not in initial scope. Needs evaluation for compatibility with collaborative editing and sync clients before adoption.
- **Federation**: No inter-server federation with other Nextcloud instances.
- **Storage quotas**: Per-user storage quotas are not needed for a small household deployment. Users share the available NAS capacity. Can be revisited if usage patterns change.
- **Public internet exposure**: Initial deployment is LAN-only (plus VPN). Public internet access is a future consideration.

## Open Questions

None — all ambiguities resolved via assumptions above. The most significant decision (document editing engine deployment model) was resolved in favor of the integrated approach for a small household. See Assumptions section for rationale.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can upload a file and download it from another device within 2 minutes of initial deployment completion.
- **SC-002**: Two users can simultaneously edit the same document and see each other's changes within 5 seconds.
- **SC-003**: All user files survive a full container rebuild-from-scratch and are accessible after redeployment.
- **SC-004**: The service is accessible through the reverse proxy within 3 minutes of a container reboot, without manual intervention.
- **SC-005**: Re-running the deployment automation on a healthy system completes with no unnecessary changes (idempotent behavior).
- **SC-006**: A new user account can be created by the administrator and used to log in within 1 minute.
- **SC-007**: Two-factor authentication can be enabled and successfully used to log in, blocking access without the second factor.
- **SC-008**: After 5 consecutive failed login attempts, further attempts from the same source are temporarily blocked.
- **SC-009**: Desktop or mobile sync clients can connect via WebDAV and synchronize files bidirectionally.
- **SC-010**: A Kanban board can be created, populated with cards, and shared with another user, with all changes persisting across page reloads.
- **SC-011**: A database backup can be created and used to restore user accounts, shares, and file metadata after a simulated data loss event.
- **SC-012**: Excluded apps (Photos, Talk, email client) are confirmed disabled or absent in the deployed instance.
