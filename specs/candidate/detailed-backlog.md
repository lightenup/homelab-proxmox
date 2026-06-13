# Transcriber Homelab Deployment — Infrastructure Backlog

**Scope**: All work that lives in the `homelab-proxmox` repo to deploy and operate
the transcriber service on Proxmox. The transcriber application code (API server,
RemoteBackend, Mac shim, metrics endpoint) is developed separately in the
`transcriber` repo (merged to main).

**Prerequisite**: `ghcr.io/lightenup/transcriber:latest` must be publicly pullable.
This image is built and pushed by CI in the transcriber repo on every push to `main`.
✓ **Done** — image published, verified public.

**Depends on**: transcriber repo merged + Docker image published. ✓ Both done.

---

## Epic: Deploy Transcriber Service on Proxmox

**Goal**: Provision an LXC, deploy the transcriber API + orchestrator as Docker
Compose services, wire up NAS storage, monitoring, and reverse proxy — following
the exact same IaC patterns as Immich, Nextcloud, and Jellyfin.

**Vertical slice**: `terraform apply` → `ansible-playbook` → service healthy at
`https://transcriber.hus-sky.no/health` → Prometheus scraping → Grafana dashboard

### Architecture

```
ghcr.io/lightenup/transcriber:latest  (public, no auth needed on pull)
         │
         ▼
Terraform creates LXC (192.168.1.217)
  │
  ▼
Ansible configures LXC:
  ├── lxc_base role (node_exporter, SSH, apt)
  ├── nfs_mount role (/mnt/nas → Synology)
  ├── geerlingguy.docker role (Docker engine)
  ├── transcriber role
  │   ├── preflight: assert NAS mount, Docker running, required vars
  │   ├── create dirs: /opt/transcriber-app, /var/lib/transcriber, NAS subdirs
  │   ├── deploy /opt/transcriber-app/docker-compose.yml from template
  │   ├── deploy /etc/transcriber/transcriber.toml from template
  │   └── docker_compose_v2: pull + start api + worker services
  └── tailscale_host role (join mesh)
         │
         ▼
Caddy (192.168.1.211):
  transcriber.hus-sky.no → 192.168.1.217:8080
  (one new task in reverse_proxy/tasks/main.yml + transcriber.caddy.j2 template)
         │
         ▼
Monitoring (192.168.1.214):
  Prometheus scrapes via monitoring_contract in host_vars/transcriber.yml
  (no changes to prometheus.yml.j2 — it iterates monitoring_contract automatically)
  Grafana dashboard JSON file
  Alert rules embedded in monitoring_contract in host_vars
```

### Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LXC IP | 192.168.1.217 | Next available in prod range |
| Resources | 2 cores / 2048 MB / 16 GB disk | API + orchestrator only, no ML inference |
| NAS mount | `/mnt/nas` → `/mnt/nas/homelab_transcriber/` on host | Consistent with other NFS bind mounts |
| NFS subdirs | `inbox/`, `output/`, `archive/` | Created by Ansible role, not Terraform |
| Container runtime | Docker Compose via `geerlingguy.docker` dependency | Matches Immich/Nextcloud/Jellyfin pattern |
| Image registry | `ghcr.io/lightenup/transcriber` (public) | No pull auth needed; private source repo |
| Image tagging | `latest` on main, `vX.Y.Z` on git tag | `transcriber_image_tag` var controls it |
| Two Compose services | `transcriber-api` + `transcriber-worker` | Same image, different CMD; independent restart |
| Config delivery | `transcriber.toml` bind-mounted at `/config/transcriber.toml` | Matches toml config format from transcriber repo |
| Molecule testing | `geerlingguy/docker-debian12-ansible` | Matches existing nightly CI target distro |
| Monitoring integration | `monitoring_contract` in host_vars | Prometheus template iterates this automatically — no changes to prometheus.yml.j2 |
| Alert rules | Embedded in `monitoring_contract.alert_rules` in host_vars | Consistent with immich/nextcloud pattern |
| Reverse proxy | One new task in reverse_proxy/tasks/main.yml + caddy template | Matches immich.caddy.j2 / nextcloud.caddy.j2 pattern |
| Healthcheck | `healthcheck_url` + `healthcheck_profile` in host_vars | Picked up automatically by healthcheck.py |

---

## User Stories

### US-0: Publish Docker image ✓ DONE

`ghcr.io/lightenup/transcriber:latest` is public and pullable without auth.
See transcriber repo commit "Add Docker image build for LXC deployment".

---

### US-1: Provision transcriber LXC via Terraform (Priority: P1)

