# Feature Specification: Decommission Host Email Notifications

**Feature Branch**: `014-email-decommission`  
**Created**: December 23, 2025  
**Status**: Draft  
**Input**: "Decommission PVE host email notifications and migrate to Kuma push monitoring for Proxmox backup alerting"

## Clarifications

### Session 2025-12-23

- Q: What is the exact HTTP API format for Kuma push monitor integration? → A: `curl -X POST "${KUMA_PUSH_URL}?status=up&msg=Backup_completed"`
- Q: How should the backup script determine failure vs success for Kuma status? → A: Exit code based (if $? != 0, then failure)
- Q: Should discovery phase override be opt-in or opt-out when conflicts detected? → A: Opt-in override flag required (safe default, abort unless forced)
- Q: Should playbook runs be idempotent (safe to run multiple times)? → A: Fully idempotent (check state, skip if already applied)
- Q: Variable naming convention for email enable/disable/uninstall flags? → A: Single control variable `proxmox_backup_email_mode` with values: `enabled`, `kuma_only`, `disabled`, `removed`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Migrate to Centralized Monitoring (Priority: P1)

As a homelab operator, I want backup failures reported through my centralized monitoring system (Uptime Kuma) instead of direct SMTP from the Proxmox host, so I have a single pane of glass for all service health notifications and don't need to maintain email infrastructure on individual hosts.

**Why this priority**: This is the primary value driver - consolidating monitoring into Kuma simplifies operations, reduces maintenance burden (no per-host SMTP config), and provides better visibility through the existing monitoring dashboard. Kuma can then fan-out notifications to email, Slack, etc.

**Independent Test**: Configure Kuma push URL, run manual backup, verify Kuma receives push notification (success status) and can detect failures when backup is intentionally broken. Complete value delivered - backup monitoring works through Kuma without host email.

**Acceptance Scenarios**:

1. **Given** Kuma push URL configured in backup vars, **When** backup succeeds, **Then** Kuma monitor shows "Up" with last push timestamp and backup completes without attempting email
2. **Given** Kuma push URL configured, **When** backup fails (NAS unreachable), **Then** Kuma monitor shows "Down" and Kuma sends notification via configured channels (email, Slack)
3. **Given** Kuma push URL not configured, **When** backup runs, **Then** backup completes successfully without crashing (silently skips push if URL missing)

---

### User Story 2 - Safely Disable Host Email (Priority: P2)

As a homelab operator, after confirming Kuma monitoring works reliably, I want to disable the host-level email notification system (Postfix SMTP relay) without uninstalling packages, so I can quickly roll back if issues arise and don't break any other system processes that might use mail.

**Why this priority**: Safety first - disabling is reversible and risk-free. Allows testing Kuma-only monitoring in production while maintaining an escape hatch. Prevents accidental breakage of other services that might use system mail.

**Independent Test**: Run Ansible playbook with `proxmox_backup_remove_host_email: true`. Verify Postfix is stopped/disabled, backup runs successfully with Kuma push only, and no email is sent. Can re-enable by setting flag to false and re-running playbook. Delivers value - email disabled, Kuma working, fully reversible.

**Acceptance Scenarios**:

1. **Given** Postfix running and email enabled, **When** disable flag set to true, **Then** Postfix service stopped/disabled and SMTP config removed from backup script
2. **Given** email disabled via flag, **When** backup runs, **Then** backup succeeds with Kuma push and no email attempt logged
3. **Given** email disabled, **When** re-enable flag set and playbook re-run, **Then** Postfix restarts and backup sends email again (rollback works)
4. **Given** discovery phase run, **When** non-backup mail usage detected, **Then** Ansible warns and aborts disable to prevent breaking other services

---

### User Story 3 - Clean Package Removal (Priority: P3)

As a homelab operator, after running email-disabled for weeks without issues, I want to optionally uninstall mail packages (Postfix, mailutils) to reduce system footprint and attack surface, with confirmation required to prevent accidents.

**Why this priority**: Optional cleanup for long-term - reduces installed packages, removes unused services, slightly improves security posture. Lower priority because system works fine with packages disabled. Only for operators who want minimal systems.

**Independent Test**: Run Ansible with uninstall flags and confirmation. Verify mail binaries removed (`which mail` returns nothing), backup still works with Kuma push, and system is otherwise unaffected. Delivers value - cleaner system with fewer packages.

**Acceptance Scenarios**:

