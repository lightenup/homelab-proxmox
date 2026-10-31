---

description: "Task list for 097 long-term memory for Hermes, shared with the owner's other AI clients"
---

# Tasks: Long-term memory for Hermes, shared with the owner's other AI clients

**Input**: Design documents from `/specs/097-hermes-long-term-memory/`

**Prerequisites**: plan.md, spec.md (including Clarifications 2026-10-31), research.md (R-001 to
R-020), data-model.md, contracts/, quickstart.md

**Tests**: Included. Spec FR-011 requires the extension to be unit-tested, and the constitution
(Test-Driven Changes) requires guard tests for rendered config. Write each test task before its
implementation task and see it fail first.

**Organization**: Grouped by user story. US1 to US3 are P1, and US4 and US5 are P2. Phase 2
builds the memory service, which every story needs.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1…US5 from spec.md
- Tasks marked **(manual)** produce evidence, not code. Record the evidence in the file named in
  the task.

## Deviations from plan.md (decided while generating tasks)

- **Nightly backup in Phase 2**, not with US4. The store must not hold real memory before the
  backup exists. US4 keeps the restore drill.
- **Web UI in the US5 phase**: the UI is FR-023's browse-and-edit surface. The service runs
  without it, so the API, adapters and backup do not wait for it.
- **Plugin wheels via `get_url`**: wheels are fetched from `files.pythonhosted.org` with `get_url`
  and a `checksum:`, then unpacked with `unarchive`. This replaces `pip download`, so the hermes
  LXC needs no `pip` (research R-003 intent unchanged: pinned, hashed, deploy time).
- **Harness gate as a guard test**: a fingerprint test enforces FR-021 (T037). It replaces a
  path-gated CI reminder, so no workflow change is needed.
- **Operation snapshot file**: the allowlist guard (R-001, R-018) compares the policy with a
  checked-in list of the pinned Hindsight operation names (T009). CI then needs no Hindsight
  source.

## Implementation notes (2026-10-31, Phases 1 and 2 code)

- **Shim smoke test**: `shim.py` and `memory_access.py` were loaded in the stock
  `hindsight:1.1.0-slim` image with the rendered `server.env` and a pgvector container. Keys,
  scopes, the tag rewrite, the internal worker path and the 401/403 responses behave as the
  contract says over REST and MCP. Every `BankReadOperation` and `BankWriteOperation` value is
  classified. See research R-001, R-004 and R-015 for what this settled.
- **Export is not validator-gated** in 1.1.0 (research R-001). Any authenticated key can export
  the bank. Owner decision open; nothing else depends on it.
- **T003**: `memory_postgres_version` uses `policy: latest` against `pgvector/pgvector`, not
  `support-only`. The tag's numeric core is pgvector's 0.8.1, which matches no PostgreSQL cycle.