> As a developer, I can create the transcriber LXC container in one `terraform apply`.

**Why P1**: Nothing else can happen until the container exists.

**Acceptance criteria**:
- `terraform plan` in `terraform/services/transcriber/` shows 1 resource to create
- `terraform apply` creates LXC: hostname `transcriber`, 2 cores, 2048 MB, 16 GB disk
- NFS bind mount: `/mnt/nas` (LXC) → `/mnt/nas/homelab_transcriber` (Proxmox host)
- Static IP 192.168.1.217/24, gateway and DNS from shared variables
- SSH accessible with existing deploy key
- Pattern: copy `terraform/services/immich/main.tf` and adapt

**Files to create/modify**:

`terraform/services/transcriber/main.tf` (new — model on immich):
```hcl
locals {
  all_mounts_transcriber     = lookup(var.service_mountpoints, "transcriber", {})
  storage_mounts_transcriber = { for k, v in local.all_mounts_transcriber : k => v if !startswith(v.volume, "/") }
}

module "transcriber_lxc" {
  source = "../../modules/lxc_service"

  name         = "transcriber-lxc"
  hostname     = "transcriber"
  node         = var.proxmox_node
  ostemplate   = var.lxc_template
  storage_pool = var.storage_pool

  cores   = 2
  memory  = 2048
  disk_gb = 16

  bridge          = var.services_bridge
  ip              = var.service_ips["transcriber"]
  gateway         = var.network_gateway
  nameserver      = var.nameserver
  searchdomain    = var.searchdomain
  ssh_public_keys = join("\n", var.ssh_public_keys)

  mountpoints = values(local.storage_mounts_transcriber)
}
```

`terraform/environments/prod.tfvars` — add to `service_ips`:
```hcl
transcriber = "192.168.1.217/24"
```

`terraform/environments/prod.tfvars` — add to `service_mountpoints`:
```hcl
transcriber = {
  nas = {
    mp     = "/mnt/nas"
    volume = "/mnt/nas/homelab_transcriber"
  }
}
```

`ansible/inventories/prod/hosts.yml` — add under `services`:
```yaml
transcriber:
  ansible_host: 192.168.1.217
  ansible_user: root
```

---

### US-2: Deploy transcriber service via Ansible (Priority: P2)

> As a developer, `ansible-playbook playbooks/transcriber.yml` fully configures the
> LXC — Docker engine, config file, both Compose services, NAS directories.

**Why P2**: Once the container exists, the service must be deployable reproducibly.

**Acceptance criteria**:
- `ansible-playbook playbooks/transcriber.yml` completes cleanly on a fresh LXC
- Docker engine installed via `geerlingguy.docker` role
- NAS subdirectories exist: `inbox/`, `output/`, `archive/` under `/mnt/nas/`
- `/etc/transcriber/transcriber.toml` deployed from template with correct values
- `/opt/transcriber-app/docker-compose.yml` deployed from template
- `transcriber-api` container up, port 8080 responding `{"status": "ok"}` at `/health`
- `transcriber-worker` container up
- Both services use `restart: unless-stopped`
- Second playbook run is idempotent
- `node_exporter` already deployed via `lxc_base` role (no action needed)
- `molecule test` passes locally

**Files to create**:

```
ansible/roles/transcriber/
  defaults/main.yml
  tasks/
    main.yml
    preflight.yml
  handlers/
    main.yml
  templates/
    docker-compose.yml.j2
    transcriber.toml.j2
  molecule/
    default/
      molecule.yml
      converge.yml
      verify.yml
ansible/playbooks/transcriber.yml
ansible/host_vars/transcriber.yml
```

**`ansible/roles/transcriber/defaults/main.yml`**:
```yaml
---
transcriber_image: "ghcr.io/lightenup/transcriber"
transcriber_image_tag: "latest"
transcriber_api_port: 8080
transcriber_api_host: "0.0.0.0"
transcriber_api_key: ""
transcriber_backend_type: "remote"
transcriber_backend_remote_url: ""   # set in host_vars (Mac Tailscale IP)
transcriber_install_dir: "/opt/transcriber-app"
transcriber_config_dir: "/etc/transcriber"
transcriber_db_dir: "/var/lib/transcriber"
transcriber_nas_mount: "/mnt/nas"
transcriber_inbox_path: "/mnt/nas/inbox"
transcriber_output_path: "/mnt/nas/output"
transcriber_db_path: "/var/lib/transcriber/jobs.db"
transcriber_max_workers: 1
transcriber_max_retries: 3
transcriber_poll_interval: 10
transcriber_max_upload_mb: 500
transcriber_require_nas_mount: true
```

