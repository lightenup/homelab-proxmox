# Implementation Plan: Pushover Alerting Integration

**Branch**: `043-alerting-pushover` | **Date**: 2026-03-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/043-alerting-pushover/spec.md`

## Summary

Add Pushover push notifications as a second alerting channel alongside existing email. Critical alerts (7 rules) are delivered at emergency priority with 60-second retry until acknowledged. Warning alerts (11 rules) are delivered at normal priority respecting quiet hours. The integration is opt-in via a feature flag (`pushover_enabled`, default `false`), with credentials stored in Ansible vault. When disabled, the Alertmanager configuration is byte-identical to the pre-feature state. Implementation requires modifying 4 existing files — no new containers, processes, or infrastructure.

## Technical Context

**Language/Version**: Ansible (Jinja2 templates), YAML configuration
**Primary Dependencies**: Alertmanager v0.30.0 (native `pushover_configs` support), Pushover API
**Storage**: N/A (configuration change only — no persistent data)
**Testing**: `ansible-lint`, `promtool check rules` (via Docker), `scripts/monitoring/smoke-test.sh`, manual Alertmanager API test
**Target Platform**: Monitoring LXC (192.168.1.214), Debian stable
**Project Type**: Infrastructure-as-code (Ansible roles)
**Performance Goals**: Push notification delivery within 2 minutes of alert firing (NFR-001)
**Constraints**: No new containers (C-003), secrets in vault only (C-001), idempotent deployments (C-001)
**Scale/Scope**: 18 alert rules (7 critical, 11 warning), single operator, ~0–3 alerts/day

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All changes traced to spec FR-001–FR-017. Feature directory exists at `specs/043-alerting-pushover/`. |
| II | Secrets Policy | ✅ PASS | `pushover_user_key` and `pushover_api_token` stored exclusively in `vault.yml`. Template uses `no_log: true`. Assertion validates presence without logging values. |
| III | Separation of Concerns | ✅ PASS | All changes are Ansible (configuration inside machines). No Terraform changes. Alertmanager is already provisioned by Features 040–042. |
| IV | Code Economy (YAGNI) | ✅ PASS | 4 files modified, 0 new files created. No wrapper functions, no abstract patterns. Feature flag is justified (FR-011). Two receivers (not one with dynamic priority) because each has distinct config fields (retry/expire only on critical). No `info` route deployed (FR-016 SHOULD, not MUST). |
| V | Dual-Provisioning Parity | ✅ PASS | Monitoring playbook already works from both CI and laptop. No new scripts, workflows, or CI-only paths. Vault accessible in both contexts per existing pattern. |

**Post-design re-check**: ✅ All gates still PASS. No new files created (YAGNI). No CI workflow changes needed (dual-provisioning). Credentials vault-only (secrets policy).

## Project Structure

### Documentation (this feature)

```text
specs/043-alerting-pushover/
├── spec.md                    # Feature specification
├── plan.md                    # This file
├── research.md                # Phase 0: Technology research and decisions
├── data-model.md              # Phase 1: Configuration entities and relationships
├── quickstart.md              # Phase 1: Operator setup guide
├── checklists/
│   └── requirements.md        # Pre-existing spec quality checklist
└── tasks.md                   # Phase 2 output (NOT created by plan)
```

### Source Code (repository root)

```text
ansible/roles/monitoring_stack/
├── defaults/main.yml                    # MODIFIED: Add pushover_enabled, retry, expire defaults
├── templates/alertmanager.yml.j2        # MODIFIED: Add conditional Pushover receivers and routes
└── tasks/main.yml                       # MODIFIED: Add credential validation assert

