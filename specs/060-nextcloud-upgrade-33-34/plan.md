# Implementation Plan: Nextcloud Major Upgrade 32 → 34

**Branch**: `060-nextcloud-upgrade-33-34` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/060-nextcloud-upgrade-33-34/spec.md`

## Summary

Advance the Nextcloud LXC (VMID 105) from major **32 → 33 → 34** through the existing gated pipeline,
one image-tag major at a time, so the Euro-Office connector (needs NC 33–35) becomes installable in
feature `058`. Each hop is fenced by a **verified restore drill** of a fresh DB+config backup. The
existing `nextcloud` role already recreates the container on a version bump (the official image
auto-runs `occ upgrade` and refuses to skip majors); this feature closes the gaps around that: an
explicit `occ status` **upgrade-verification** step, an **uninstall** path that removes the flaky
built-in office editor (`richdocuments`/`richdocumentscode`), and a **restore-drill** script that
proves rollback before each hop.

## Technical Context

**Language/Version**: YAML (Ansible 2.x), Jinja2, Bash — no new language.
**Primary Dependencies**: `community.docker.docker_compose_v2`; official `nextcloud:33` / `nextcloud:34`
(Apache) images; `mariadb:11`; existing `nextcloud` and `nextcloud_backup` roles; `occ` CLI in the
`nextcloud_app` container.
**Storage**: MariaDB on local LXC disk (`/opt/nextcloud/mariadb`); **user data on Synology NFS**
(`/mnt/nextcloud/data`, durable); backup artefacts on NFS (`/mnt/nextcloud/backups`).
**Testing**: non-destructive `occ status`/`occ app:list` assertions in the role; on-demand
**restore drill** (scratch `mariadb:11` import); gated-pipeline post-apply healthcheck; LAB gate.
**Target Platform**: Nextcloud LXC (VMID 105, Debian) on Proxmox; deployed via `pve-service-deploy`.
**Project Type**: single (infra — Ansible role extension + one helper script).
**Performance Goals**: N/A (one-shot operational upgrade); readiness timeout sized to the observed
hop-1 DB-migration duration.
**Constraints**: no-major-skip (image-enforced); end on 34, never exceed 35; upgrade must not report
success while `maintenance:on` or `needsDbUpgrade:true`; backup fails closed if NFS unreachable.
**Scale/Scope**: single household instance; small user/file set.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1.*

| Principle | Assessment |
|---|---|
| **I. Spec-Driven** | ✅ Work is driven from this `specs/060-*/` dir; `tasks.md` to follow via `/speckit.tasks`. |
| **II. Secrets (NON-NEGOTIABLE)** | ✅ No new secrets. DB creds already sourced from `.env`/vault; restore-drill reads existing backup env, outputs no secrets. |
| **III. Separation of Concerns** | ✅ **No Terraform change** — LXC 105 already exists and is unchanged (existence/sizing untouched). Ansible owns the in-guest upgrade/config only. No mixing. |
| **IV. Code Economy (YAGNI)** | ✅ Extend the existing `nextcloud` role (add verify + `nextcloud_apps_remove` loop mirroring the existing disable loop) rather than new roles. One new helper script justified by FR-003 (restore drill has no existing equivalent). No new abstractions. contracts/ intentionally omitted (no new external interface). |
| **V. Dual-Provisioning Parity** | ✅ Runs via CI *and* laptop through `pve-service-deploy`; the restore-drill is a script runnable in both contexts with the same args. No CI-only assumptions. |
| **Test-Driven Changes** | ✅ Non-destructive validation added (occ status/app assertions); the restore drill *is* the safety test; each hop plan-then-apply through the gate. |

**Result**: PASS — no violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/060-nextcloud-upgrade-33-34/
├── plan.md              # This file
├── research.md          # Phase 0 (done)
├── data-model.md        # Phase 1 (done) — operational state machine + artefact
├── quickstart.md        # Phase 1 (done) — per-hop operator runbook
├── checklists/
│   └── requirements.md  # spec quality checklist (from /speckit.specify)
└── tasks.md             # Phase 2 (/speckit.tasks — NOT created here)
# contracts/  — intentionally omitted: this feature exposes no new external interface
#               (reverse-proxy route + healthcheck contract are unchanged).
```

### Source Code (repository root)

```text
ansible/
├── group_vars/services/vars.yml          # nextcloud_version: "32" → "33" → "34" (the pin, bumped per hop)
└── roles/
    ├── nextcloud/
    │   ├── defaults/main.yml              # drop richdocuments/richdocumentscode from nextcloud_apps_enable;
    │   │                                  #   add nextcloud_apps_remove: [richdocuments, richdocumentscode]
    │   └── tasks/main.yml                 # NEW: post-recreate upgrade verification (occ upgrade / maintenance
    │                                      #   off / assert occ status version+needsDbUpgrade) BEFORE app steps;
    │                                      #   NEW: app:disable + app:remove loop over nextcloud_apps_remove;
    │                                      #   post-hop: occ app:update --all + assert none disabled-by-incompat
    └── nextcloud_backup/                  # unchanged (produces the DB+config artefact)

scripts/
└── nextcloud/
    └── restore_drill.sh                   # NEW: force fresh backup → scratch mariadb import → verify sentinel →
                                           #   print artefact path (rollback point) → teardown. Dual-runnable.
```

**Structure Decision**: Single-project infra change. Everything lands in the **existing `nextcloud`
role** plus **one new dual-runnable script** for the restore drill; the version pin lives in the
canonical `group_vars/services/vars.yml`. No new roles, no Terraform, no reverse-proxy change.

## Implementation Phases (for /speckit.tasks to decompose)

1. **Role hardening (no version change yet)** — add the upgrade-verification block, the
   `nextcloud_apps_remove` list + task, and the post-hop app-compat assertion to the `nextcloud`
   role; keep `nextcloud_version: "32"`. Validate idempotently against the live 32 instance
   (no-op upgrade, apps removed). This is independently shippable and de-risks the hops.
2. **Restore-drill script** — `scripts/nextcloud/restore_drill.sh` + wire it into the runbook;
   prove it against the current instance (produces artefact, imports to scratch DB, sentinel matches).
3. **Hop 1 (32→33)** — drill → bump pin to `33` → promote→apply → verify (occ status 33.x,
   maintenance off, no pending DB upgrade, apps compatible, `nextcloud.hus-sky.no` 302). Record
   migration duration.
4. **Hop 2 (33→34)** — drill → bump pin to `34` → promote→apply → verify (occ status 34.x, same
   gates). Confirm `eurooffice` connector dependency (≥33) is now satisfiable (dry
   `occ app:install eurooffice` check — the SC-006 hand-off to `058`).

## Complexity Tracking

No constitution violations — section intentionally empty.