**`ansible/roles/transcriber/tasks/preflight.yml`** — model on immich:
- Check `/mnt/nas` exists (fail if `transcriber_require_nas_mount`)
- Verify NAS is writable (touch test file)
- Check Docker daemon is running
- Assert `transcriber_backend_remote_url` is defined and non-empty

**`ansible/roles/transcriber/tasks/main.yml`** — model on immich:
- Include preflight.yml
- Create dirs: `transcriber_install_dir`, `transcriber_config_dir`, `transcriber_db_dir`
- Create NAS subdirs: `inbox/`, `output/`, `archive/` under `transcriber_nas_mount`
- Deploy `docker-compose.yml.j2` → `{{ transcriber_install_dir }}/docker-compose.yml`, notify restart
- Deploy `transcriber.toml.j2` → `{{ transcriber_config_dir }}/transcriber.toml`, notify restart
- `community.docker.docker_compose_v2`: `project_src: "{{ transcriber_install_dir }}"`, `pull: always`
- `ansible.builtin.uri`: verify `http://127.0.0.1:{{ transcriber_api_port }}/health` returns 200

**`ansible/roles/transcriber/handlers/main.yml`**:
```yaml
---
- name: Restart transcriber
  community.docker.docker_compose_v2:
    project_src: "{{ transcriber_install_dir }}"
    state: restarted
```

**`ansible/roles/transcriber/templates/docker-compose.yml.j2`**:
```yaml
services:
  transcriber-api:
    container_name: transcriber_api
    image: {{ transcriber_image }}:{{ transcriber_image_tag }}
    command: ["transcriber", "api"]
    volumes:
      - "{{ transcriber_config_dir }}/transcriber.toml:/config/transcriber.toml:ro"
      - "{{ transcriber_nas_mount }}:{{ transcriber_nas_mount }}"
      - "{{ transcriber_db_dir }}:{{ transcriber_db_dir }}"
      - "/etc/localtime:/etc/localtime:ro"
    ports:
      - "{{ transcriber_api_port }}:8080"
    restart: unless-stopped

  transcriber-worker:
    container_name: transcriber_worker
    image: {{ transcriber_image }}:{{ transcriber_image_tag }}
    command: ["transcriber", "orchestrate"]
    volumes:
      - "{{ transcriber_config_dir }}/transcriber.toml:/config/transcriber.toml:ro"
      - "{{ transcriber_nas_mount }}:{{ transcriber_nas_mount }}"
      - "{{ transcriber_db_dir }}:{{ transcriber_db_dir }}"
      - "/etc/localtime:/etc/localtime:ro"
    restart: unless-stopped
```

**`ansible/roles/transcriber/templates/transcriber.toml.j2`**:
```toml
[api]
host = "{{ transcriber_api_host }}"
port = 8080
api_key = "{{ transcriber_api_key }}"
max_upload_mb = {{ transcriber_max_upload_mb }}

[orchestrator]
inbox = "{{ transcriber_inbox_path }}"
db_path = "{{ transcriber_db_path }}"
max_workers = {{ transcriber_max_workers }}
max_retries = {{ transcriber_max_retries }}
poll_interval = {{ transcriber_poll_interval }}

[backend]
type = "{{ transcriber_backend_type }}"
remote_url = "{{ transcriber_backend_remote_url }}"
```

**`ansible/roles/transcriber/molecule/default/molecule.yml`** — model on geerlingguy.docker:
```yaml
---
dependency:
  name: galaxy
  options:
    ignore-errors: true
driver:
  name: docker
platforms:
  - name: instance
    image: "geerlingguy/docker-${MOLECULE_DISTRO:-debian12}-ansible:latest"
    command: ""
    volumes:
      - /sys/fs/cgroup:/sys/fs/cgroup:rw
    cgroupns_mode: host
    privileged: true
    pre_build_image: true
provisioner:
  name: ansible
  playbooks:
    converge: converge.yml
```

**`ansible/roles/transcriber/molecule/default/converge.yml`** — model on geerlingguy.docker:
```yaml
---
- name: Converge
  hosts: all
  become: true

  pre_tasks:
    - name: Update apt cache
      apt: update_cache=yes cache_valid_time=600
      when: ansible_os_family == 'Debian'

    - name: Wait for systemd to complete initialization
      command: systemctl is-system-running
      register: systemctl_status
      until: >
        'running' in systemctl_status.stdout or
        'degraded' in systemctl_status.stdout
      retries: 30
      delay: 5
      when: ansible_service_mgr == 'systemd'
      changed_when: false
      failed_when: systemctl_status.rc > 1

    - name: Create mock NAS mount directory
      ansible.builtin.file:
        path: /mnt/nas
        state: directory
        mode: '0755'

  roles:
    - role: geerlingguy.docker
    - role: transcriber
      vars:
        transcriber_require_nas_mount: false
        transcriber_backend_remote_url: "http://192.168.1.1:8765"
```