ansible/group_vars/monitoring/
└── vars.yml                             # MODIFIED: Add vault reference comment for pushover credentials
```

**Structure Decision**: No new files. All changes extend existing files in the `monitoring_stack` role. This follows Constitution IV (Code Economy) — the feature flag, 2 receivers, and 2 routes are injected via Jinja2 conditionals in the existing Alertmanager template.

## File Manifest

| File | Action | Purpose | Traces to |
|------|--------|---------|-----------|
| `ansible/roles/monitoring_stack/defaults/main.yml` | MODIFY | Add `pushover_enabled`, `pushover_retry_interval`, `pushover_expire_duration`, `pushover_grafana_url` | FR-011, FR-014, DL-05 |
| `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` | MODIFY | Add conditional Pushover receivers and severity-based routes | FR-001–FR-010, FR-015 |
| `ansible/roles/monitoring_stack/tasks/main.yml` | MODIFY | Add credential validation assert before compose_stack | FR-012 |
| `ansible/group_vars/monitoring/vars.yml` | MODIFY | Add comment documenting vault variables for Pushover | FR-013 |

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Push notification service | Pushover (native Alertmanager receiver) | A-003: Alertmanager v0.30.0 has built-in `pushover_configs`. No plugins, webhooks, or sidecars needed. |
| Feature gating | Jinja2 conditional blocks (`{% if pushover_enabled %}`) | Produces byte-identical config when disabled. No runtime overhead. Follows existing template patterns. |
| Credential validation | `ansible.builtin.assert` task | Fail-fast with clear error. `no_log: true` prevents credential leak. Single task, no new file (YAGNI). |
| Routing strategy | Child routes with `continue: true` + catch-all email | Ensures all alerts reach both channels. Verified against Alertmanager routing semantics. See `research.md` Area 3. |
| Priority mapping | Two separate receivers (critical=emergency, warning=normal) | Simpler than dynamic priority template in one receiver. Each receiver has distinct config fields (retry/expire only on critical). |

## Implementation Steps

### Step 1: Add Pushover defaults to role defaults

- **Files**: `ansible/roles/monitoring_stack/defaults/main.yml`
- **Description**: Append three new variables after the existing Alertmanager configuration block:
  ```yaml
  # Pushover push notification configuration
  # Feature: 043-alerting-pushover (FR-011, FR-014)
  pushover_enabled: false
  pushover_retry_interval: "1m"
  pushover_expire_duration: "1h"
  pushover_grafana_url: "{{ grafana_protocol | default('https') }}://{{ grafana_domain }}"
  ```
  These are role defaults — can be overridden in `group_vars`, `host_vars`, or `-e` extra vars. Note: `pushover_grafana_url` composes the Grafana URL from existing variables (`grafana_protocol` is defined in `group_vars/monitoring/vars.yml` but NOT in defaults, so the `default('https')` filter is a safety net). This avoids an undefined variable error if deployed without group_vars (e.g., CI/lab).
- **Dependencies**: None
- **Parallel-safe**: Yes
- **Traces to**: FR-011 (default disabled), FR-014 (role defaults with overridability), DL-05 (Grafana URL in notifications)
- **Done-condition**: `ansible-lint ansible/roles/monitoring_stack/defaults/main.yml` returns 0. File contains exactly `pushover_enabled: false`, `pushover_retry_interval: "1m"`, `pushover_expire_duration: "1h"`, `pushover_grafana_url`.

### Step 2: Add vault reference comment to group_vars

- **Files**: `ansible/group_vars/monitoring/vars.yml`
- **Description**: Add a comment line in the Alertmanager configuration section documenting that Pushover credentials live in vault.yml, following the existing pattern for SMTP credentials:
  ```yaml
  # pushover_user_key, pushover_api_token → vault.yml (when pushover_enabled=true)
  ```
  This is placed after the existing `# smtp_server, smtp_username, ...` comment block.
- **Dependencies**: None
- **Parallel-safe**: Yes (different file from Step 1)
- **Traces to**: FR-013 (credentials in vault), Constitution II (secrets policy)
- **Done-condition**: `grep -q 'pushover_user_key.*pushover_api_token.*vault.yml' ansible/group_vars/monitoring/vars.yml` returns 0.

### Step 3: Add credential validation assert to tasks/main.yml

- **Files**: `ansible/roles/monitoring_stack/tasks/main.yml`
- **Description**: Insert an assert task **before** the `include_tasks: compose_stack.yml` line. The task validates that `pushover_user_key` and `pushover_api_token` are defined and non-empty, but only when `pushover_enabled` is true. Uses `no_log: true` to prevent credential values from appearing in output.
  ```yaml
  - name: Validate Pushover credentials when enabled
    ansible.builtin.assert:
      that:
        - pushover_user_key is defined
        - pushover_user_key | length > 0
        - pushover_api_token is defined
        - pushover_api_token | length > 0
      fail_msg: >-
        Pushover is enabled (pushover_enabled=true) but credentials are missing.
        Add 'pushover_user_key' and 'pushover_api_token' to
        ansible/group_vars/monitoring/vault.yml.
    when: pushover_enabled | default(false) | bool
    no_log: true
    tags: [compose, pushover]
  ```
