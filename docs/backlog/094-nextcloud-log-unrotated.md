# Nextcloud's application log is 479 MB with no rotation

**Status**: Backlog — found 2026-10-24 measuring research R8 for `092` (log aggregation).
**Impact**: none observed yet — the NAS has headroom — but an unrotated, unbounded log file on
shared NFS storage is a disk-fill risk the same class as the Docker json-file issue `089` already
fixed, just not yet applied to this file.

## What was measured

A sample of `/mnt/nextcloud/data/nextcloud.log` on 2026-10-24 (research R8, spec 092):

- **479 MB**, 6,447 lines (so individual lines run to multiple MB — Nextcloud writes full
  request/stack context per entry).
- Level breakdown: 0 (debug) 1,964; 1 (info) 1,065; 2 (warning) 42; 3 (error) 149;
  **4 (fatal) 3,227** — more than half the sampled lines are fatal-level.
- No `logrotate` entry and no Nextcloud-side `log_rotate_size` configured anywhere in the repo
  (`ansible/roles/nextcloud/`).
- **fail2ban's `nextcloud` jail reads this exact file**
  (`ansible/host_vars/nextcloud.yml` → `fail2ban_jails`, `logpath`). This is why spec 092's
  Alloy `alloy_file_logs` declaration for Nextcloud also tails this file rather than switching
  Nextcloud to `log_type: errorlog` — that would stop fail2ban from seeing auth failures.
- Loki (spec 092) truncates any single line over 256 KB, so the largest individual log lines
  will not reach the store intact — a separate, accepted limitation of the collector, not of this
  item.

## Suggested fix

Set `log_rotate_size` in Nextcloud's `config.php` through `occ config:system:set` (the standard
built-in rotation, rather than external `logrotate`, since Nextcloud writes to NFS and manages
its own log file handle). Verify afterwards that:

- the file is capped and old content is rotated out instead of growing forever;
- fail2ban's `nextcloud` jail still matches the (now-rotated) current file
  (`logpath` may need a glob, e.g. `nextcloud.log*`, depending on how Nextcloud rotates); and
- Alloy's `tail_from_end: true` declaration for this file (spec 092) still behaves sensibly
  across a rotation (typically requires `loki.source.file`'s file-watch to pick up the
  truncation/recreation, which Alloy's `local.file_match` handles by re-stat'ing the path).