1. **Given** email disabled for 2+ weeks, **When** uninstall flags set with confirmation, **Then** Postfix and mailutils packages removed via apt-get purge
2. **Given** packages removed, **When** `which mail` run, **Then** returns empty (binary not found)
3. **Given** packages removed, **When** backup runs, **Then** backup succeeds with Kuma push (no dependency on mail command)
4. **Given** uninstall requested without confirmation flag, **When** playbook runs, **Then** fails with error requiring explicit `proxmox_backup_uninstall_confirmed: true`
5. **Given** non-backup mail usage detected during discovery, **When** uninstall requested, **Then** Ansible aborts with warning listing detected usage

---

### Edge Cases

- What happens when Kuma URL is misconfigured (wrong port, typo in URL)? → Backup continues, logs warning, exits with success (push is best-effort, doesn't fail backup)
- What happens when Kuma server is down/unreachable during backup? → curl timeout (5s), backup continues, success status (network issues shouldn't fail backups)
- What happens if operator uninstalls packages but later needs email for another service? → Manual reinstall required (apt-get install postfix mailutils), document in runbook
- What happens if Postfix is used by other services (PVE alerts, other scripts)? → Discovery phase detects this (grep journald, scan /etc/systemd, /usr/local/sbin), aborts disable/uninstall, prompts operator
- What happens if operator disables email but forgets to configure Kuma URL? → Backups run without notifications - operator discovers via missing heartbeat or next manual check
- What happens when rolling back (re-enabling email) but vault credentials expired/rotated? → Playbook fails with clear error, operator must update vault with current credentials
- What happens if backup fails and Kuma URL is not configured? → Silent failure - no notification sent, operator relies on manual checks or schedule-based alerts

## Requirements *(mandatory)*

### Functional Requirements

**Core Push Monitoring (US1)**:

- **FR-001**: System MUST send HTTP POST to Kuma push monitor URL on backup success using format: `curl -X POST "${KUMA_PUSH_URL}?status=up&msg=Backup_completed_successfully"` with 5s timeout
- **FR-002**: System MUST send HTTP POST to Kuma push monitor URL on backup failure using format: `curl -X POST "${KUMA_PUSH_URL}?status=down&msg=${FAILURE_REASON}"` with URL-encoded message
- **FR-002a**: System MUST detect backup failure via exit code (if final exit code != 0, backup failed) - standard Unix success/failure convention
- **FR-003**: System MUST continue backup execution if Kuma push fails (network timeout, bad URL, etc.) - push failures MUST NOT fail the backup
- **FR-004**: System MUST log Kuma push attempts to journald (success/failure with URL and response code)
- **FR-005**: System MUST fall back silently if `KUMA_PUSH_URL` is not configured (no crash, no error)
- **FR-006**: Kuma push timeout MUST be <= 5 seconds (don't block backup for network issues)
- **FR-007**: System MUST control email/Kuma behavior via `proxmox_backup_email_mode` state variable (enabled|kuma_only|disabled|removed) - single source of truth for notification state

**Safe Disable (US2)**:

- **FR-008**: Ansible MUST perform discovery phase before disable/uninstall (check packages, services, config files, other usage)
- **FR-009**: Ansible MUST abort disable if non-backup mail usage detected (journald logs, systemd units, other scripts) unless explicit opt-in override flag `proxmox_backup_force_remove_email: true` is set (safe default prevents accidental breakage)
- **FR-010**: Ansible MUST stop and disable Postfix service when `proxmox_backup_email_mode` is set to `disabled` or `removed`
- **FR-011**: Ansible MUST remove SMTP variables from `/etc/proxmox-backup.conf` when mode is `disabled` or `removed`
- **FR-012**: Ansible MUST support rollback to `enabled` mode (re-enable Postfix, restore SMTP config from vault)
- **FR-013**: Ansible MUST leave backup script email function intact (commented/gated) for potential future use
- **FR-014**: Ansible MUST add comment to config noting "Kuma owns notifications now" when email disabled

**Package Removal (US3)**:

- **FR-015**: Package uninstall (mode `removed`) MUST require explicit confirmation flag (`proxmox_backup_uninstall_confirmed: true`) - prevents accidental permanent removal
- **FR-016**: Ansible MUST fail with clear error if mode `removed` requested without confirmation flag
- **FR-017**: Ansible MUST use `apt-get remove --purge` to remove mailutils, postfix when `proxmox_backup_email_mode: removed`
- **FR-018**: Ansible MUST run `apt-get autoremove --purge` after package removal
- **FR-019**: Ansible MUST remove `/etc/postfix/` directory after Postfix uninstall (if owned by package)
- **FR-020**: Ansible MUST remove `/etc/msmtprc` if exists and mailutils removed
- **FR-021**: Ansible MUST NOT delete `/etc/aliases` (system file, may be used by other services)

**Discovery & Safety (US2/US3)**:

- **FR-022**: Discovery MUST check installed packages (`dpkg -l | grep -E 'postfix|mailutils|msmtp|exim|sendmail'`)
- **FR-023**: Discovery MUST check active/enabled services (`systemctl list-unit-files | grep -E 'postfix|exim'`)
- **FR-024**: Discovery MUST check journald for non-backup mail activity (`journalctl -u postfix -n 200`)
- **FR-025**: Discovery MUST scan `/etc/systemd`, `/usr/local/sbin`, `/opt` for mail command usage (grep for sendmail|mail|msmtp)
- **FR-026**: Discovery MUST report findings to Ansible output (packages found, services running, potential conflicts)
- **FR-027**: Ansible MUST log all disable/uninstall actions to journald on target host
- **FR-027a**: All Ansible tasks MUST be fully idempotent - check current state before acting, safe to re-run multiple times without errors or unexpected side effects (standard Ansible best practice)

**Verification (US2/US3)**:

- **FR-028**: Verification MUST confirm Postfix stopped (`systemctl is-active postfix` returns inactive)
- **FR-029**: Verification MUST confirm backup succeeds after email disabled (`proxmox-config-backup` exit code 0)
- **FR-030**: Verification MUST confirm Kuma received push (check Kuma monitor status via web UI or API)
- **FR-031**: Verification MUST confirm mail binaries removed after uninstall (`which mail` returns empty)
- **FR-032**: Verification MUST test failure path (break NAS, run backup, confirm Kuma detects failure)

### Key Entities

- **Email Mode State Machine**: `proxmox_backup_email_mode` variable controls notification behavior with four states:
  - `enabled`: Email notifications active via Postfix SMTP (legacy default)
  - `kuma_only`: Kuma push enabled, email function present but not invoked (transition state)
  - `disabled`: Postfix stopped/disabled, SMTP config removed, Kuma push active (reversible)
  - `removed`: Mail packages uninstalled, only Kuma push available (requires confirmation, permanent)
- **Kuma Push Monitor**: Uptime Kuma monitor configured in "Push" mode, generates unique URL for receiving heartbeat/status updates via HTTP POST
- **Backup Configuration**: `/etc/proxmox-backup.conf` - contains KUMA_PUSH_URL, ENABLE_HOST_EMAIL flag, and (if enabled) SMTP variables
- **Email Notification Function**: `send_email_notification()` in backup script - gated behind ENABLE_HOST_EMAIL, preserved for rollback
- **Discovery Report**: Ansible facts gathered during discovery phase - lists installed packages, active services, config files, detected usage patterns

## Success Criteria *(mandatory)*

- Operator can configure Kuma push URL and receive backup success/failure notifications through Kuma dashboard
- Operator can disable host email notifications safely (Postfix stopped, no impact on backups or other services)
- Operator can re-enable email notifications if Kuma issues arise (rollback works)
- Operator can optionally remove mail packages after confirming Kuma reliability (with explicit confirmation required)
- Ansible playbook detects and prevents breaking non-backup mail usage (discovery phase works)
- Backup continues to function normally regardless of email enabled/disabled/uninstalled state
- Kuma push failures do not cause backup failures (network issues don't break backups)
- Operator has clear documentation for disable/uninstall/verify/rollback procedures

## Out of Scope

- Migrating other PVE services to Kuma (only backup notifications)
- Configuring Kuma server or monitors (assumes Kuma already deployed from feature 011)
- Setting up Kuma notification channels (email, Slack, etc.) - operator responsibility
- Monitoring other than backup (Proxmox alerts, LXC notifications, etc. remain unchanged)
- Replacing email entirely at infrastructure level (other services may still use system mail)
- Automated rollback on Kuma failure (operator must manually re-enable email if needed)
- Health checks or monitoring of Kuma itself (assumes Kuma is reliable)

## Assumptions

- Uptime Kuma is already deployed and accessible (from feature 011-monitoring-alerting)
- Operator has access to Kuma web UI to create push monitors and retrieve URLs
- Kuma has notification channels configured (email, Slack, etc.) for alerting
- No other services on PVE host currently depend on Postfix/mailutils (or operator accepts discovery warnings)
- Operator will test Kuma monitoring for at least 1-2 weeks before uninstalling packages
- Operator understands rollback requires vault credentials to remain valid
- Network connectivity between PVE host and Kuma server is reliable (same LXC, local network)
- Operator follows phased approach: (1) test Kuma, (2) disable email, (3) verify, (4) optionally uninstall