- **Dependencies**: Step 1 (pushover_enabled must be defined as default)
- **Parallel-safe**: No (depends on Step 1)
- **Traces to**: FR-012 (validate credentials when enabled), US-4 AC-4.3 (clear error on missing credentials)
- **Done-condition**: `ansible-lint ansible/roles/monitoring_stack/tasks/main.yml` returns 0. The assert task appears before the `compose_stack.yml` include. Running the playbook with `pushover_enabled=true` and no vault credentials produces a failure message containing "credentials are missing".

### Step 4: Extend alertmanager.yml.j2 with Pushover receivers and routes

- **Files**: `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2`
- **Description**: This is the core change. Extend the template with Jinja2 conditional blocks:

  **4a. Add child routes** under the `route:` section (after `repeat_interval`):
  ```yaml
  {% if pushover_enabled | default(false) | bool %}
    routes:
      - receiver: 'pushover-critical'
        matchers:
          - severity = "critical"
        continue: true
      - receiver: 'pushover-warning'
        matchers:
          - severity = "warning"
        continue: true
      - receiver: 'email-default'
  {% endif %}
  ```

  **4b. Add Pushover receivers** after the `email-default` receiver block:
  ```yaml
  {% if pushover_enabled | default(false) | bool %}
    - name: 'pushover-critical'
      pushover_configs:
        - user_key: '{{ pushover_user_key }}'
          token: '{{ pushover_api_token }}'
          send_resolved: true
          priority: '{{"{{ if eq .Status \"firing\" }}2{{ else }}0{{ end }}"}}'
          retry: {{ pushover_retry_interval }}
          expire: {{ pushover_expire_duration }}
          title: '{{"{{ if eq .Status \"firing\" }}"}}[CRITICAL] {{"{{ .GroupLabels.alertname }}"}}{{"{{ else }}"}}[RESOLVED] {{"{{ .GroupLabels.alertname }}"}}{{"{{ end }}"}}'
          message: |
            {{"{{ range .Alerts }}"}}
            {{"{{ .Annotations.summary }}"}}
            {{"{{ end }}"}}
          url: '{{ pushover_grafana_url }}'

    - name: 'pushover-warning'
      pushover_configs:
        - user_key: '{{ pushover_user_key }}'
          token: '{{ pushover_api_token }}'
          send_resolved: true
          priority: '0'
          title: '{{"{{ if eq .Status \"firing\" }}"}}[WARNING] {{"{{ .GroupLabels.alertname }}"}}{{"{{ else }}"}}[RESOLVED] {{"{{ .GroupLabels.alertname }}"}}{{"{{ end }}"}}'
          message: |
            {{"{{ range .Alerts }}"}}
            {{"{{ .Annotations.summary }}"}}
            {{"{{ end }}"}}
          url: '{{ pushover_grafana_url }}'
  {% endif %}
  ```

  **Key design decisions embedded in this template**:
  - `continue: true` on Pushover routes ensures alerts fall through to the catch-all email route (FR-007, FR-008)
  - Catch-all `email-default` child route (no matchers) ensures all alerts reach email (FR-007)
  - Critical priority uses Go template conditional: `2` when firing, `0` when resolved (avoids emergency-priority resolved notifications)
  - Warning priority is static `0` (normal) for both firing and resolved
  - `retry` and `expire` only on critical receiver (only meaningful for emergency priority)
  - Title uses `[CRITICAL]`/`[WARNING]` prefix when firing, `[RESOLVED]` when resolved (FR-005, US-3)
  - Message iterates over all alerts in the group using `{{ range .Alerts }}` (handles grouped alerts per AC-1.6)
  - `url` uses `{{ pushover_grafana_url }}` (composed in defaults from `grafana_protocol` + `grafana_domain`, with `https` fallback for safety — DL-05)
  - Inhibition rules section is untouched (C-002)

- **Dependencies**: Step 1 (variables must be defined), Step 3 (validation must exist)
- **Parallel-safe**: No (depends on Steps 1, 3)
- **Traces to**: FR-001–FR-010, FR-015, US-1–US-5
- **Done-condition**: Template renders without Jinja2 errors. With `pushover_enabled=false`, the rendered output is byte-identical to the pre-change template output (no Pushover receivers or routes). With `pushover_enabled=true`, the rendered output contains `pushover-critical`, `pushover-warning` receivers and severity-based routes with `continue: true`. The `email-default` receiver configuration is unchanged in both cases.

### Step 5: Verify template rendering (disabled state)

