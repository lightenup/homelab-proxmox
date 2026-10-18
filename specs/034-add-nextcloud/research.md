# Research Summary: Nextcloud Deployment for Docker Compose Homelab

**Date**: 2026-02-22
**Branch**: `034-add-nextcloud`
**Sources**: Nextcloud official docs, Docker Hub, Collabora docs, community forums, deployment guides

---

## 1. Recommended Database: MariaDB

**Decision**: MariaDB (over PostgreSQL)

**Rationale**:
- Nextcloud's official documentation explicitly recommends MySQL/MariaDB as the preferred database engine ([docs.nextcloud.com/server/28](https://docs.nextcloud.com/server/28/admin_manual/configuration_database/linux_database_configuration.html)).
- Nextcloud is a PHP application; PHP + MariaDB is the most tested and documented combination in the Nextcloud ecosystem.
- The majority of community guides, Docker examples, and official Docker Compose samples use MariaDB.
- Nextcloud has a partnership/alignment with MariaDB Foundation ([nextcloud.com blog, Sep 2025](https://nextcloud.com/blog/owning-your-data-the-open-source-path-with-nextcloud-and-mariadb/)).
- PostgreSQL is supported but has less coverage in Nextcloud docs (configuration details are thinner, some community members report edge cases).
- For a <5 user household deployment, MariaDB's simpler configuration and wider Nextcloud community support outweigh PostgreSQL's advanced features.

**Key MariaDB config requirements**:
```ini
# /etc/mysql/my.cnf (inside container, handled by image defaults)
transaction_isolation = READ-COMMITTED
binlog_format = ROW
innodb_file_per_table = 1
```

**Image**: `mariadb:11` (or latest LTS; the official Nextcloud Docker examples use `mariadb:10.11` or `mariadb:11`)

---

## 2. Collaborative Editing: Collabora Online (CODE) — Built-in

**Decision**: Use the Nextcloud Office app with the **built-in CODE server** (not a separate Collabora container)

**Options evaluated**:

| Option | Pros | Cons |
|--------|------|------|
| **Built-in CODE** (Nextcloud Office app) | Zero extra containers, simplest setup, sufficient for <5 users | Limited to ~5 concurrent editors, higher memory usage on NC container |
| **Separate Collabora/CODE container** | Better performance, scales independently | Extra container, DNS/proxy config, overkill for <5 users |
| **OnlyOffice** | Good MS Office compatibility | Separate container required, different codebase, less Nextcloud-native |

**Recommendation for this deployment**: Built-in CODE via the `richdocumentscode` app (Nextcloud Office / CODE built-in). This aligns with the spec's assumption of integrated deployment.

**How to enable**:
```bash
# Via occ inside the Nextcloud container
php occ app:install richdocuments        # Nextcloud Office (connector)
php occ app:install richdocumentscode    # Built-in CODE server
php occ app:enable richdocuments
php occ app:enable richdocumentscode
```

**If separate Collabora is ever needed** (future scale-up), the Docker Compose service would be:
```yaml
collabora:
  image: collabora/code:latest
  container_name: nextcloud_collabora
  environment:
    - aliasgroup1=https://nextcloud.local:443
    - extra_params=--o:ssl.enable=false --o:ssl.termination=true
  restart: always
  ports:
    - "9980:9980"
```

**Resource requirements for Collabora** (standalone): 1 GB RAM + ~100 MB per concurrent user, 2 CPU cores minimum.

---

## 3. Docker Compose Structure

Based on the Immich pattern already in the project (`ansible/roles/immich/templates/docker-compose.yml.j2`), the Nextcloud stack should follow the same Ansible-templated approach:

```yaml
# Recommended Docker Compose structure
services:
  nextcloud:
    image: nextcloud:{{ nextcloud_version }}
    container_name: nextcloud_app
    environment:
      - MYSQL_HOST=db
      - MYSQL_DATABASE=nextcloud
      - MYSQL_USER={{ nextcloud_db_user }}
      - MYSQL_PASSWORD={{ nextcloud_db_password }}
      - REDIS_HOST=redis
      - REDIS_HOST_PASSWORD={{ nextcloud_redis_password }}
      - NEXTCLOUD_TRUSTED_DOMAINS={{ nextcloud_trusted_domains }}
      - TRUSTED_PROXIES={{ nextcloud_trusted_proxies }}
      - OVERWRITEPROTOCOL=https
      - OVERWRITECLIURL=https://{{ nextcloud_domain }}
      - NEXTCLOUD_ADMIN_USER={{ nextcloud_admin_user }}
      - NEXTCLOUD_ADMIN_PASSWORD={{ nextcloud_admin_password }}
      - PHP_MEMORY_LIMIT=1024M
      - PHP_UPLOAD_LIMIT=16G
    volumes:
      - {{ nextcloud_data_dir }}/html:/var/www/html        # App files
      - {{ nextcloud_nfs_mount }}:/var/www/html/data        # User data on NAS
      - /etc/localtime:/etc/localtime:ro
    ports:
      - "{{ nextcloud_port }}:80"
    depends_on:
      - db
      - redis
    restart: always

  db:
    image: mariadb:11
    container_name: nextcloud_db
    environment:
      MYSQL_ROOT_PASSWORD: {{ nextcloud_db_root_password }}
      MYSQL_DATABASE: nextcloud
      MYSQL_USER: {{ nextcloud_db_user }}
      MYSQL_PASSWORD: {{ nextcloud_db_password }}
    command: --transaction-isolation=READ-COMMITTED --log-bin=binlog --binlog-format=ROW
    volumes:
      - {{ nextcloud_data_dir }}/mariadb:/var/lib/mysql
    restart: always
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: nextcloud_redis
    command: redis-server --requirepass {{ nextcloud_redis_password }}
    volumes:
      - {{ nextcloud_data_dir }}/redis:/data
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "{{ nextcloud_redis_password }}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
```

**Key architectural notes**:
- The `nextcloud:` image uses the Apache variant by default (includes Apache + PHP). The `-fpm` variant requires a separate nginx container — Apache variant is simpler for this deployment.
- User data volume (`/var/www/html/data`) points to NFS-backed mount on the NAS.
- App/config volume (`/var/www/html`) is on local disk for performance (contains PHP code, config files, app code).
- MariaDB data is on local disk (NOT NFS — see NFS gotchas section).
- Redis provides both caching and file locking.

---

## 4. Key config.php Settings

These are set automatically via environment variables on first run, but may need manual adjustment:

```php
<?php
$CONFIG = array(
  // === Reverse Proxy ===
  'trusted_proxies' => ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'],  // or specific proxy IP
  'overwriteprotocol' => 'https',
  'overwrite.cli.url' => 'https://nextcloud.local',
  'overwritehost' => 'nextcloud.local',

  // === Trusted Domains ===
  'trusted_domains' => array(
    0 => 'nextcloud.local',
    1 => '192.168.x.x',    // direct IP access for emergency admin
  ),

  // === Redis Caching ===
  'memcache.local' => '\\OC\\Memcache\\APCu',          // Local cache (fast, in-process)
  'memcache.distributed' => '\\OC\\Memcache\\Redis',    // Distributed cache
  'memcache.locking' => '\\OC\\Memcache\\Redis',        // File locking backend
  'filelocking.enabled' => true,
  'redis' => array(
    'host' => 'redis',
    'port' => 6379,
    'password' => 'REDIS_PASSWORD_HERE',
    'timeout' => 0.0,
  ),

  // === Database ===
  'dbtype' => 'mysql',
  'dbhost' => 'db',
  'dbname' => 'nextcloud',
  'dbuser' => 'nextcloud',
  'dbpassword' => 'DB_PASSWORD_HERE',

  // === Performance ===
  'default_phone_region' => 'NO',   // ISO 3166-1 country code
  'maintenance_window_start' => 3,  // UTC hour for background maintenance (3 AM UTC)

  // === Brute Force (see section 8) ===
  'auth.bruteforce.protection.enabled' => true,  // default: true
);
```

**Environment variables** recognized by the Nextcloud Docker image (set in docker-compose):
- `MYSQL_HOST`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` — database connection
- `REDIS_HOST`, `REDIS_HOST_PORT`, `REDIS_HOST_PASSWORD` — Redis connection
- `NEXTCLOUD_TRUSTED_DOMAINS` — space-separated list
- `TRUSTED_PROXIES` — space-separated list of IPs/CIDRs
- `OVERWRITEPROTOCOL` — `https`
- `OVERWRITECLIURL` — full URL (e.g., `https://nextcloud.local`)
- `NEXTCLOUD_ADMIN_USER`, `NEXTCLOUD_ADMIN_PASSWORD` — initial admin (first run only)
- `PHP_MEMORY_LIMIT` — e.g., `1024M`
- `PHP_UPLOAD_LIMIT` — e.g., `16G`

**Important**: Environment variables are only applied on **first installation**. After first run, changes must be made in `config/config.php` directly.

---

## 5. Apps: Enable and Disable

### Apps to ENABLE

| App ID | Name | Purpose | How |
|--------|------|---------|-----|
| `richdocuments` | Nextcloud Office | Collaborative editing connector | `php occ app:install richdocuments` |
| `richdocumentscode` | Collabora Online - Built-in CODE Server | Integrated editing engine | `php occ app:install richdocumentscode` |
| `deck` | Deck | Kanban boards (project tracking) | `php occ app:install deck` |
| `twofactor_totp` | Two-Factor TOTP Provider | TOTP 2FA | `php occ app:install twofactor_totp` |
| `bruteforcesettings` | Brute-force settings | UI to whitelist IPs for brute-force protection | `php occ app:install bruteforcesettings` |
| `text` | Text | Markdown/plain text editor | Bundled by default, ensure enabled |

### Apps to DISABLE

| App ID | Name | Reason |
|--------|------|--------|
| `photos` | Photos | Immich handles photo management |
| `spreed` | Talk | Video/voice calling not needed, requires TURN server |
| `mail` | Mail | Email handled by external providers |
| `calendar` | Calendar | Out of initial scope |
| `contacts` | Contacts | Out of initial scope |
| `weather_status` | Weather Status | Unnecessary |
| `dashboard` | Dashboard | Optional — can clutter the landing page |
| `recommendations` | Recommendations | Unnecessary AI suggestions |
| `firstrunwizard` | First Run Wizard | Only needed once, disable after setup |

**Disable command (inside Docker container)**:
```bash
docker exec --user www-data nextcloud_app php occ app:disable photos
docker exec --user www-data nextcloud_app php occ app:disable spreed
docker exec --user www-data nextcloud_app php occ app:disable mail
docker exec --user www-data nextcloud_app php occ app:disable calendar
docker exec --user www-data nextcloud_app php occ app:disable contacts
docker exec --user www-data nextcloud_app php occ app:disable weather_status
docker exec --user www-data nextcloud_app php occ app:disable firstrunwizard
```

**Note**: Some apps (like `mail`, `calendar`, `contacts`) may not be installed by default in recent Nextcloud versions — they need to be installed first to be present. If they're not installed, they simply won't appear. Check with `php occ app:list` to see what's actually installed.

**Automation approach**: Create an Ansible task or post-install script that runs these occ commands after the first deployment.

---

## 6. Backup Approach

### Database Backup (MariaDB)

**Command**:
```bash
docker exec nextcloud_db mysqldump \
  --single-transaction \
  --default-character-set=utf8mb4 \
  -u nextcloud -p'DB_PASSWORD' \
  nextcloud > /path/to/backups/nextcloud-db-$(date +%Y%m%d-%H%M%S).sql
```

**Key flags**:
- `--single-transaction`: Consistent backup without locking tables (InnoDB only)
- `--default-character-set=utf8mb4`: Preserve 4-byte Unicode characters

**Compression**:
```bash
docker exec nextcloud_db mysqldump --single-transaction \
  -u nextcloud -p'DB_PASSWORD' nextcloud | gzip > /path/to/backups/nextcloud-db-$(date +%Y%m%d).sql.gz
```

### Cron Schedule

Follow the Immich backup pattern established in the project:
```cron
# Daily database backup at 2:00 AM
0 2 * * * /opt/nextcloud/backup-db.sh >> /var/log/nextcloud-backup.log 2>&1
```

### Full Backup Checklist

| Component | What to Back Up | How | Location |
|-----------|----------------|-----|----------|
| Database | MariaDB dump | `mysqldump --single-transaction` | NAS backup directory |
| Config | `config/config.php` | File copy | NAS backup directory |
| User data | `/var/www/html/data` | Already on NAS — covered by NAS backup | NAS (Synology snapshots/HyperBackup) |
| App data | `/var/www/html/custom_apps` | File copy (or rebuild via occ) | NAS backup directory |

### Maintenance Mode for Backups

For consistent backups, enable maintenance mode before backup:
```bash
docker exec --user www-data nextcloud_app php occ maintenance:mode --on
# ... perform backup ...
docker exec --user www-data nextcloud_app php occ maintenance:mode --off
```

### Retention

- Keep **7 daily** backups
- Keep **4 weekly** backups (optional)
- Rotate with `find /path/to/backups -name "nextcloud-db-*.sql.gz" -mtime +7 -delete`

---

## 7. Resource Sizing

### For <5 users with collaborative editing (built-in CODE)

| Component | CPU | RAM | Disk |
|-----------|-----|-----|------|
| **Nextcloud (Apache + PHP + built-in CODE)** | 2 cores | 1–2 GB | 2 GB (app code/config) |
| **MariaDB** | 1 core (shared) | 512 MB–1 GB | 1 GB+ (grows with metadata) |
| **Redis** | minimal | 64–128 MB | <100 MB |
| **Total recommended** | **2–4 cores** | **2–4 GB** | 5 GB local + NAS for user data |

**Source guidance**:
- Nextcloud official: Minimum 512 MB RAM per process, recommended 2–4 GB for small deployments ([docs.nextcloud.com](https://docs.nextcloud.com/server/25/admin_manual/installation/system_requirements.html))
- Nextcloud AIO recommends: 4 CPU cores, 8 GB RAM (but that includes Talk, full Collabora, etc.)
- For this deployment (no Talk, built-in CODE, <5 users): **2 CPU cores + 2 GB RAM is the minimum; 4 cores + 4 GB is comfortable.**
- Collabora standalone requires 1 GB + 100 MB/user + 2 CPU cores — but the built-in CODE server is lighter.

**PHP settings for the Nextcloud container**:
```
PHP_MEMORY_LIMIT=1024M     # 1 GB for PHP processes (includes CODE)
PHP_UPLOAD_LIMIT=16G       # Max upload size
```

**LXC container sizing** (for the Proxmox LXC that runs Docker):
- Allocate **4 GB RAM** and **2–4 CPU cores** to the LXC container
- This gives headroom for all three containers (Nextcloud + MariaDB + Redis)

---

## 8. Security: Brute-Force, TOTP, Rate Limiting

### Brute-Force Protection

**Status**: Enabled by default. No config changes needed.

**How it works**:
- Tracks failed login attempts per IP/subnet
- Applies increasing delays after failures: starts at 200ms, maximum 25–30 seconds delay
- After severe repeated failures, blocks the IP for up to 30 minutes
- Successful login clears previous invalid attempts for that IP
- Delays can accumulate up to 24 hours for persistent attackers

**Config** (defaults are fine, but available in `config.php`):
```php
'auth.bruteforce.protection.enabled' => true,  // default: true
```

**Whitelist trusted IPs** (e.g., your LAN gateway to avoid locking yourself out):
```bash
# Via occ command
docker exec --user www-data nextcloud_app php occ config:system:set auth.bruteforce.protection.whitelist 0 --value="192.168.1.0/24"
```

Or install the `bruteforcesettings` app for a web UI to manage whitelisted IPs.

### TOTP Two-Factor Authentication

**Setup**:
1. Install the app: `php occ app:install twofactor_totp`
2. Enable it: `php occ app:enable twofactor_totp`
3. Each user enables TOTP in their **Personal Settings → Security** section
4. Users scan a QR code with an authenticator app (Google Authenticator, Aegis, etc.)
5. Backup codes are automatically available (`twofactor_backupcodes` is bundled)

**Admin enforcement** (optional):
```bash
# Force all users to use 2FA
php occ twofactorauth:enforce --on
# Or enforce for specific groups
php occ twofactorauth:enforce --on --group=admin
```

### Rate Limiting

**Status**: Nextcloud has built-in rate limiting via annotations on API endpoints. No separate configuration needed.

**How it works**:
- API endpoints are annotated with rate limits (e.g., `@UserRateThrottle` and `@AnonRateThrottle`)
- Uses the brute-force protection infrastructure to track and throttle
- For a reverse-proxy setup, ensure the real client IP is forwarded (via `X-Forwarded-For` header) and `trusted_proxies` is configured — otherwise all requests appear from the proxy IP and rate limiting becomes overly aggressive.

**Critical for reverse proxy**: If `trusted_proxies` is not set correctly, ALL requests appear to come from the proxy IP, which can trigger brute-force protection against the proxy itself. This is the #1 gotcha reported in forums.

---

## 9. NFS-Backed Data Directory: Gotchas

**This is one of the most problematic areas** based on community reports. Key issues and mitigations:

### Permission Issues (Critical)

**Problem**: Nextcloud runs as `www-data` (UID 33, GID 33) inside the container. NFS mounts may not preserve or map this UID/GID correctly.

**Mitigations**:
1. **NFS export options** (on the Synology NAS):
   - Use `no_root_squash` or `all_squash` with `anonuid=33,anongid=33` to map all access to UID/GID 33
   - Or use `no_squash` if the host UID 33 matches the container UID 33
2. **Mount options** (on the Proxmox host / LXC):
   ```
   nfs_server:/nextcloud-data /mnt/nextcloud-data nfs defaults,noatime 0 0
   ```
3. **Verify**: After mounting, ensure `ls -la /mnt/nextcloud-data` shows UID 33 ownership

### File Locking Issues

**Problem**: NFS v3 has limited file locking support. Nextcloud relies on file locking for concurrent access.

**Mitigation**:
- Use **NFSv4** which has proper file locking support
- Nextcloud's Redis-based file locking (`memcache.locking`) handles application-level locking, which works regardless of filesystem locking — **this is why Redis is essential for NFS setups**

### `.ncdata` Marker File

**Problem**: Nextcloud checks for a `.ocdata` file in the data directory root. If NFS mount fails silently, this file is missing, and Nextcloud shows "data directory not writable" errors.

**Mitigation**: Ensure the NFS mount is verified before the Nextcloud container starts. The Ansible role should check mount availability.

### Performance

**Problem**: NFS adds latency. File scanning, thumbnail generation, and large file operations are slower.

**Mitigations**:
- Use **NFSv4** with `noatime` mount option
- Redis caching reduces repeated filesystem metadata lookups
- Set `'filesystem_check_changes' => 1` in config.php (check on each request, which is the default) — or `0` to never check (faster but requires manual `occ files:scan` after external changes)

### Database on NFS: DO NOT DO THIS

**Critical**: MariaDB/PostgreSQL data files should **never** be stored on NFS. Database engines require low-latency, POSIX-compliant filesystem behavior. NFS introduces latency, caching inconsistencies, and locking issues that can corrupt the database.

**Solution**: Store MariaDB data on local disk (the LXC container's local storage). Back up the database with `mysqldump` to NAS on a schedule.

---

## 10. Summary of Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | MariaDB 11 | Nextcloud-recommended, best community support, PHP ecosystem alignment |
| Collaborative editing | Built-in CODE (`richdocumentscode`) | Simplest for <5 users, no extra container, spec requirement |
| Caching | Redis 7 + APCu | Redis for distributed cache + locking; APCu for local cache |
| Docker image variant | `nextcloud:XX` (Apache) | Simpler than FPM+nginx, sufficient for this scale |
| Data storage | NFS mount to NAS for user data; local disk for DB | NFS for data resilience; local disk for DB performance |
| Backup | `mysqldump --single-transaction` daily via cron | Standard approach, consistent with Immich backup pattern |
| 2FA | TOTP via `twofactor_totp` app | Standard, no external dependencies |
| Brute-force | Built-in (default enabled) | No config needed; whitelist LAN subnet |
| Rate limiting | Built-in via API annotations | No separate config; ensure trusted_proxies is set |
| LXC resources | 4 GB RAM, 2–4 CPU cores | Covers Nextcloud + MariaDB + Redis comfortably |

---

## 11. Codebase Pattern Verification (Post-Research Addendum)

**Added**: 2026-02-22 (after codebase exploration during plan phase)

These findings were discovered by examining the existing Immich, Jellyfin, and reverse proxy implementations. They correct or supplement the original research.

### 11.1 Docker Compose Templating Pattern

**Finding**: The project uses Jinja `{{ var }}` rendering in docker-compose templates, NOT `${VAR}` shell-style interpolation.

- `immich/templates/docker-compose.yml.j2` uses Jinja for image versions, ports, volume paths, and even direct secret values (e.g., `POSTGRES_PASSWORD: {{ immich_db_password }}`).
- The main service uses `env_file: - .env` for runtime container environment variables.
- The `.env` file is also a Jinja template, rendered by Ansible with mode 0600.
- **Correction**: The Docker Compose section (§3) of this research uses Jinja `{{ var }}` correctly. The contracts previously suggested `${VAR}` for some values — this has been corrected.

### 11.2 Caddy Reverse Proxy: Multi-Service Routing

**Finding**: The existing `immich.caddy.j2` uses `:80` as a catch-all site address. For multiple services, Caddy supports hostname-based virtual hosting.

- `immich.caddy.j2` content: `:80 { reverse_proxy {{ immich_ip }}:{{ immich_port }} { header_up X-Forwarded-Proto http } }`
- The main Caddyfile has `auto_https off` and imports `{{ caddy_conf_dir }}/*.caddy`
- Each service `.caddy` file must be a standalone valid Caddyfile (required by the `caddy validate` step)
- **Decision**: Nextcloud uses `http://nextcloud.local` as site address. Caddy merges imported site blocks: `http://nextcloud.local` handles Nextcloud traffic, `:80` catches everything else (Immich).
- **DNS requirement**: For proxy routing to work, `nextcloud.local` must resolve to the proxy IP (`192.168.20.211`), not the LXC IP. This requires a DNS entry or `/etc/hosts` configuration. Direct access via `http://192.168.20.216:8080` is always available as a fallback.

### 11.3 Terraform `features_mount` Variable

**Finding**: The `features_mount` variable is declared in `lxc_service/variables.tf` but is NOT referenced in the module's `main.tf` resource block.

- The module comment says: "mount feature is applied host-side by orchestrator via `pct set`"
- The variable exists for documentation and potential future use
- The actual NFS bind mount works via the `mountpoints` variable's dynamic `mountpoint` blocks in `proxmox_lxc`
- Jellyfin's module call includes `features_mount = "nfs"` — Nextcloud should follow the same pattern for consistency

### 11.4 Backup Pattern: systemd Timers (not cron)

**Finding**: The `immich_backup` role uses **systemd timers** (service + timer units), not cron.

- **Correction to §6**: The backup section references cron (`0 2 * * *`), but the actual project pattern uses systemd timers with `OnCalendar` syntax (e.g., `*-*-* 04:30:00`).
- Nextcloud backup follows the systemd timer pattern: `nextcloud-backup.service` (oneshot) + `nextcloud-backup.timer`.

### 11.5 IP Subnet

**Finding**: `docs/naming-and-mdns.md` shows `192.168.1.x` but `prod.tfvars.example` shows `192.168.20.x`.

- The tfvars file is authoritative for IP assignments.
- The docs table may be outdated.
- Nextcloud uses `192.168.20.216/24` (from tfvars pattern).

## 12. References

- Nextcloud Docker Hub: https://hub.docker.com/_/nextcloud/
- Nextcloud Admin Manual (config.php): https://docs.nextcloud.com/server/30/admin_manual/configuration_server/config_sample_php_parameters.html
- Nextcloud Database Config: https://docs.nextcloud.com/server/28/admin_manual/configuration_database/linux_database_configuration.html
- Nextcloud Reverse Proxy: https://docs.nextcloud.com/server/32/admin_manual/configuration_server/reverse_proxy_configuration.html
- Nextcloud Brute Force Protection: https://docs.nextcloud.com/server/stable/admin_manual/configuration_server/bruteforce_configuration.html
- Nextcloud Two-Factor Auth: https://docs.nextcloud.com/server/stable/admin_manual/configuration_user/two_factor-auth.html
- Nextcloud Memory Caching: https://docs.nextcloud.com/server/22/admin_manual/configuration_server/caching_configuration.html
- Nextcloud Apps Management: https://docs.nextcloud.com/server/stable/admin_manual/apps_management.html
- Collabora CODE Docker: https://sdk.collaboraonline.com/docs/installation/CODE_Docker_image.html
- Deck App: https://apps.nextcloud.com/apps/deck
- Nextcloud GitHub (Docker): https://github.com/nextcloud/docker