**`ansible/roles/transcriber/molecule/default/verify.yml`**:
```yaml
---
- name: Verify
  hosts: all
  become: true
  tasks:
    - name: Check transcriber-api container is running
      community.docker.docker_container_info:
        name: transcriber_api
      register: container_info
      failed_when: not container_info.container.State.Running

    - name: Verify /health endpoint responds 200
      ansible.builtin.uri:
        url: "http://127.0.0.1:8080/health"
        status_code: 200
      retries: 10
      delay: 5
```

**`ansible/playbooks/transcriber.yml`** — model on immich.yml:
```yaml
---
- name: Configure base for Transcriber
  hosts: transcriber
  become: true
  roles:
    - lxc_base

- name: Configure Transcriber
  hosts: transcriber
  become: true
  vars:
    transcriber_require_nas_mount: "{{ (deploy_environment | default('prod')) != 'lab' }}"
  roles:
    - geerlingguy.docker
    - transcriber
```

**`ansible/playbooks/services.yml`** — add entry:
```yaml
- name: Configure Transcriber
  import_playbook: transcriber.yml
  tags: transcriber
```

**`ansible/host_vars/transcriber.yml`** — initial version (monitoring_contract populated in US-4):
```yaml
transcriber_backend_remote_url: ""  # set to Mac Tailscale IP before deploy

healthcheck_url:
  scheme: http
  port: 8080
  path: /health
healthcheck_profile: lan
healthcheck_expect_status: 200
```

---

### US-3: Tailscale mesh join (Priority: P3)

> As a developer, the transcriber LXC joins the Tailscale mesh so the Mac can
> reach it remotely without VPN configuration changes.

**Why P3**: Required for remote access from outside LAN; also needed before the Mac
`transcriber_backend_remote_url` can use a stable Tailscale address.

**Acceptance criteria**:
- `tailscale status` on the transcriber LXC shows it connected to the mesh
- Mac can reach `192.168.1.217:8080` via Tailscale from outside the LAN
- No Tailscale ACL changes needed (inherits existing policy)

**Files to modify**:
- `ansible/playbooks/transcriber.yml` — add `tailscale_host` role to second play
- Tailscale auth key must be in vault (check existing `tailscale_host` role for var name)

---

### US-4: Prometheus monitoring + Grafana dashboard (Priority: P4)

> As a user, I can see transcriber job queue depth, throughput, and failure rate
> in my existing Grafana instance.

**Why P4**: Observability for production trust.

**Key insight**: Prometheus scrape targets and alert rules are driven entirely by
`monitoring_contract` in host_vars. **No changes to `prometheus.yml.j2` needed.**
The template iterates `groups['all']` and picks up any host with
`monitoring_contract.enabled: true`.

**Acceptance criteria**:
- Prometheus scrapes `http://192.168.1.217:8080/metrics` successfully
- Grafana dashboard shows: queue depth (gauge), job throughput (rate), processing
  duration (histogram), dead-letter count
- Alert rules fire correctly:
  - `TranscriberQueueBacklog`: `transcriber_queue_depth > 5` for 15m
  - `TranscriberDeadLetters`: increase in `transcriber_jobs_dead_total`

**Files to create/modify**:

`ansible/host_vars/transcriber.yml` — add `monitoring_contract` block:
```yaml
monitoring_contract:
  enabled: true
  scrape_targets:
    - job_name: "transcriber"
      port: 8080
      path: "/metrics"
      scrape_interval: "30s"
  alert_rules:
    - alert: TranscriberQueueBacklog
      expr: |
        transcriber_queue_depth > 5
      for: "15m"
      severity: "warning"
      summary: !unsafe "Transcriber queue backlog on {{ $labels.instance }}"
      description: !unsafe "Transcriber queue depth above 5 for 15 minutes (current: {{ $value }})."
    - alert: TranscriberDeadLetters
      expr: |
        increase(transcriber_jobs_dead_total[1h]) > 0
      for: "0m"
      severity: "warning"
      summary: !unsafe "Transcriber dead-letter jobs on {{ $labels.instance }}"
      description: !unsafe "One or more jobs moved to dead-letter queue in the last hour."
  dashboard_file: "grafana/dashboards/transcriber.json"
```