- **Files**: (no file changes — verification only)
- **Description**: Render the Alertmanager template with `pushover_enabled=false` (default) and diff against the current production config to confirm zero behavioral change.
  ```bash
  # On a development machine with Ansible:
  ansible-playbook playbooks/monitoring.yml --check --diff -e pushover_enabled=false
  ```
  The Alertmanager configuration task should show no diff (idempotent).
- **Dependencies**: Step 4
- **Parallel-safe**: No
- **Traces to**: FR-011 (disabled by default), US-4 AC-4.1, AC-4.2, SC-006
- **Done-condition**: `ansible-playbook --check --diff` shows no changes to `alertmanager.yml` when `pushover_enabled=false`.

### Step 6: Verify template rendering (enabled state)

- **Files**: (no file changes — verification only)
- **Description**: Render the Alertmanager template with `pushover_enabled=true` and valid mock credentials. Validate the generated config with `amtool check-config` or manual inspection.
  - Confirm 3 receivers: `email-default`, `pushover-critical`, `pushover-warning`
  - Confirm 3 child routes under root: critical match, warning match, email catch-all
  - Confirm `continue: true` on both Pushover routes
  - Confirm `email-default` receiver is unchanged
  - Confirm all 8 inhibition rules are unchanged
  - Confirm `priority: 2` (firing) / `0` (resolved) on critical receiver
  - Confirm `priority: 0` on warning receiver
  - Confirm `retry` and `expire` only on critical receiver
- **Dependencies**: Step 4
- **Parallel-safe**: Yes (with Step 5 — different `-e` flags)
- **Traces to**: FR-001–FR-010, FR-015, SC-008, SC-010
- **Done-condition**: Generated `alertmanager.yml` passes `amtool check-config` (or `docker run prom/alertmanager:v0.30.0 amtool check-config`). Manual inspection confirms all 6 verification points above.

### Step 7: Lint and validate

- **Files**: (no file changes — validation only)
- **Description**: Run project linting and validation:
  ```bash
  ansible-lint ansible/roles/monitoring_stack/
  ```
  Verify no new warnings or errors introduced by the changes.
- **Dependencies**: Steps 1–4
- **Parallel-safe**: No
- **Traces to**: Constitution I (quality gate)
- **Done-condition**: `ansible-lint` returns 0 with no new warnings for the modified files.

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Jinja2/Go template escaping error produces invalid YAML | High — Alertmanager container fails to start | Low — following established pattern in existing template | Step 6 validates rendered config. Existing `promtool check rules` catches syntax errors at deploy time. |
| `continue: true` routing doesn't behave as expected | High — email delivery breaks | Very Low — verified against official docs and community examples (research.md Area 3) | Step 5 verifies disabled-state is unchanged. Step 6 verifies enabled-state routing structure. |
| Pushover API rate limit exceeded | Medium — notifications delayed | Very Low — homelab generates ~0–3 alerts/day, limit is 7,500/month | Not mitigated — acceptable risk given volume (A-007). |
| Operator forgets to add vault credentials before enabling | Low — playbook fails | Medium — human error | Step 3 credential assertion provides clear error message (FR-012). Quickstart documents setup order. |
| Emergency priority notifications annoy operator at night for genuine critical alerts | Medium — operator fatigue | Low — only 7 critical rules, most indicate real issues | By design (spec DL-03). Critical alerts SHOULD bypass quiet hours. Operator can adjust Pushover app settings. |

## Testing Strategy

- **Lint**: `ansible-lint` on modified role — catches YAML, Ansible, and Jinja2 issues.
- **Template validation**: Render template with `pushover_enabled=false` → diff shows zero changes. Render with `pushover_enabled=true` → validate with `amtool check-config`.
- **Credential validation test**: Run playbook with `pushover_enabled=true` but no vault credentials → assert fails with expected message (SC-007).
- **Idempotency test**: Run playbook twice with same config → second run shows no changes (SC-009).
- **Smoke test**: After deployment, run `scripts/monitoring/smoke-test.sh` → all 5 containers healthy, all endpoints responding (existing verification).
- **Manual integration test**: Fire test alerts via Alertmanager API (see quickstart.md) → verify push + email delivery for critical, warning, and resolved notifications (SC-001–SC-005).
- **Coverage target**: 100% of FRs covered by at least one verification method. All 10 success criteria (SC-001–SC-010) have documented test procedures.

## Complexity Tracking

No constitution violations to justify. All gates PASS.