- **T008**: besides `decide` and `rewrite_retain_tags`, the module exposes `authorize` and
  `retain`, which apply the internal-call rule and the client lookup by `api_key_id`, so the
  shim stays translation only. Read scope adds `get_bank_profile` and `list_operations` (read
  on most bank routes and by the UI's operation list). Admin adds `update_bank`, which PUT on a
  bank fires alongside `create_bank`.
- **T012**: the validator reads the client file through its own
  `HINDSIGHT_API_OPERATION_VALIDATOR_CLIENTS_FILE`. Hindsight passes each extension only its
  own prefixed variables.
- **T015**: preflight also asserts `memory_db_password` is URL-safe (it sits in the database
  URL unescaped) and that keys have at least 43 characters after `hmem_` (32 bytes).
- **T016**: `clients.json` is owned by uid 1000 (the image's `hindsight` user) at 0400, not by
  root. The API container cannot read a root-only file.
- **T022**: `healthcheck_url` is the estate's `{scheme, port, path}` object with a literal
  port, because `ansible-inventory --list` does not render Jinja.
- **T023**: the gateway preflight gains a check that a client's `models` names declared aliases
  only.
- **T024**: also classified `memory_api_image`, `memory_api_port` and `memory_api_url`
  (`internal`), which the secret-name pattern matches.
- **T025**: the 1.1.0 export is asynchronous. The snapshot submits it, polls the operation and
  downloads the archive from `result_metadata.download_url`, then checks `manifest.json`.
- **T026**: the redaction corpus gains a `memory-key` line.
- **Export gap accepted** by the owner, 2026-10-31 (research R-001).
- **T028**: the per-mode secret freeze for `hindsight-config.json` lives in
  `test_hermes_env_modes.py`, the compose-render assertions in `test_hermes_memory_config.py`.
  `hermes_memory_api_url` and `hermes_memory_bank_id` are hermes role defaults (a guard test
  keeps the bank equal to the memory role's).
- **T030**: wheels pinned at `0.10.3` (the latest releases are `1.1.0`, outside plugin 1.2.3's
  `<1`). The spike resolved three packages, not four: `hindsight_client_api` ships inside the
  `hindsight-client` wheel.
- **T031**: a changed pin re-extracts into an emptied directory, so no older file survives;
  `unzip` is installed for the wheels. Downloads are cached in `/var/cache/hermes-memory-plugin`.
- **T032**: the hermes preflight asserts `memory_client_hermes_key` is set and well formed.
  `hermes_memory_api_url` is also classified `internal`.
- **T035**: `render-prod.sh` fetches with `curl` (Python's TLS fails behind the dev Mac's
  interception) and verifies checksums in Python. `llmproxy` gains `MODEL_MAP` (the gateway's
  alias mapping for `hermes-embed` and `hermes-rerank`) and logs a short hash of each caller's
  key for SC-003. A `.gitignore` now keeps `keys/`, `logs/`, `runs/*/secret.env` and the
  prod-render build out of the repo; none of them was ignored before.
- **T037**: `test_harness_gate_ran_against_this_configuration` fails until T036 commits a
  matching `results/*-prod-render/fingerprint.txt`. This is the FR-021 gate, so CI's Python
  tests stay red on this branch until then.
- **Not run locally**: `terraform init/validate`. The local binary is broken, and the provider
  download from a container fails TLS verification behind Zscaler. `terraform fmt -check` passes.
  CI runs `terraform-validate.sh`.

---

## Phase 1: Setup (preconditions, pins, addresses)

**Purpose**: Secrets, storage, pins and addresses that every later task reads.

- [X] T001 (manual) Create the Synology share `homelab_memory`, exported over NFS to `pve` like `homelab_hermes`. Run `ssh pve sudo pct list` and confirm that no container uses `192.168.1.223`. Record both under a new `## 0. Preconditions` heading at the top of `specs/097-hermes-long-term-memory/quickstart.md`.
- [ ] T002 (manual) Add vault entries with `ansible-vault edit ansible/group_vars/services/vault.yml`:
  - `memory_db_password`: random, no prefix.
  - `memory_client_hermes_key`, `memory_client_open_webui_key`, `memory_client_claude_code_key`, `memory_client_control_plane_key`, `memory_ui_access_key`, `memory_admin_key`: each `hmem_` followed by at least 32 random bytes, URL-safe base64 (data-model.md: "Every key starts with `hmem_`… Keys are at least 32 random bytes").
  - `llm_router_client_memory_key`: in the existing `sk-` format of the other gateway keys.
  - Copy `memory_client_claude_code_key` into the Mac keychain: `security add-generic-password -s homelab-memory -a claude-code -w`.
  - Copy `memory_ui_access_key` into the password manager.
  - Never paste a value into chat or logs.
- [X] T003 [P] Pin the new versions:
  - Add `hindsight_version: "1.1.0"`, `memory_postgres_version: "0.8.1-pg17"` and `hermes_hindsight_plugin_version: "1.2.3"` to the `# Service versions` block of `ansible/group_vars/services/vars.yml`. The block ends at the first blank line.
  - Add one entry each to `ansible/version-sources.yml`:
    - Hindsight: `policy: latest`, `github: vectorize-io/hindsight`.
    - Postgres: `policy: support-only`.
    - The plugin: `policy: unchecked` with `reason: "tags carry the integrations/hermes/ prefix; re-checked with hindsight_version (097 R-018)"`, unless the checker can filter tag prefixes.
  - `python/tests/guardrails/test_version_pins.py` must pass.
- [X] T004 [P] Add the addresses:
  - In `ansible/group_vars/services/vars.yml`: `memory_ip: "192.168.1.223"`, `memory_api_port: 8888`, `memory_ui_port: 9999`.
  - In `ansible/inventories/lab/lab-overrides.yml`: `memory_ip: "10.99.0.223"`.
  - Add `memory: {ansible_host: 192.168.1.223, ansible_user: root}` to `ansible/inventories/prod/hosts.yml`, and the `10.99.0.223` twin to `ansible/inventories/lab/hosts.yml`, under the `services` group as for `ntfy`.
  - Bump the service count from 12 to 13 in `python/tests/guardrails/test_lab_overrides.py`.

---

## Phase 2: Foundational (the memory service, its gateway key and its backup)

**Purpose**: A running, authenticated, backed-up store that every adapter can reach.

**⚠️ CRITICAL**: No user-story work starts until T027 passes (memory deployed to PROD, quickstart
§ 3 green).

### Tests for the foundation

- [X] T005 [P] Write `python/tests/memory_access/test_policy.py` against `homelab_proxmox_orchestrator.memory_access`, before the module exists. Cover:
  - **(a) Client list validation** (data-model.md § Client):
    - `id` matches `^[a-z][a-z0-9-]{1,31}$` and is unique;
    - hashes are unique;
    - "Exactly one `admin` client";
    - an entry holding a plaintext key (anything starting `hmem_`) is rejected.
  - **(b) Authentication**: a sha256 match with `hmac.compare_digest` returns the client. Unknown, empty and revoked keys return `None`.
  - **(c) Scope matrix**: every row of data-model.md § Scope matrix for `readonly`, `readwrite`, `curator` and `admin`, including the last row, "webhooks, reflect, consolidation, mental-model create or refresh, directives, reprocess, entity regeneration, clone, knowledge-base writes": refused for every scope, admin included.
  - **(d) Unlisted operations**: an operation name in no allowlist is refused with reason `scope <scope> may not <operation>`. A refused-for-all operation gets reason `<operation> is disabled` (contracts/memory-access.md § Responses to refusals).
  - **(e) Tag rewrite** (research R-002):
    - a forged `client:other` tag is replaced by `client:<id>`;
    - a missing tag is added;
    - several items are each rewritten;
    - `session:*` tags are kept;
    - `admin` keeps a supplied `client:*` tag.
  - **(f) Internal calls**: a call with `internal=True` and `api_key_id` set is accepted without a rewrite.
- [X] T006 [P] Write `python/tests/guardrails/test_memory_config.py`. Render `ansible/roles/memory/templates/{server.env.j2,clients.json.j2,docker-compose.yml.j2}` with `jinja2`, using `ansible/group_vars/services/vars.yml`, role defaults and placeholder secrets that start `hmem_test`. Reuse the repo-root finder pattern of `python/tests/guardrails/test_log_pipeline.py`. Assert:
  - every value in research R-004's table, exactly;
  - `HINDSIGHT_API_LLM_PROVIDER=none`;
  - no rendered value contains `openai.com`, `openrouter`, `huggingface` or `anthropic`;
  - `HINDSIGHT_API_MCP_ENABLED_TOOLS` equals exactly `recall,retain,list_memories,update_memory,invalidate_memory,list_tags`;
  - `clients.json` holds sha256 hex digests and no string starting `hmem_`;
  - the API port binds `memory_ip` only;
  - `HINDSIGHT_VERIFIED_VERSION` in `ansible/roles/memory/files/hindsight_ext/shim.py` equals `hindsight_version`.
- [X] T007 [P] Extend `python/tests/guardrails/test_memory_config.py` with the allowlist guard. Every operation name used in `memory_access.py` must exist in `ansible/roles/memory/files/hindsight_ext/operations-1.1.0.txt`, and every name in that file must be allowed by some scope or listed as refused-for-all. Select the snapshot file by `hindsight_version`, so a bump without a new snapshot fails.

### Implementation of the foundation

- [X] T008 Implement `python/src/homelab_proxmox_orchestrator/memory_access.py` until T005 passes.
  - **Contents**: pure functions over plain data:
    - `load_clients(text) -> list[Client]`;
    - `authenticate(bearer, clients) -> Client | None`;
    - `decide(client, operation) -> Decision(allowed, reason)`;
    - `rewrite_retain_tags(client, items) -> items`;
    - the constants `SCOPE_ALLOWLISTS` and `REFUSED_FOR_ALL`, matching data-model.md § Scope matrix.
  - **Standalone**: standard library only, and no import of any other package module, because the file is mounted on its own into the Hindsight container.
  - Add `--cov=homelab_proxmox_orchestrator.memory_access` to `python/pytest.ini`.
- [X] T009 [P] Create `ansible/roles/memory/files/hindsight_ext/operations-1.1.0.txt`: one operation name per line.
  - **Source**: the enums in upstream `hindsight-api-slim/hindsight_api/extensions/operation_validator.py` at tag `v1.1.0`, lines 378–459 (bank read and bank write), plus the hook names `retain`, `recall`, `reflect`, `consolidate`, `memory_update`, `mental_model_get`, `mental_model_refresh`, `import`, `create_bank`.
  - **Header**: the upstream commit `a5a619b`.
- [X] T010 Implement `ansible/roles/memory/files/hindsight_ext/shim.py` (depends on T008).
  - **Constant**: `HINDSIGHT_VERIFIED_VERSION = "1.1.0"`.
  - **`ClientKeyTenantExtension(TenantExtension)`**:
    - Reads the client file named by its `config["clients_file"]` once in `__init__`.
    - `authenticate()` calls `memory_access.authenticate`. It raises `AuthenticationError` on `None`, sets `context.api_key_id = client.id` and returns the default schema.
    - `list_tenants()` returns that one tenant.
  - **`ClientScopeValidator(OperationValidatorExtension)`**:
    - It implements `validate_retain`, `validate_recall`, `validate_reflect`, `validate_consolidate`, `validate_memory_update`, `validate_bank_read`, `validate_bank_write`, `validate_import`, `validate_create_bank`, `validate_mental_model_get` and `validate_mental_model_refresh`.
    - Each one maps the context to an operation name, calls `memory_access.decide`, and returns `ValidationResult.reject(reason, status_code=403)` or an accept.
    - `validate_retain` accepts internal calls (`context.internal`) unchanged. Otherwise it returns `ValidationResult.accept_with(contents=memory_access.rewrite_retain_tags(...))`.
    - Key on `api_key_id`, never on `api_key`: the async worker drops the key (R-001).
  - **Size**: no logic beyond translation, about 60 lines.
- [X] T011 Create `ansible/roles/memory/defaults/main.yml`:
  - **Paths**: `memory_install_dir: /opt/memory`, `memory_data_dir: /opt/memory-data`, `memory_ext_dir: /opt/memory-ext`.
  - **Images**: `memory_api_image: "ghcr.io/vectorize-io/hindsight:{{ hindsight_version }}-slim"`, `memory_postgres_image: "pgvector/pgvector:{{ memory_postgres_version }}"`, `memory_ui_image: "ghcr.io/vectorize-io/hindsight-control-plane:{{ hindsight_version }}"`.
  - **Bank and tools**: `memory_bank_id: owner`, `memory_probe_bank_id: deploy-probe`, and `memory_mcp_enabled_tools` (the six tools from T006).
  - **Clients**: `memory_claude_code_scope: readwrite` (allowed values `readwrite|readonly|revoked`), and `memory_clients`: a list of `{id, vault_var, scope}` for `hermes`, `open-webui`, `claude-code` (scope `{{ memory_claude_code_scope }}`), `control-plane` (`curator`) and `backup` (`admin`).
- [X] T012 Create `ansible/roles/memory/templates/server.env.j2`. It renders research R-004's table exactly, plus:
  - `HINDSIGHT_API_DATABASE_URL=postgresql://hindsight:{{ memory_db_password }}@memory_postgres:5432/hindsight`;
  - `HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY` and `HINDSIGHT_API_RERANKER_LITELLM_API_KEY`, both `{{ llm_router_client_memory_key }}`;
  - `HINDSIGHT_API_TENANT_EXTENSION=shim:ClientKeyTenantExtension` and `HINDSIGHT_API_TENANT_CLIENTS_FILE=/run/memory/clients.json`;
  - `HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=shim:ClientScopeValidator`;
  - `PYTHONPATH={{ memory_ext_dir }}`.
  - Classify `memory_db_password` and `llm_router_client_memory_key` as `internal` in `python/tests/guardrails/test_lab_switches.py` in the same change (I1: the test fails on a classification no template references yet).
  - Also create `ansible/roles/memory/templates/db.env.j2` with exactly `POSTGRES_USER=hindsight`, `POSTGRES_DB=hindsight` and `POSTGRES_PASSWORD={{ memory_db_password }}`.
- [X] T013 [P] Create `ansible/roles/memory/templates/clients.json.j2`.
  - Render a JSON list of `{"id", "sha256", "scope"}` from `memory_clients`, with `sha256` = `lookup('vars', item.vault_var) | hash('sha256')`.
  - Omit `claude-code` when `memory_claude_code_scope == 'revoked'`.
  - Never render a plaintext key.
- [X] T014 Create `ansible/roles/memory/templates/docker-compose.yml.j2` with two services for now:
  - **`memory_postgres`**: image `memory_postgres_image`, `env_file: db.env`, bind volume `{{ memory_data_dir }}/postgres`, healthcheck `pg_isready -U hindsight -d hindsight`. No published port.
  - **`memory_api`**:
    - image `memory_api_image`, `env_file: server.env`;
    - volumes `{{ memory_ext_dir }}:{{ memory_ext_dir }}:ro` and `{{ memory_install_dir }}/clients.json:/run/memory/clients.json:ro`;
    - ports `"{{ memory_ip }}:{{ memory_api_port }}:8888"`;
    - healthcheck on `/health`, `depends_on` the healthy `memory_postgres`.
  - **Logging**: follow the estate's compose logging options as in `ansible/roles/ntfy/templates/docker-compose.yml.j2`.
- [X] T015 Create `ansible/roles/memory/tasks/preflight.yml`.
  - **Assert**:
    - every `memory_clients[*].vault_var`, plus `memory_db_password` and `llm_router_client_memory_key`, is defined and non-empty;
    - every `memory_client_*_key`, `memory_admin_key` and `memory_ui_access_key` starts with `hmem_`;
    - exactly one client has scope `admin`;
    - `memory_claude_code_scope` is in `[readwrite, readonly, revoked]`.
  - Use `no_log: true` on every assert that touches a secret.
- [X] T016 Create `ansible/roles/memory/tasks/main.yml` and `ansible/roles/memory/handlers/main.yml`.
  - **main.yml**:
    1. Include `preflight.yml`.
    2. Create the dirs: `memory_ext_dir` root 0755, `memory_data_dir` 0700.
    3. Copy `python/src/homelab_proxmox_orchestrator/memory_access.py` and `files/hindsight_ext/shim.py` into `memory_ext_dir` (root, 0644).
    4. Template `server.env` and `db.env` (both 0600, `no_log`), `clients.json` (0400) and `docker-compose.yml`, each with `notify: Restart memory`.
    5. Write `{{ memory_install_dir }}/backup.key` from `memory_admin_key` (root, 0400, `no_log`).
    6. Run `community.docker.docker_compose_v2` with `project_src`, `state: present`, `remove_orphans: true`, `pull: always`.
    7. Wait on `http://{{ memory_ip }}:{{ memory_api_port }}/health` (18 retries, 10 s apart).
    8. Include `bank.yml`.
  - **handlers/main.yml**: the `Restart memory` handler restarts the compose project.
- [X] T017 Create `ansible/roles/memory/tasks/bank.yml` (research R-019).
  - **Banks**: with the admin key from `backup.key`, ensure banks `owner` and `deploy-probe` exist.
  - **Deploy probe** (PROD only, `when: deploy_environment | default('prod') != 'lab'`):
    1. Sync-retain a random sentence into `deploy-probe`.
    2. Recall it and assert that it is returned.
    3. Assert that `stats.total_documents` grew by 1.
    4. Delete the document.
  - **Lab**: append `memory: deploy probe (needs embeddings)` to `reports/lab/skipped-checks.txt`, the same way `ansible/roles/hermes/tasks/main.yml` does for its skipped egress probes.
- [X] T018 [P] Create `ansible/playbooks/memory.yml`: play 1 runs role `lxc_base`. Play 2 runs `geerlingguy.docker`, then `memory`, then `{role: service_backup, service_backup_name: memory, when: (deploy_environment | default('prod')) != 'lab'}`, copying `ansible/playbooks/hermes.yml`.
- [X] T019 [P] Create the Terraform root and inventory entries.
  - **Root**: `terraform/services/memory/{main,outputs,providers,variables}.tf`, copied from `terraform/services/ntfy/`, with `module "memory_lxc"`, `name = "memory-lxc"`, `hostname = "${var.hostname_prefix}memory"`, `cores = 2`, `memory = 2048`, `disk_gb = 16`, `ip = var.service_ips["memory"]` and output `ansible_inventory = { services = { "memory" = module.memory_lxc.ipv4 } }`.
  - **Template**: in `terraform/environments/prod.tfvars.template`, add `memory = "192.168.1.223/24"` to `service_ips`, and `memory = { backups = { mp = "/mnt/memory/backups", volume = "/mnt/nas/homelab_memory" } }` to `service_mountpoints`.
  - **Counts**: in `python/tests/guardrails/test_lab_tfvars.py`, bump IPs from 12 to 13 and volumes from 8 to 9.
- [X] T020 [P] Register the service. These are protected paths: the PR needs the label `allow-protected-path-changes`.
  - Add `"memory": ["module.memory_lxc"]` to `scripts/lab/service-scope-allowlist.json`.
  - Add `memory` to `SERVICES=(...)` in `scripts/lab/validate-existing-state.sh`.
  - Add `- memory` to the service dropdown in `.github/workflows/lxc-promote-prod.yml`.
  - Validate with `act -l` and `act -n -W .github/workflows/lxc-promote-prod.yml workflow_dispatch` (`DOCKER_HOST=unix://$HOME/.docker/run/docker.sock`).
- [X] T021 [P] Add the NFS mount `/mnt/nas/homelab_memory` from `192.168.1.109:/volume1/homelab_memory` to `ansible/roles/proxmox_mounts/tasks/main.yml`, next to the `homelab_hermes` entry.
- [X] T022 [P] Add the API vhost and health check.
  - **Caddy**: add `{host: memory-api, ip: "{{ memory_ip }}", port: "{{ memory_api_port }}", title: "Memory API", desc: "Shared AI memory API", enabled: true, user_facing: false}` to `caddy_services` in `ansible/group_vars/services/vars.yml`.
  - **Health check**: create `scripts/healthcheck/memory.sh` from `scripts/healthcheck/ntfy.sh` (`--host memory`). In the new `ansible/host_vars/memory.yml`, set `healthcheck_url: "http://{{ memory_ip }}:{{ memory_api_port }}/health"` and `healthcheck_profile: lan`. It checks directly, because there is no Caddy in a single-copy lab (R-016).
- [X] T023 Add the gateway client (research R-011).
  - **Override**: in `ansible/roles/llm_router/tasks/virtual_keys.yml`, let a client's optional `models` list override `llm_router_client_allowed_models`, in both the generate call and the reconcile loop.
  - **Entry**: add `{alias: memory, key_env: LLM_ROUTER_CLIENT_MEMORY_KEY, max_budget: 1.00, budget_duration: "30d", rpm_limit: 30, models: [hermes-embed, hermes-rerank]}` to `llm_router_clients` in `ansible/group_vars/services/vars.yml`, with a comment citing 097 FR-004.
  - **Preflight**: the band in `ansible/roles/llm_router/tasks/preflight.yml` must still hold (max 60 ≤ 65 < sum 122; budget sum $28 < $50).
- [X] T024 [P] Check the lab-switch classification after T012 to T025: `python/tests/guardrails/test_lab_switches.py` must pass with exactly the foundation's two new entries (`memory_db_password`, `llm_router_client_memory_key`, added in T012).
  - `test_no_stale_classifications` fails on a name that no role template references literally inside `{{ }}`. Each later name is therefore classified `internal` in the task that first templates it: `memory_client_hermes_key` in T032, and `memory_ui_access_key` and `memory_client_control_plane_key` in T066.
  - `memory_admin_key` and `memory_client_open_webui_key` are used only in tasks and through `lookup('vars', …)`, never literally in a template, so they are not classified. Record this as a comment next to `CLASSIFICATION`.
- [X] T025 Add the nightly backup (research R-013).
  - **Registration**: in `ansible/group_vars/all/vars.yml`, add `service_backups.memory: {host: memory, mount: /mnt/memory/backups, dir: /mnt/memory/backups, schedule: "*-*-* 05:30:00"}`.
  - **Snapshot**: create `ansible/roles/service_backup/templates/snapshot/memory.sh.j2` with a `snapshot()` that:
    - runs `docker exec memory_postgres pg_dump -Fc -U hindsight hindsight > "$WORK_DIR/db.dump"`, then `pg_restore --list` on it;
    - exports the bank: `curl -fsS -H "Authorization: Bearer $(cat /opt/memory/backup.key)" -X POST http://{{ memory_ip }}:{{ memory_api_port }}/v1/default/banks/owner/document-transfer/export -o "$WORK_DIR/owner-export.zip"`. The API is bound to `memory_ip` only (T014), not to `127.0.0.1`;
    - writes `stats.json` from `GET http://{{ memory_ip }}:{{ memory_api_port }}/v1/default/banks/owner/stats`;
    - copies `docker-compose.yml` and `clients.json`, never `server.env`, `db.env`, `ui.env` or `backup.key`.
  - `python/tests/guardrails/test_service_backup.py` must pass.
- [X] T026 [P] Add a redaction pattern `memory-key` matching `hmem_[A-Za-z0-9_-]{20,}` to `ansible/roles/alloy/defaults/main.yml`, next to `ntfy-token`.
- [ ] T027 (manual) Deploy the foundation. Record the outcomes in `specs/097-hermes-long-term-memory/quickstart.md` under § 2 and § 3.
  1. Run `bash scripts/ci/python-tests.sh` and `pre-commit run --all-files`; both must be green.
  2. Run `lxc-lifecycle.yml` with `action=add`, `environment=prod`, `service=memory`, `confirm_apply_prod=deploy-prod`.
  3. Deploy `llm-router` through `Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`.
  4. Deploy `memory` the same way. The LAB stage must pass quickstart § 2 "memory": liveness without embeddings, deploy probe listed as skipped.
  5. Run `curl -s http://10.99.0.223:8888/metrics | grep -E '^hindsight_' | cut -d'{' -f1 | sort -u` from `pve` during the rehearsal, and paste the metric names into research R-015.
  6. In PROD, quickstart § 3 steps 1–5 must pass.
  7. Check that `/health` and `/metrics` answer without a key. If not, make the shim admit exactly those two paths (contracts/memory-access.md UNVERIFIED note) and redeploy.

**Checkpoint**: Store live in PROD, authenticated, backed up nightly. Adapters can start.

---

## Phase 3: User Story 1 — Hermes remembers more about me than its built-in memory holds (P1) 🎯 MVP

**Goal**: Hermes injects recall from the shared store on every turn, including the first, and
retains every turn (FR-001, FR-002, FR-005, FR-008).

**Independent Test**: quickstart § 4. A fact told in one conversation is answered on the first
turn of a new one, across Norwegian and English, and an unknown topic gets "don't know".

### Tests for User Story 1

- [X] T028 [P] [US1] Write `python/tests/guardrails/test_hermes_memory_config.py`. Render `ansible/roles/hermes/templates/{agent-config.yaml.j2,hindsight-config.json.j2,docker-compose.yml.j2,agent.env.j2}` with PROD vars and placeholder secrets, and assert:
  - `memory.memory_enabled: true` and `memory.provider: hindsight`;
  - `hindsight-config.json` equals research R-003's table exactly: `mode: local_external`, `api_url: https://memory-api.hus-sky.no`, `bank_id: owner`, `memory_mode: context`, `auto_recall: true`, `auto_retain: true`, `recall_sync: true`, `recall_types: ["world"]`, `recall_budget: mid`, `retain_every_n_turns: 1`, `retain_async: true`, `retain_tags: ["client:hermes"]`, `retain_user_prefix: User`, `retain_assistant_prefix: Assistant`, timeout 10;
  - the plugin and deps mounts end in `:ro`, and `PYTHONPATH=/opt/hermes-memory-deps` is set on the agent service;
  - no `hmem_` value appears in `agent.env`, because the plugin key lives only in the config file;
  - `api_url` uses `https://memory-api.` and never the direct port `:8888` (G1: clients go through Caddy over TLS; the direct port serves only the reverse proxy, monitoring and health checks, spec FR-010).
  - Also extend `python/tests/guardrails/test_hermes_env_modes.py` (G3): freeze the set of secrets rendered into `hindsight-config.json` per mode, the same way `agent.env` is frozen. PROD, LAB rig and pipeline LAB each hold exactly `memory_client_hermes_key`. Add a comment citing 097 R-003 and `095` R-016 (credential-policy decision).
  - Keep `test_only_the_ntfy_shim_is_enabled_as_a_plugin` in `python/tests/guardrails/test_hermes_ntfy_config.py` unchanged. The memory provider is set under `memory:`, not under `plugins.enabled`.
- [X] T029 [P] [US1] Write `python/tests/guardrails/test_hermes_memory_plugin_pins.py`. Assert that `ansible/roles/hermes/defaults/main.yml` pins the plugin tarball URL with tag `integrations/hermes/v{{ hermes_hindsight_plugin_version }}` and a `sha256:` checksum. Assert that each wheel entry has an exact `==` version, a `files.pythonhosted.org` URL and a `sha256:` checksum.

### Implementation for User Story 1

- [X] T030 [US1] Add the plugin pins to `ansible/roles/hermes/defaults/main.yml`.
  - **Tarball**: `hermes_hindsight_plugin_url` (GitHub archive of `vectorize-io/hindsight` at tag `integrations/hermes/v1.2.3`) and `hermes_hindsight_plugin_sha256`.
  - **Wheels**: `hermes_hindsight_plugin_wheels`, a list of `{name, version, url, sha256}` for `hindsight-client`, `hindsight-embed` and `aiohttp-retry==2.9.1`.
    - Take versions inside plugin 1.2.3's `>=0.10.1,<1` constraint. Prefer `0.10.3`, which passed the spike.
    - Take URLs and hashes from `https://pypi.org/pypi/<name>/<version>/json`, `py3-none-any` wheels only.
  - **Dirs**: `hermes_memory_plugin_dir: "{{ hermes_agent_plugins_dir }}/memory/hindsight"` and `hermes_memory_deps_dir: "{{ hermes_agent_plugins_dir }}/memory-deps"`.
- [X] T031 [US1] Create `ansible/roles/hermes/tasks/memory_plugin.yml` and include it from `ansible/roles/hermes/tasks/main.yml` before the compose task.
  1. `get_url` the tarball with `checksum: "sha256:{{ hermes_hindsight_plugin_sha256 }}"`.
  2. `unarchive` only `hindsight-integrations/hermes/` into `hermes_memory_plugin_dir`, root-owned.
  3. Read `plugin.yaml` and fail unless its `version` equals `hermes_hindsight_plugin_version`, and its `requires_hermes` (if present) admits `hermes_agent_version`. If `1.2.3` does not admit `v0.21.6`, stop and fall back to `1.2.2` (research R-003).
  4. `get_url` each wheel with its checksum, and `unarchive` it into `hermes_memory_deps_dir`, root-owned.
  5. Notify the agent restart handler on any change.
- [X] T032 [US1] Create `ansible/roles/hermes/templates/hindsight-config.json.j2` with exactly the values T028 asserts. `api_key` is `{{ memory_client_hermes_key }}`. Render it to `{{ hermes_install_dir }}/hindsight-config.json` (root, 0644, `no_log`) in `ansible/roles/hermes/tasks/main.yml`. In the same change, classify `memory_client_hermes_key` as `internal` in `python/tests/guardrails/test_lab_switches.py` (I1).
- [X] T033 [US1] In `ansible/roles/hermes/templates/agent-config.yaml.j2`, add `provider: hindsight` under `memory:` (lines 76–79). Add a comment citing 097 FR-001 and stating that `_config_version` and the plugin pin are re-checked together on a `hermes_agent_version` bump.
- [X] T034 [US1] In `ansible/roles/hermes/templates/docker-compose.yml.j2`, on the agent service:
  - add the read-only mounts `{{ hermes_memory_plugin_dir }}:/opt/data/plugins/hindsight:ro`, `{{ hermes_memory_deps_dir }}:/opt/hermes-memory-deps:ro` and `{{ hermes_install_dir }}/hindsight-config.json:/opt/data/hindsight/config.json:ro`;
  - add the environment variable `PYTHONPATH=/opt/hermes-memory-deps`.
  - The existing `:ro` assertion in `ansible/roles/hermes/tasks/main.yml` (around line 306) must cover the new plugin mount.
- [X] T035 [US1] Build the harness `prod-render` candidate in `docs/backlog/097-spike/`.
  - **`render-prod.sh`**: renders `ansible/roles/memory/templates/{server.env.j2,clients.json.j2}` and `ansible/roles/hermes/templates/hindsight-config.json.j2` with `ansible localhost -m template`, using PROD vars and harness-local keys (generated into `runs/prod-render/secret.env`, gitignored). It rewrites only the gateway URL to `http://llmproxy:4000` and `api_url` to `http://hindsight:8888`.
  - **`compose.prod-render.yml`**: uses `memory_api_image`, `memory_postgres_image`, and the shim and `memory_access.py` mounted read-only. Hermes uses the stock image plus the plugin and wheel dirs that `memory_plugin.yml` produces, unpacked locally by `render-prod.sh` from the same pins.
  - **README**: add `prod-render` to `docs/backlog/097-spike/README.md`.
- [ ] T036 [US1] (manual) Run the harness gate (quickstart § 1): `./render-prod.sh && ./run.sh prod-render`. SC-001, SC-002, SC-003 and SC-004 must pass. Commit the results to `docs/backlog/097-spike/results/<YYYY-MM-DD>-prod-render/`, including `fingerprint.txt` (T037). If it fails, stop: FR-021 forbids the PROD promotion.
- [X] T037 [US1] Write `python/tests/guardrails/test_memory_harness_gate.py`.
  - **Fingerprint**: sha256 over the pins `hindsight_version`, `memory_postgres_version`, `hermes_hindsight_plugin_version` and `hermes_agent_version` (G2: the plugin's behaviour depends on the agent, so an agent bump re-runs the gate), the wheel pins, and the contents of:
    - `ansible/roles/memory/templates/server.env.j2`;
    - `ansible/roles/hermes/templates/hindsight-config.json.j2`;
    - `python/src/homelab_proxmox_orchestrator/memory_access.py`;
    - `ansible/roles/memory/files/hindsight_ext/shim.py`;
    - `ansible/roles/hermes/files/open_webui/memory_filter.py`, once it exists.
  - **Not fingerprinted**: the Claude Code hook. It lives in dotfiles, and the harness replays its turn format without running the script, so hashing it would force re-runs that test nothing (I2). It is covered by the contract and quickstart § 6.
  - **Assertion**: some `docs/backlog/097-spike/results/*-prod-render/fingerprint.txt` equals the computed value (FR-021).
  - **Helper**: `render-prod.sh` writes `fingerprint.txt` using the same function, importable from the test module.
- [ ] T038 [US1] (manual) Deploy `hermes` through `Prod 1` → `Prod 2`.
  - **LAB stage**: the agent's `/health` stays healthy with memory unreachable, and one API-server turn returns the gateway's 429 without a crash (quickstart § 2 "hermes", research R-016).
  - **PROD**: run quickstart § 4 steps 1–5. Record the results in `specs/097-hermes-long-term-memory/quickstart.md`.

**Checkpoint**: US1 delivered. Hermes alone uses the shared store.

---

## Phase 4: User Story 2 — What I tell one client, the others know (P1)

**Goal**: Open WebUI and Claude Code inject recall and retain turns in the same format. Open
WebUI's own memories are imported and retired (FR-012, FR-016, FR-019).

**Independent Test**: quickstart § 6 steps 1–4 and § 7.

### Tests for User Story 2

- [ ] T039 [P] [US2] Write `python/tests/open_webui_memory_filter/test_filter.py`. Load `ansible/roles/hermes/files/open_webui/memory_filter.py` by path and stub HTTP. Cover:
  - **Inlet**:
    - one system message with contracts/turn-format.md § Recall's preamble, verbatim;
    - no block on empty results;
    - fail open within 3 s on timeout or error, with one log line;
    - skips `__metadata__["task"]` requests;
    - skips requests whose `body["model"]` is in the `agent_model_ids` valve (a list), because the agent's plugin retains those turns itself.
  - **Outlet**: builds exactly the retain JSON of contracts/turn-format.md § Retain:
    - `User:` and `Assistant:` prefixes;
    - `document_id = owui-<chat_id>`, `update_mode: append`, tag `session:owui-<chat_id>`, `async: true`;
    - drops tool-call and tool-result messages and any injected memory block;
    - strips strings matching `hmem_[A-Za-z0-9_-]{20,}`.
- [ ] T040 [P] [US2] Extend `python/tests/guardrails/test_hermes_memory_config.py`:
  - the Open WebUI service renders `ENABLE_MEMORIES=false` and `USER_PERMISSIONS_FEATURES_MEMORIES=false`;
  - `hermes_managed_config` contains `memories.enable: false`;
  - the filter-reconcile task's payload carries `memory_client_open_webui_key` and never `memory_client_hermes_key`;
  - the valve `url` starts with `https://memory-api.` and never contains `:8888` (G1, spec FR-010).

### Implementation for User Story 2

- [ ] T041 [US2] Implement `ansible/roles/hermes/files/open_webui/memory_filter.py` (about 120 lines) until T039 passes. Ship T041 to T046 in one PR: the filter changes the harness fingerprint (T037), so CI stays red until T046 commits the new results folder.
  - **Structure**: `class Filter` with `Valves(url, key, bank="owner", agent_model_ids: list[str] = [], timeout_s=3)`.
  - **inlet**: `inlet(body, __user__, __metadata__)` recalls with types `["world"]` and budget `mid`, caps the block at about 8,000 characters, and inserts the system message.
  - **outlet**: async retain per contracts/turn-format.md.
  - **Dependencies**: standard library plus `requests`, which ships in Open WebUI's environment.
- [ ] T042 [US2] Add the filter reconcile task to `ansible/roles/hermes/tasks/main.yml`, after the existing tool-server reconcile.
  - **Mechanism**: `docker exec -i hermes_open_webui python3 -c ...`, with a JSON payload on stdin (`no_log`).
  - **Upsert**: the `function` row `id=shared_memory`, `type=filter`, `is_active=1`, `is_global=1`, the content of the filter file, and valves `{url: "https://memory-api.{{ caddy_base_domain }}", key: memory_client_open_webui_key, bank: owner, agent_model_ids: <ids>}`.
  - **Agent model ids**: inside the Open WebUI container (it shares the compose network), the same reconcile script calls `GET {{ hermes_agent_api_base_url }}/models` with `Authorization: Bearer {{ hermes_agent_api_server_key }}`, and writes every returned `data[*].id` into `agent_model_ids`. It fails the task if the list is empty, which catches a renamed or missing agent connection.
  - **Restart**: restart `hermes_open_webui` only when the stored content hash changed.
  - Follow the pattern of the tool-server reconcile at `ansible/roles/hermes/tasks/main.yml:636-708`.
- [ ] T043 [US2] Add the one-shot import task to `ansible/roles/hermes/tasks/main.yml` (research R-008). It runs before memories are switched off, and only while `memories.enable` is still true in `webui.db`.
  1. Read the `memory` table through `docker exec`.
  2. For each row, retain with the admin key (`memory_admin_key`, `no_log`): `document_id = owui-memory-<id>`, tags `origin:open-webui-memory` and `client:open-webui`, synchronously.
  3. Assert that the count of `owui-memory-*` documents equals the row count.
  - Skip when the counts already match. PROD only: lab has no memory service.
- [ ] T044 [US2] Switch Open WebUI's memories off.
  - In `ansible/roles/hermes/templates/docker-compose.yml.j2` (open-webui service), set `ENABLE_MEMORIES=false` and `USER_PERMISSIONS_FEATURES_MEMORIES=false`.
  - Add `memories.enable: false` to `hermes_managed_config` in `ansible/group_vars/services/vars.yml`.
  - Order: after T043 in the same deploy.
- [ ] T045 [US2] Extend `docs/backlog/097-spike/llmproxy/portability.py` with `--clients hermes,open-webui,claude-code`. Each client gets its own key from `runs/prod-render/secret.env` and replays a turn in the contracts/turn-format.md format. Then assert:
  - 6/6 cross-client recalls (SC-005);
  - a `client:<id>` tag stamped per writer, with a forged tag replaced;
  - a read-only `claude-code` retain refused with 403;
  - a webhook creation and a bank-config change refused with 403 for every key.
- [ ] T046 [US2] (manual) Re-run the harness gate with the filter and portability legs (quickstart § 1), and commit the new results folder and fingerprint.
- [ ] T047 [US2] (manual) Deploy `hermes` (Open WebUI) through `Prod 1` → `Prod 2`.
  - **LAB stage**: the filter loads and fails open.
  - **PROD**: run quickstart § 7. Record the row count before the deploy, and the document count and the missing memory setting after it.
- [ ] T048 [US2] (manual) Confirm the accepted risk "memory reaches Anthropic through Claude Code" against the Claude Enterprise Guidance & Guidelines. Record the outcome and date in the Assumptions of `specs/097-hermes-long-term-memory/spec.md`. If it is not confirmed, stop US2's Claude Code tasks (T049 to T051) and set `memory_claude_code_scope: revoked` in `ansible/roles/memory/defaults/main.yml`.
- [ ] T049 [US2] In the owner's dotfiles repo (`~/Development/private/dotfiles`), add the executable `claude-memory-hook` (Bash, `curl` and `jq` only), with two modes (research R-010):
  - **`recall`**:
    - Reads the hook JSON from stdin and recalls with `prompt` as the query (`--max-time 3`).
    - Prints `{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":...}}` with the contracts/turn-format.md preamble, capped at 8,000 characters.
    - On any error it prints nothing and exits 0.
  - **`retain`**:
    - Pairs the last user prompt from `transcript_path` with `last_assistant_message`.
    - Strips `hmem_…` strings and retains with `document_id = cc-<session_id>`, `update_mode: append`, `async: true`.
  - **Key**: from `security find-generic-password -s homelab-memory -a claude-code -w`. **URL**: `https://memory-api.hus-sky.no`.
- [ ] T050 [US2] (manual) Enable the hooks in exactly one private repository. Add `UserPromptSubmit` → `claude-memory-hook recall` (timeout 5) and `Stop` → `claude-memory-hook retain` (`async: true`) to that repo's `.claude/settings.local.json`. Never use committed project settings or `~/.claude/settings.json`. Document the snippet in the dotfiles README.
- [ ] T051 [US2] (manual) Run quickstart § 6 steps 1–4 (cross-client recall, tags, no hook in a work repository). Record the results in `specs/097-hermes-long-term-memory/quickstart.md`.

**Checkpoint**: US2 delivered. All three clients share one memory.

---

## Phase 5: User Story 3 — Memory costs little inference and never blocks chat (P1)

**Goal**: Zero memory-side chat calls, enforced at the gateway. Failed and stalled writes alert.
Every client keeps working when memory is down (FR-004, FR-006, FR-015).

**Independent Test**: quickstart § 5. The gateway shows the memory key using only embed and
rerank, a chat call with the memory key is refused, and stopping memory leaves chat working with a
log line within 5 minutes (SC-010).

### Tests for User Story 3

- [ ] T052 [P] [US3] Extend `python/tests/guardrails/test_log_pipeline.py`. Add `memory` to `EXPECTED_LOG_RULE_SERVICES` (line about 300) and assert the shape of the new log rules in `ansible/host_vars/memory.yml` and `ansible/host_vars/hermes.yml` (T054).
- [ ] T053 [P] [US3] Write `python/tests/guardrails/test_memory_monitoring.py`. Assert that `ansible/host_vars/memory.yml` `monitoring_contract` declares:
  - the scrape target `{{ memory_ip }}:{{ memory_api_port }}/metrics`;
  - the liveness target `https://memory-api.{{ caddy_base_domain }}/health` with `http_2xx`;
  - the alerts `MemoryDown` (for 5m, critical), `MemoryRetainFailures` (for 30m) and `MemoryWritesStalled`.

### Implementation for User Story 3

- [ ] T054 [US3] Complete `ansible/host_vars/memory.yml` `monitoring_contract` (research R-015).
  - **Scrape and liveness**: as asserted in T053.
  - **Alerts**: use the metric names recorded in T027.
    - `MemoryDown`: `probe_success{job="memory-health"} == 0` for 5m.
    - `MemoryRetainFailures`: the backlog gauge with `status="failed"` > 0 for 30m.
    - `MemoryWritesStalled`: retain operations at 0 over 12h while `sum(increase(litellm_deployment_success_responses_total[12h]))` exceeds 20.
  - **Log rule**: the memory container's `ERROR` lines, with `enabled: false` and `disabled_reason: "awaiting 7-day baseline (097)"`.
  - In `ansible/host_vars/hermes.yml`, add a log rule for agent lines matching `Hindsight (retain|recall) failed`, with the same disabled reason.
- [ ] T055 [US3] (manual) Deploy `monitoring` through `Prod 1` → `Prod 2`. Run quickstart § 5 steps 1–4: gateway model scope, chat refused with the memory key, `ss -tnp` on the memory LXC, memory stopped while chat works and a log line in Loki within 5 minutes. Record the results in `specs/097-hermes-long-term-memory/quickstart.md`.

**Checkpoint**: US3 delivered. Cost and failure behaviour are proven and monitored.

---

## Phase 6: User Story 4 — Memory survives a rebuild and can be restored (P2)

**Goal**: A restore drill brings the store back from the nightly backup, by both the dump and
the portable export (FR-007, FR-018, SC-006).

**Independent Test**: quickstart § 9.

### Tests for User Story 4

- [ ] T056 [P] [US4] Extend `python/tests/guardrails/test_service_backup.py` to cover `ansible/playbooks/memory-restore-drill.yml`: extraction happens inside the `block` that owns the `always:` cleanup (the rule at line about 240).

### Implementation for User Story 4

- [ ] T057 [US4] Create `ansible/roles/service_backup/templates/restore/memory-compose.yml.j2`: throwaway `memory_postgres_restore` and `memory_api_restore` on their own network, API on port `8889`, `server.env` re-rendered with the restore database URL and the same `clients.json`.
- [ ] T058 [US4] Create `ansible/playbooks/memory-restore-drill.yml`, modelled on `ansible/playbooks/restore-drill.yml` (Immich). Run it on `hosts: memory` with `become`, and `vars_files: ../roles/memory/defaults/main.yml`.
  1. Find the latest `{{ service_backups['memory'].dir }}/memory-backup-*.tar.gz` (overridable with `-e`).
  2. In a `block`: extract, render the restore compose, run `pg_restore` into `memory_postgres_restore`, start `memory_api_restore` and wait for `/health`.
  3. Compare `GET /v1/default/banks/owner/stats` (`total_documents`, `total_nodes`) with `stats.json`.
  4. For each entry in the archive's `drill-probes.json`, recall its `query` on the restored instance (admin key, the gateway's embedder) and assert that its `unit_id` is among the top 3 results.
  5. Import `owner-export.zip` into an empty bank `restore-import` and assert the same document count.
  6. `always:` tears down both containers and the drill directory.
- [ ] T059 [US4] Extend `ansible/roles/service_backup/templates/snapshot/memory.sh.j2` (from T025) to write `drill-probes.json`. Pick 3 random active units from bank `owner` (`list_memories`, admin key) and store `{unit_id, query}` for each, where `query` is the first 200 characters of the unit's text.
  - The probe set is generated from the store at backup time and lives only inside the backup archive on the NAS, so no question about the owner is committed to this public repository (U3).
  - With fewer than 3 units in the bank, write the units that exist. With none, write an empty list, and the drill checks stats only.
- [ ] T060 [US4] (manual) After one nightly backup, run `ansible-playbook -i ansible/inventories/prod/hosts.yml ansible/playbooks/memory-restore-drill.yml` (quickstart § 9). Record the result in `specs/097-hermes-long-term-memory/quickstart.md`.

**Checkpoint**: US4 delivered. Both restore paths are proven.

---

## Phase 7: User Story 5 — I can see, correct and forget memories (P2)

**Goal**: Every client can browse and edit through six MCP tools. The web UI on the portal
page can browse, correct, hide, hard-delete and retry, behind its own login (FR-009, FR-013,
FR-023, SC-011).

**Independent Test**: quickstart § 8 and § 11.

### Tests for User Story 5

- [ ] T061 [P] [US5] Extend `python/tests/guardrails/test_hermes_env_modes.py`. Add `AUXILIARY_MCP_MEMORY_API_KEY` to the frozen PROD and LAB credential sets (lines about 216–237), with a comment citing 097 R-009.
- [ ] T062 [P] [US5] Write `python/tests/guardrails/test_hermes_memory_mcp.py`. Render `ansible/roles/hermes/templates/hermes-agent-egress.sh.j2` and `agent-config.yaml.j2` with the memory entry in `hermes_mcp_servers`, and assert:
  - no `MCP_DESTINATIONS` element for a `via_proxy: true` entry;
  - the agent's `mcp_servers.memory.headers.Authorization` equals `Bearer ${AUXILIARY_MCP_MEMORY_API_KEY}`;
  - the Open WebUI connection fact uses `webui_vault_var` (`memory_client_open_webui_key`);
  - the memory entry's `url` starts with `https://memory-api.` and never contains `:8888` (G1, spec FR-010).
  - Simulate the `set_fact` expression from `ansible/roles/hermes/tasks/main.yml:217-236` in Python.
- [ ] T063 [P] [US5] Extend `python/tests/guardrails/test_memory_config.py`:
  - `ui.env.j2` renders `HINDSIGHT_CP_ACCESS_KEY` and `HINDSIGHT_CP_DATAPLANE_API_KEY`, both non-empty, and nothing else secret;
  - the compose `memory_ui` service binds `{{ memory_ip }}:{{ memory_ui_port }}` only, has `mem_limit: 384m`, and sets `HINDSIGHT_CP_DATAPLANE_API_URL=http://memory_api:8888`;
  - the `caddy_services` entry `memory` has `user_facing: true`.

### Implementation for User Story 5

- [ ] T064 [US5] Add the memory MCP entry to `hermes_mcp_servers` in `ansible/group_vars/services/vars.yml`: `{name: memory, url: "https://memory-api.{{ caddy_base_domain }}/mcp/", auth: bearer, credential_env: AUXILIARY_MCP_MEMORY_API_KEY, vault_var: memory_client_hermes_key, webui_vault_var: memory_client_open_webui_key, via_proxy: true, enabled: true}`. Add a comment explaining both new fields (097 R-005, R-009).
- [ ] T065 [US5] Support the two new fields in the hermes role.
  - **Connection key**: in `ansible/roles/hermes/tasks/main.yml:217-236`, use `item.webui_vault_var | default(item.vault_var | default(item.credential_env | lower))` for the Open WebUI connection key.
  - **Egress rule**: in `ansible/roles/hermes/templates/hermes-agent-egress.sh.j2` (line about 25), filter out `via_proxy` entries from `MCP_DESTINATIONS`. They are covered by rule 6 (reverse proxy :443).
  - **Egress probe**: in the probe list (`ansible/roles/hermes/tasks/main.yml:406-512`), probe a `via_proxy` entry as `reverse_proxy_ip:443`, not as its URL host.
  - **Preflight**: `ansible/roles/hermes/tasks/preflight.yml` (lines about 146–163) must accept the new optional fields.
- [ ] T066 [US5] Add the web UI to the memory role (research R-020).
  - **Env file**: create `ansible/roles/memory/templates/ui.env.j2` with `HINDSIGHT_CP_ACCESS_KEY={{ memory_ui_access_key }}` and `HINDSIGHT_CP_DATAPLANE_API_KEY={{ memory_client_control_plane_key }}`. Render it at 0600 with `no_log`.
  - **Compose**: add the `memory_ui` service to `ansible/roles/memory/templates/docker-compose.yml.j2`:
    - `image: memory_ui_image`, `env_file: ui.env`;
    - `environment: HINDSIGHT_CP_DATAPLANE_API_URL=http://memory_api:8888`;
    - `ports: "{{ memory_ip }}:{{ memory_ui_port }}:9999"`, `mem_limit: 384m`;
    - `depends_on` the healthy `memory_api`.
  - **Preflight**: `ansible/roles/memory/tasks/preflight.yml` already asserts `memory_ui_access_key`. Add a message: "upstream serves the UI open without it".
  - **Health**: extend the health wait in `ansible/roles/memory/tasks/main.yml` and `scripts/healthcheck/memory.sh` to `GET http://{{ memory_ip }}:{{ memory_ui_port }}/api/health`.
- [ ] T067 [P] [US5] Add the portal entry `{host: memory, ip: "{{ memory_ip }}", port: "{{ memory_ui_port }}", title: "Memory", desc: "Shared AI memory: browse and edit", enabled: true, user_facing: true}` to `caddy_services` in `ansible/group_vars/services/vars.yml`.
- [ ] T068 [US5] (manual) Deploy `memory`, then `hermes`, then `reverse_proxy` through `Prod 1` → `Prod 2`.
  - **LAB stage**: the UI's lab copy answers `/api/health` and serves `/login` without data. Record its resident memory (quickstart § 2 "memory web UI").
  - **PROD**: run quickstart § 11 steps 1–5.
- [ ] T069 [US5] (manual) Add the MCP server in Claude Code's user scope: `claude mcp add --scope user --transport http memory https://memory-api.hus-sky.no/mcp/ --header "Authorization: Bearer <key from keychain>"`. Do this only if T048 confirmed the risk. Document it in the dotfiles README without the key.
- [ ] T070 [US5] (manual) Run quickstart § 8, including step 4, the resurrection check. If an edited or invalidated fact comes back after appending to the same session, carry out T071. Otherwise mark T071 "not needed" with the date.
- [ ] T071 [US5] (conditional on T070) Switch every adapter to one document per turn (research R-012): `document_id = <session>-<turn_index>` in `ansible/roles/hermes/files/open_webui/memory_filter.py` and the dotfiles `claude-memory-hook`, and the plugin's `bank_id_template`/`document_id` setting in `ansible/roles/hermes/templates/hindsight-config.json.j2` if the plugin offers one; otherwise record that limit in research R-012. Then update contracts/turn-format.md and re-run the harness gate (T046).
- [ ] T072 [US5] (manual) Run quickstart § 6 steps 5–6 (SC-009): set `memory_claude_code_scope: readonly`, deploy `memory`, check; set it to `revoked`, deploy, check; restore `readwrite`. Record the results.

**Checkpoint**: US5 delivered. Memory can be inspected, corrected and forgotten from every
client and from the portal.

---

## Phase 8: Polish & cross-cutting

- [ ] T073 [P] Make the amendments of FR-022:
  - `docs/backlog/083-hermes-agent-runtime.md` FR-018: built-in memory plus Hindsight via 097.
  - `docs/backlog/065-hermes-service.md`: Open WebUI memories retired, filter added.
  - `specs/002-core-services-lxc/spec.md` line about 111: add `memory` to the service list.
  - `docs/architecture.md` line about 40: rebuild table.
  - `docs/backlog/097-hermes-long-term-memory.md` Status: point to `specs/097-hermes-long-term-memory/`. Supersede "egress allowlist gains one rule" (R-005) and "plugin 1.2.1" (R-003).
- [ ] T074 (manual) One week after T047, measure SC-007: peak `node_memory_MemAvailable_bytes` on `memory` must stay above 30 % of 2048 MB. If not, raise `memory` in `terraform/services/memory/main.tf` and redeploy. Record the result in quickstart § 10.
- [ ] T075 (manual) Seven days after T055, enable the log rules from T054: set `enabled: true` with `baseline: {from, to, max_15m}` from Loki in `ansible/host_vars/memory.yml` and `ansible/host_vars/hermes.yml`, then deploy `monitoring`.
- [ ] T076 Run `bash scripts/ci/python-tests.sh`, `pre-commit run --all-files`, `bash scripts/ci/terraform-validate.sh` and `task mutmut:gate`. All must be green, with `memory_access.py` at or above `python/mutmut-threshold.txt`.
- [ ] T077 Set the Status line of `specs/097-hermes-long-term-memory/spec.md` to "Delivered" with the date, list any open manual checks, and tick the tasks in this file.

---

## Dependencies & execution order

### Phase dependencies

- **Setup (Phase 1)**: T001 and T002 first (manual). T003 and T004 can run in parallel.
- **Foundational (Phase 2)**: depends on Phase 1.
  - Tests T005, T006 and T007 come before T008 to T014.
  - T008 → T010 (the shim needs the policy).
  - T011 → T012, T013, T014, T015 → T016 → T017.
  - T019, T020, T021, T022, T024, T025 and T026 are independent.
  - T023 comes before T027.
  - T027 (deploy) closes the phase.
- **US1 (Phase 3)**: depends on T027. T028 and T029 → T030 → T031 → T032, T033, T034 → T035 → T036 (gate) → T037 → T038.
- **US2 (Phase 4)**: depends on T038, because the harness gate builds on US1's candidate.
  - Open WebUI: T039, T040 → T041 → T042 → T043 → T044.
  - Harness: T045 → T046 → T047.
  - Claude Code: T048 gates T049 → T050 → T051.
- **US3 (Phase 5)**: depends on T027 (metric names) and on traffic from T038. It can run in parallel with US2.
- **US4 (Phase 6)**: depends on T025 and one nightly backup. It can run in parallel with US2 and US3.
- **US5 (Phase 7)**:
  - MCP: depends on T038 (T061 to T065).
  - Web UI: depends on T027 (T063, T066 to T068).
  - Claude Code MCP: depends on T048 (T069).
  - Forget check: T070 needs adapters live (T038; T047 for all three).
- **Polish (Phase 8)**: after the stories it touches.

### User story dependencies

- **US1**: needs the foundation only. It is the MVP.
- **US2**: needs US1's harness candidate. Its Claude Code part needs the guidance confirmation (T048).
- **US3**: needs the foundation and US1 traffic for a meaningful staleness alert.
- **US4**: needs the foundation's backup.
- **US5**: MCP needs US1. The UI needs only the foundation.

## Parallel examples

```text
# Phase 2 tests together:
T005 python/tests/memory_access/test_policy.py
T006 python/tests/guardrails/test_memory_config.py
# then independent infra files together:
T019 terraform/services/memory/*   T020 scripts/lab/* + workflow   T021 proxmox_mounts
T022 caddy + healthcheck          T024 lab switches              T026 alloy redaction

# US1 tests together:
T028 test_hermes_memory_config.py   T029 test_hermes_memory_plugin_pins.py

# After T038, three streams:
US2 Open WebUI (T039–T044) | US3 monitoring (T052–T055) | US5 web UI (T063, T066–T068)
```

## Implementation strategy

### MVP = Phase 1 + Phase 2 + US1

1. Phases 1 and 2: the store is live, authenticated and backed up (T027).
2. US1: the harness gate passes (T036), then Hermes gets memory in PROD (T038).
3. **Stop and validate** with quickstart § 4. This is a usable increment: Hermes remembers beyond
   its built-in budget.

### Incremental after MVP

1. US3: monitoring and the cost proof. It is small and makes the MVP safe to leave running.
2. US2: Open WebUI first, then Claude Code after T048.
3. US5: MCP tools and the web UI. Then the forget check, which may trigger T071.
4. US4: the restore drill, after the first week of backups.
5. Polish: the SC-007 measurement and log-rule baselines on their dates.

## Notes

- Every PROD step goes through `Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`, so the LAB
  rehearsal runs first (`067`).
- Push commits through the GitHub API (CLAUDE.md, Zscaler constraint). Branch
  `097-hermes-long-term-memory`.
- Tasks that touch `scripts/lab/**` need the PR label `allow-protected-path-changes`.
- Never print a vault value. Placeholders in tests start `hmem_test`.