`ansible/roles/transcriber/files/grafana/dashboards/transcriber.json` (new):
- Grafana dashboard JSON with four panels:
  - Queue depth: `transcriber_queue_depth` (gauge)
  - Job throughput: `rate(transcriber_jobs_completed_total[5m])` (time series)
  - Processing duration: `transcriber_processing_duration_seconds` histogram (heatmap or percentile)
  - Dead letters: `transcriber_jobs_dead_total` (stat)
- Follow same structure as `ansible/roles/immich/files/grafana/dashboards/immich-photo-service.json`

---

### US-5: Reverse proxy and HTTPS (Priority: P5)

> As a user, I can reach the API at `transcriber.hus-sky.no` over HTTPS.

**Why P5**: Stable hostname with TLS needed before any external client integration.

**Acceptance criteria**:
- `https://transcriber.hus-sky.no/health` returns 200 from any Tailscale device
- TLS uses existing wildcard cert via Domeneshop DNS challenge (no new cert provisioning)
- `/health` and `/metrics` accessible without API key even when auth is configured
- Caddy template follows same 7-line pattern as `immich.caddy.j2`

**Files to create/modify**:

`ansible/roles/reverse_proxy/templates/transcriber.caddy.j2` (new — model on immich.caddy.j2):
```
transcriber.{{ caddy_base_domain }} {
    reverse_proxy {{ transcriber_ip }}:{{ transcriber_api_port }} {
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }
}
```

`ansible/roles/reverse_proxy/tasks/main.yml` — add new task (model on existing service tasks):
```yaml
- name: Deploy Transcriber Caddy configuration
  ansible.builtin.template:
    src: transcriber.caddy.j2
    dest: "{{ caddy_conf_dir }}/transcriber.caddy"
    mode: '0644'
  notify: Restart caddy
```

`ansible/host_vars/reverse_proxy.yml` — add transcriber vars (check existing file for pattern):
```yaml
transcriber_ip: "192.168.1.217"
transcriber_api_port: 8080
```

Monitoring host_vars — add blackbox HTTPS probe target:
- Find where `blackbox_https_targets` is defined (likely `ansible/host_vars/monitoring/vars.yml`)
- Add `https://transcriber.hus-sky.no/health`

AdGuard DNS rewrite: `transcriber.hus-sky.no → 192.168.1.211` (Caddy IP)
- Check existing AdGuard role/host_vars for DNS rewrite pattern

---

### US-6: Healthcheck integration (Priority: P6)

> As a developer, `task healthcheck:run -- --service transcriber` validates the
> service alongside other services.

**Why P6**: Integration with existing operational tooling.

**Key insight**: The healthcheck system reads `healthcheck_url`, `healthcheck_profile`,
and `healthcheck_expect_status` directly from host_vars (already added in US-2).
No changes to `healthcheck.py` needed.

**Acceptance criteria**:
- `task healthcheck:run -- --service transcriber` passes
- Checks: `/health` returns 200 on port 8080, NFS mount present
- Both LAN profile check works; Tailscale profile works after US-3

**Files to modify**:
- `ansible/host_vars/transcriber.yml` already contains healthcheck config from US-2
- Verify `transcriber` appears in the service scope allowlist used by the Taskfile
  (check `Taskfile.yml` healthcheck task for allowlist var or file reference)
- Update `healthcheck_profile: lan` → `healthcheck_profile: both` after US-3 is done

---

## Implementation Order

```
✓ US-0: Docker image published at ghcr.io/lightenup/transcriber:latest
  │
  ▼
US-1: Terraform LXC (main.tf + prod.tfvars + hosts.yml)
  │   (terraform apply; verify SSH access)
  ▼
US-2: Ansible role + Molecule (docker-compose, config, verify /health)
  │   (molecule test locally first, then ansible-playbook)
  ├──→ US-3: Tailscale join (add role to playbook, vault auth key)
  ├──→ US-4: Monitoring (host_vars monitoring_contract + Grafana JSON)
  │
  ▼
US-5: Reverse proxy (transcriber.caddy.j2 + reverse_proxy task + DNS)
  │
  ▼
US-6: Healthcheck (verify host_vars config, check scope allowlist)
```

## Out of Scope

- Transcriber application code — lives in `transcriber` repo ✓ done
- NFS export configuration on Synology — assumed pre-existing
- Tailscale ACL policy changes — inherits existing policy
- Mobile client — API compatible, no client built here
- CPU-mode inference on LXC — future work; needs `[inference]` image variant
- Automated Mac `transcriber serve` launchd setup — manual for now
- `transcriber serve` in Docker — Mac shim runs bare Python, not containerised
