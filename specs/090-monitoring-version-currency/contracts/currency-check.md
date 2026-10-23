# Contract: Version currency check

The check's interfaces are its command line, its scheduled workflow, and its ntfy message.

## 1. Command line

```text
python -m homelab_proxmox_orchestrator.version_currency [--dry-run] [--sources PATH] [--repo-root PATH]
```

| Option | Default | Meaning |
|---|---|---|
| `--dry-run` | off | Print the report to stdout and do not publish. `NTFY_TOKEN` is not needed. |
| `--sources` | `ansible/version-sources.yml` | Pin → source map ([data-model §2](../data-model.md)) |
| `--repo-root` | auto-detect (as the guardrail tests do) | Base for the `file` paths in the sources map |

| Environment | Required | Meaning |
|---|---|---|
| `NTFY_TOKEN` | when not `--dry-run` | Bearer token of the `version_check` publisher |
| `NTFY_URL` | no; default `https://ntfy.hus-sky.no` | Server base URL |
| `NTFY_TOPIC` | no; default `versions` | Topic |
| `GITHUB_TOKEN` | no | Raises the GitHub API limit. Unauthenticated works for the current pin count. |

**Exit codes**

| Code | When |
|---|---|
| `0` | Every source was read, and either there were no findings (nothing published) or the report was published |
| `1` | Any source could not be fetched or parsed, **or** the publish failed (any status other than `200`, or a connection error or timeout) |
| `2` | Bad input: the sources file is invalid, a `file` is missing, a `variable` is not found in its file, or `NTFY_TOKEN` is missing without `--dry-run` |

Never: exit `0` after an error. Never: the token in stdout, stderr or the message body.

Every HTTP call has a 20 s timeout and no retries. The next weekly run is the retry. This follows
the 082 contract's warning that retries can duplicate messages.

## 2. Scheduled workflow: `.github/workflows/version-currency.yml`

| Item | Value |
|---|---|
| Triggers | `schedule: cron "0 6 * * 1"` (Mondays 06:00 UTC); `workflow_dispatch` with input `dry_run` (boolean, default `false`) |
| Runner | `[self-hosted]` (`pi-ci`, LAN) |
| Timeout | `timeout-minutes: 10` |
| Secrets used | `ANSIBLE_VAULT_PASSWORD` (existing), only to read `ntfy_version_check_token` from `ansible/group_vars/services/vault.yml`; the value is masked before use |
| Token | Workflow `GITHUB_TOKEN`, passed as `GITHUB_TOKEN`; permissions `contents: read` |
| Result | The job fails whenever the command exits non-zero. GitHub notifies the repo owner of failed scheduled runs. |

A scheduled run checks `main`. A manual run checks the branch it is started on (SC-003).

## 3. ntfy publisher (082 contract onboarding)

| Item | Value |
|---|---|
| Account | `version_check` in `ntfy_users` (`roles/ntfy/defaults/main.yml`) |
| Topic | `versions` (new) |
| ACL | `write-only` on `versions` |
| Vault | `ntfy_version_check_token`, `ntfy_version_check_password_hash` in `group_vars/services/vault.yml` |
| Owner | Subscribes to `versions` in the app; the existing `*` read grant covers it |
| 082 SC-002 matrix | Extended with the new row and column |

## 4. Message

Sent only when there is at least one finding or error.

```text
POST {NTFY_URL}/{NTFY_TOPIC}
Authorization: Bearer <token>
Title: Version pins: <F> behind[, <E> check errors]
Priority: <4 if any support-ended or errors, else 3>
Tags: package
```

Body (plain text, under the 32 KB limit). One line per finding, in sorted order: monitoring pins
first, then service pins.

```text
prometheus_version v3.13.5 -> v3.13.6 (newer patch on LTS 3.13)
grafana_version 13.2.4 -> 13.3.0 (newer release)
telegraf_version 1.40.2: support ends 2026-12-07 (in 25 days)
nextcloud_version 34: support ended 2026-10-01

Not checked: immich_postgres_image (digest-pinned; upgraded with Immich), ...
Check errors: endoflife.date/grafana: timeout after 20s
Run: <workflow run URL, when available>
```

A pin whose source failed appears only under "Check errors", never as current.
