# Tasks: Pushover Alerting Integration

**Input**: Design documents from `/specs/043-alerting-pushover/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Summary

- **Total tasks**: 7
- **Estimated complexity**: Low (4 file modifications, 0 new files, pure Ansible/Jinja2 configuration)
- **Parallel tracks**: 2 (T001 + T002 in Phase 2; T006 + T007 in Phase 4)
- **Task count by story**: US4: 3 (T001–T003, foundational), US1/US2/US3/US5: 1 (T004, core template), Validation: 3 (T005–T007)

---

## Phase 1: Setup

Not applicable. The `monitoring_stack` Ansible role and all infrastructure (Alertmanager v0.30.0, Docker Compose stack, email receiver, 18 alert rules, 8 inhibition rules) are fully deployed from Features 040–042. No new directories, containers, or processes are required — this feature is a pure configuration extension.

---

## Phase 2: Foundational — Feature Flag & Credential Safety (User Story 4, Priority: P2)

**Goal**: Establish the opt-in mechanism (`pushover_enabled: false` default), sensible tuning defaults, and a fail-fast credential validation gate before any Alertmanager template change is deployed.

**⚠️ CRITICAL**: T003 (credential validation) depends on T001 (defaults) and both MUST complete before T004 (template extension). The Alertmanager template references `pushover_enabled`, `pushover_retry_interval`, `pushover_expire_duration`, `pushover_grafana_url`, `pushover_user_key`, and `pushover_api_token`.

**Independent Test**: Run the monitoring playbook with `pushover_enabled=false` (default). Confirm zero diff on `alertmanager.yml` — pre-feature state is preserved (SC-006, US-4 AC-4.2). Run with `pushover_enabled=true` and no vault credentials — playbook fails immediately with a clear error identifying the missing variables (SC-007, US-4 AC-4.3).

- [X] T001 [P] [US4] Add Pushover default variables to `ansible/roles/monitoring_stack/defaults/main.yml`

  **What**: Append four variables after the `timezone: "Europe/Copenhagen"` line (current end of file):

  ```yaml
  # Pushover push notification configuration
  # Feature: 043-alerting-pushover (FR-011, FR-014)
  pushover_enabled: false
  pushover_retry_interval: "1m"
  pushover_expire_duration: "1h"
  pushover_grafana_url: "{{ grafana_protocol | default('https') }}://{{ grafana_domain }}"
  ```

  `pushover_enabled: false` is the feature-flag default — ensures the monitoring stack deploys without Pushover credentials (FR-011, US-4 AC-4.1, AC-4.2). `pushover_retry_interval: "1m"` (60 seconds) and `pushover_expire_duration: "1h"` (3600 seconds) are tunable role defaults satisfying FR-003: minimum retry is 30s per Pushover API, maximum expire is 10800s (3h) per Pushover API — both defaults are within valid ranges and match Alertmanager's own emergency-priority defaults (research.md Area 2). `pushover_grafana_url` composes the Grafana URL from existing variables — note that `grafana_protocol` is defined in `group_vars/monitoring/vars.yml` but NOT in role defaults, so the `default('https')` filter prevents an undefined variable error in bare-defaults deployments (CI/lab). These role defaults can be overridden in `group_vars`, `host_vars`, or `-e` extra vars (FR-014).

  **Traces to**: FR-011, FR-014, DL-05

  **Done-condition**:
  1. `grep -c 'pushover_enabled: false' ansible/roles/monitoring_stack/defaults/main.yml` returns `1`
  2. `grep -c 'pushover_retry_interval: "1m"' ansible/roles/monitoring_stack/defaults/main.yml` returns `1`
  3. `grep -c 'pushover_expire_duration: "1h"' ansible/roles/monitoring_stack/defaults/main.yml` returns `1`
  4. `grep -c 'pushover_grafana_url' ansible/roles/monitoring_stack/defaults/main.yml` returns `1`
  5. `ansible-lint ansible/roles/monitoring_stack/defaults/main.yml` returns exit code 0

---

- [X] T002 [P] [US4] Add vault reference comment to `ansible/group_vars/monitoring/vars.yml`

  **What**: Insert a comment line immediately after the existing vault reference comment `# smtp_server, smtp_username, smtp_password, smtp_from_address, alert_email_recipient → vault.yml` (currently the last line in the Alertmanager configuration section):

  ```yaml
  # pushover_user_key, pushover_api_token → vault.yml (when pushover_enabled=true)
  ```

  This follows the established pattern used for SMTP credentials and documents that Pushover credentials live in `vault.yml`. The operator sees this when editing `vars.yml` and knows exactly where to add credentials before enabling the feature flag (FR-013, Constitution II Secrets Policy).

  **Traces to**: FR-013, Constitution II (Secrets Policy)

  **Done-condition**:
  1. `grep -q 'pushover_user_key.*pushover_api_token.*vault.yml' ansible/group_vars/monitoring/vars.yml` returns exit code 0
  2. `grep -n 'smtp_server.*vault.yml' ansible/group_vars/monitoring/vars.yml` returns line N; `grep -n 'pushover_user_key.*vault.yml' ansible/group_vars/monitoring/vars.yml` returns line N+1 (comment appears on the next line immediately after the SMTP vault comment)

---

- [X] T003 [US4] Add Pushover credential validation assert to `ansible/roles/monitoring_stack/tasks/main.yml`

  **Depends on**: T001 (defines `pushover_enabled` in role defaults)

  **What**: Insert an assert task **before** the `Deploy Docker Compose stack` include block (`compose_stack.yml`). Place it after the `Configure NFS backup mount` when-conditional block (the `monitoring_nfs_enabled` block). The new task must appear before the line `- name: Deploy Docker Compose stack`:

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

  `no_log: true` prevents credential values from appearing in Ansible output or CI logs (Constitution II Secrets Policy). `when: pushover_enabled | default(false) | bool` ensures the assert is skipped when Pushover is disabled — zero impact on the default deployment path (US-4 AC-4.1). `fail_msg` names both missing variables and the exact file where they must be added — satisfies US-4 AC-4.3. Follows the `ansible.builtin.assert` pattern used by the `jellyfin` and `nextcloud` roles for vault preflight checks (Feature 041 pattern).

  **Traces to**: FR-012, US-4 AC-4.3

  **Done-condition**:
  1. `ansible-lint ansible/roles/monitoring_stack/tasks/main.yml` returns exit code 0
  2. `grep -n 'Validate Pushover credentials' ansible/roles/monitoring_stack/tasks/main.yml` returns line N
  3. `grep -n 'Deploy Docker Compose stack' ansible/roles/monitoring_stack/tasks/main.yml` returns line M
  4. N < M (assert appears before compose_stack include)
  5. `grep -A2 'Validate Pushover credentials' ansible/roles/monitoring_stack/tasks/main.yml | grep -q 'ansible.builtin.assert'` returns exit code 0
  6. `grep -A15 'Validate Pushover credentials' ansible/roles/monitoring_stack/tasks/main.yml | grep -q 'no_log: true'` returns exit code 0

**Checkpoint**: After T001–T003, `ansible-playbook --syntax-check ansible/playbooks/monitoring.yml` exits 0. Running the playbook with defaults (`pushover_enabled=false`) produces zero diff on `alertmanager.yml`. Running with `pushover_enabled=true` and no vault credentials fails immediately with "credentials are missing" message before Alertmanager is touched.

---

## Phase 3: User Stories 1 & 2 — Critical and Warning Push Notifications (Priority: P1) 🎯 MVP

**Goal**: Extend the Alertmanager Jinja2 template with conditional Pushover receiver configurations and severity-based routing. When `pushover_enabled=true`: critical alerts (7 rules) route to emergency-priority push + email; warning alerts (11 rules) route to normal-priority push + email; all 18 alerts continue to email. When `pushover_enabled=false`: the template renders byte-identically to the pre-feature state — no diff on Alertmanager config.

**Note**: US3 (resolution notifications via `send_resolved: true`) and US5 (email continuity via `continue: true` + catch-all route) are structurally included in T004 — they are implemented as receiver fields and routing semantics within the same single template change. They are not separate file modifications.

**Independent Test**: With `pushover_enabled=true` and mock credentials, render the template — confirm it contains 3 receivers (`email-default`, `pushover-critical`, `pushover-warning`), 3 child routes (critical match → continue, warning match → continue, catch-all → email-default), and the email receiver is byte-identical to pre-change. Config passes `amtool check-config` (SC-008, SC-010).

**Acceptance Scenarios covered** (from spec.md):
- Critical alert → emergency push (priority 2, retry 60s, expire 1h) + email (US1 AC-1.1–1.6)
- Warning alert → normal push (priority 0, respects quiet hours) + email (US2 AC-2.1–2.4)
- Alert resolves → resolved push for both severities at normal priority (US3 AC-3.1–3.2)
- Email delivery unchanged for all alerts in both enabled and disabled states (US5 AC-5.1–5.4)

### Implementation for User Stories 1, 2, 3, and 5

- [X] T004 [US1/US2/US3/US5] Extend `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` with conditional Pushover config

  **Depends on**: T001 (variables referenced in template), T003 (credential validation gate must exist before template is deployed)

  **Two insertions required in the existing template:**

  **4a — Add conditional child routes** under `route:` — insert immediately after the `repeat_interval: {{ alertmanager_repeat_interval }}` line (currently the last line under `route:`):

  ```jinja2
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

  **4b — Add conditional Pushover receivers** — insert after the closing `          </ul>` line of the `email-default` receiver's html body block, and before the blank line that precedes `inhibit_rules:`:

  ```jinja2
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

  **Design decisions embedded in the template** (verified in plan.md Step 4 and research.md):

  | Decision | Reasoning | Traces to |
  |----------|-----------|-----------|
  | Critical priority: `2` when firing, `0` when resolved (Go template conditional) | Emergency resolved notifications would require unnecessary acknowledgment; operator already knows the issue resolved from context | FR-015, research.md Area 2 |
  | Warning priority: static `0` for both firing and resolved | Normal priority respects quiet hours natively; no behavior change needed on resolve | FR-004, FR-015 |
  | `retry` and `expire` only on critical receiver | Only meaningful for emergency priority (Pushover API silently ignores these fields for priority < 2) | FR-003, research.md Area 2 |
  | `send_resolved: true` on both receivers | Resolution notifications close the operator feedback loop after remediation action (US3 AC-3.1, AC-3.2) | FR-006 |
  | `continue: true` on both Pushover child routes | Ensures alerts continue to next sibling (catch-all `email-default`) after matching a Pushover route (FR-008, research.md Area 3) | FR-008 |
  | Catch-all `email-default` child route (no matchers) | Ensures ALL alerts reach email regardless of severity label, including alerts with no severity (FR-007, FR-010) | FR-007, FR-010 |
  | Root `receiver: 'email-default'` retained | Serves as fallback when no child routes exist (`pushover_enabled=false`); ensures email delivery in disabled state too | FR-011 |
  | Title prefix `[CRITICAL]/[WARNING]` when firing, `[RESOLVED]` when resolved | Clear at-a-glance severity identification on phone; resolution closes the mental loop | FR-005 |
  | `{{ range .Alerts }}` in message body | Iterates all alerts in the group — one notification per alert group, not per individual alert instance (US1 AC-1.6) | FR-005 |
  | `url: '{{ pushover_grafana_url }}'` | One-tap path to Grafana (`https://grafana.hus-sky.no`); composed in defaults from `grafana_protocol` + `grafana_domain` with `https` fallback for bare-defaults safety (DL-05) | DL-05 |
  | `{{"{{ ... }}"}}` double-escaping for Go templates | Jinja2 renders `{{"..."}}` as literal string; Alertmanager then evaluates it as Go template. Established pattern from existing email receiver Subject and html fields (research.md Area 4) | research.md Area 4 |
  | `email-default` receiver block untouched | Email continuity — to address, headers, HTML body, send_resolved, timing, grouping all unchanged (FR-009, C-002) | FR-009, C-002 |
  | `inhibit_rules:` section untouched | Inhibition operates at alert level before routing; no changes needed (spec Out of Scope, C-002) | C-002 |

  **Traces to**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-015, US1–US3, US5

  **Done-condition**:
  1. `grep -q 'pushover-critical' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns exit code 0
  2. `grep -q 'pushover-warning' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns exit code 0
  3. `grep -c 'continue: true' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns `2` (one per Pushover child route)
  4. `grep -c "send_resolved: true" ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns `3` (`email-default` + `pushover-critical` + `pushover-warning`)
  5. `grep -c 'retry:' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns `1` (only on critical receiver)
  6. `grep -c 'expire:' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns `1` (only on critical receiver)
  7. `grep -q 'if eq .Status' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns exit code 0 (Go template conditional present for critical priority)
  8. `grep -c 'source_matchers:' ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` returns `8` (inhibit_rules unchanged, all 8 rules intact)
  9. `ansible-lint ansible/roles/monitoring_stack/templates/` returns exit code 0 (or template is excluded from lint per `.ansible-lint` config — verify which applies)

**Checkpoint**: After T004, the full integration is code-complete. With `pushover_enabled=false`, rendered output is byte-identical to pre-change state (0 occurrences of `pushover`, 1 receiver, 0 child routes). With `pushover_enabled=true`, rendered output contains 3 receivers and 3 child routes. The `email-default` receiver is unchanged in both states.

---

## Phase 4: Validation

**Purpose**: Mechanically verify all 4 modified files for syntax correctness, structural validity, and correct rendering in both enabled and disabled states. All 10 success criteria (SC-001–SC-010) are covered between automated validation and the quickstart.md manual tests.

- [X] T005 [ALL] Lint all modified files with `ansible-lint ansible/roles/monitoring_stack/`

  **Depends on**: T001, T002, T003, T004

  **What**: Run ansible-lint against the monitoring_stack role:

  ```bash
  ansible-lint ansible/roles/monitoring_stack/
  ```

  Catches YAML syntax errors, Ansible module usage issues, and Jinja2 template problems introduced by the 4 file modifications. Pre-existing warnings in the role (from Features 040–042) are not regressions and do not constitute failure.

  **Traces to**: Constitution I (quality gate)

  **Done-condition**:
  1. `ansible-lint ansible/roles/monitoring_stack/` returns exit code 0
  2. No new warnings attributable to `defaults/main.yml`, `tasks/main.yml`, `group_vars/monitoring/vars.yml`, or `templates/alertmanager.yml.j2`

---

- [X] T006 [P] [US4/US5] Verify disabled-state template rendering (`pushover_enabled=false`)

  **Depends on**: T004

  **What**: Confirm the Alertmanager template renders identically to the pre-feature state when `pushover_enabled=false` (the default). Verify all 5 criteria below:

  ```bash
  # Option A — check mode diff on target host (preferred):
  ansible-playbook ansible/playbooks/monitoring.yml --check --diff -e pushover_enabled=false
  # Alertmanager config task must show no diff (zero changes)

  # Option B — local inspection (if Ansible is available locally):
  # Manually render the template with pushover_enabled=false and verify criteria
  ```

  Minor whitespace differences (extra blank lines from `{% if false %}` blocks being omitted) are acceptable — they do not affect Alertmanager config semantics.

  **Traces to**: FR-011, SC-006, SC-008, US-4 AC-4.1, AC-4.2, US-5 AC-5.3, AC-5.4

  **Done-condition**:
  1. Rendered `alertmanager.yml` with `pushover_enabled=false` contains 0 occurrences of the string `pushover`
  2. Rendered `alertmanager.yml` contains exactly 1 receiver (`email-default` block only)
  3. Rendered `alertmanager.yml` `route:` section has no `routes:` child key
  4. Rendered `alertmanager.yml` contains exactly 8 `source_matchers:` entries (inhibit_rules unchanged)
  5. `route.group_by`, `route.group_wait`, `route.group_interval`, `route.repeat_interval` values are identical to pre-feature values

---

- [X] T007 [P] [US1/US2/US3] Verify enabled-state template rendering and config validity (`pushover_enabled=true`)

  **Depends on**: T004

  **What**: Render the Alertmanager template with `pushover_enabled=true` and mock credentials (`pushover_user_key: "test"`, `pushover_api_token: "test"`), then validate structural correctness and Alertmanager config syntax:

  ```bash
  # Validate config syntax (if Docker is available):
  docker run --rm \
    -v /path/to/rendered/alertmanager.yml:/etc/alertmanager/alertmanager.yml \
    prom/alertmanager:v0.30.0 \
    amtool check-config /etc/alertmanager/alertmanager.yml

  # Verify routing matrix via manual inspection of rendered output:
  # - 3 receivers: email-default, pushover-critical, pushover-warning
  # - 3 child routes under route.routes
  # - continue: true on first two child routes (pushover-critical, pushover-warning)
  # - no-matcher catch-all route (email-default) as third child
  # - priority "{{ if eq .Status "firing" }}2{{ else }}0{{ end }}" on critical
  # - priority '0' (static) on warning
  # - retry: 1m and expire: 1h ONLY on critical receiver (not on warning)
  # - send_resolved: true on both Pushover receivers
  # - email-default receiver block byte-identical to pre-change
  # - inhibit_rules: 8 entries unchanged
  ```

  **Routing matrix** (per data-model.md and research.md Area 3):

  | Alert Severity | pushover-critical | pushover-warning | email-default | Expected |
  |---------------|-------------------|------------------|---------------|----------|
  | `critical` (7 rules) | ✅ match + continue | ❌ skip | ✅ catch-all | emergency push + email |
  | `warning` (11 rules) | ❌ skip | ✅ match + continue | ✅ catch-all | normal push + email |
  | (no severity) | ❌ skip | ❌ skip | ✅ catch-all | email only |

  **Traces to**: FR-001–FR-010, FR-015, SC-008, SC-010

  **Done-condition**:
  1. Rendered `alertmanager.yml` contains exactly 3 receivers (`email-default`, `pushover-critical`, `pushover-warning`)
  2. Rendered `alertmanager.yml` `route.routes` contains exactly 3 child route entries
  3. First two child routes have `continue: true`; third child route has no `continue` key and no matchers (catch-all)
  4. `pushover-critical` receiver has `priority:` field containing the Go template conditional (`{{ if eq .Status "firing" }}2{{ else }}0{{ end }}`)
  5. `pushover-critical` receiver has `retry:` and `expire:` fields; `pushover-warning` does NOT have `retry:` or `expire:`
  6. Both `pushover-critical` and `pushover-warning` have `send_resolved: true`
  7. Config passes `amtool check-config` (if Docker available) OR manual YAML structure inspection confirms valid Alertmanager syntax
  8. `email-default` receiver's `to:`, `headers.Subject`, `html:`, and `send_resolved:` fields are byte-identical to pre-change

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 2 (Foundational) ──────> Phase 3 (Core) ──────> Phase 4 (Validation)
  T001 ─┐ (parallel)             T004                   T005
  T002 ─┘                                               T006 ─┐ (parallel)
  T003 (after T001)                                     T007 ─┘
```

- **Phase 2** (Foundational): No external dependencies — start immediately
  - T001 and T002 are parallel-safe (different files)
  - T003 depends on T001 (`pushover_enabled` must be defined in defaults before assert can reference it)
- **Phase 3** (Core): Depends on T001 (variable names used in template) and T003 (validation gate must exist before template is deployed)
- **Phase 4** (Validation): Depends on all Phase 2 and Phase 3 tasks
  - T005 lints all 4 modified files — runs after all changes complete
  - T006 and T007 are parallel-safe (both validate T004's template — read-only, different rendering states)

### Within-Phase Task Dependencies

| Task | Depends On | Reason |
|------|------------|--------|
| T001 | — | No dependencies |
| T002 | — | No dependencies (different file from T001) |
| T003 | T001 | `when: pushover_enabled` references the variable defined in T001 |
| T004 | T001, T003 | Template uses variables from T001; validation gate (T003) must exist before template deploys |
| T005 | T001–T004 | Lints all 4 modified files — requires all changes complete |
| T006 | T004 | Validates disabled-state rendering of T004's template output |
| T007 | T004 | Validates enabled-state rendering of T004's template output |

### Parallel Opportunities

```bash
# Phase 2: Launch T001 and T002 in parallel
Task: "Add Pushover defaults to defaults/main.yml"       (T001)
Task: "Add vault reference comment to vars.yml"          (T002)
# Then T003 sequentially (after T001)

# Phase 4: Launch T006 and T007 in parallel
Task: "Verify disabled-state template rendering"         (T006)
Task: "Verify enabled-state template rendering"          (T007)
```

---

## Implementation Strategy

### MVP (All User Stories in a Single Pass)

Given the minimal scope (4 file modifications, 0 new files), all 5 user stories are delivered together:

1. Complete Phase 2 (T001–T003): Feature flag, vault docs, credential safety net
2. Complete Phase 3 (T004): Core template extension — all 5 user stories satisfied
3. **STOP and VALIDATE**: Run Phase 4 (T005–T007) — verify lint + both rendering states
4. Deploy to monitoring LXC (`ansible-playbook ansible/playbooks/monitoring.yml --ask-vault-pass`)
5. Run quickstart.md manual tests to verify SC-001–SC-005 and SC-009

### Incremental Option (extra confidence)

For additional risk mitigation, T004 can be deployed across two playbook runs:

1. Deploy T001–T003 only → verify monitoring stack runs identically with `pushover_enabled=false`
2. Deploy T004 → enable `pushover_enabled=true` → verify push delivery manually

### Rollback

If push notifications cause issues after deployment: set `pushover_enabled: false` in `ansible/group_vars/monitoring/vars.yml` and re-run the monitoring playbook. Alertmanager reloads its configuration in under 2 minutes and reverts to email-only. No container restart required.

---

## File Manifest

### Files MODIFIED (4)

| File | Task | Stories | Change |
|------|------|---------|--------|
| `ansible/roles/monitoring_stack/defaults/main.yml` | T001 | US4 | Append `pushover_enabled: false`, `pushover_retry_interval: "1m"`, `pushover_expire_duration: "1h"`, `pushover_grafana_url` |
| `ansible/group_vars/monitoring/vars.yml` | T002 | US4 | Insert vault reference comment for Pushover credentials after SMTP vault comment |
| `ansible/roles/monitoring_stack/tasks/main.yml` | T003 | US4 | Insert credential validation assert task before `Deploy Docker Compose stack` include |
| `ansible/roles/monitoring_stack/templates/alertmanager.yml.j2` | T004 | US1/US2/US3/US5 | Add conditional Pushover receivers and severity-based child routes inside `{% if pushover_enabled %}` blocks |

### Files CREATED (0)

None. Constitution IV (Code Economy) — all changes extend existing files in the `monitoring_stack` role. No new containers, processes, or infrastructure are introduced (C-003).

### Files UNCHANGED (verified)

| File | Reason |
|------|--------|
| `ansible/roles/monitoring_stack/templates/docker-compose.yml.j2` | No new containers (C-003) |
| `ansible/roles/monitoring_stack/files/prometheus/alerts/*.yml` | No alert rule changes (spec Out of Scope) |
| `ansible/roles/monitoring_stack/tasks/compose_stack.yml` | Alertmanager config deploy task already templates `alertmanager.yml.j2`; no new tasks needed |
| `ansible/roles/monitoring_stack/handlers/main.yml` | Existing `Restart monitoring stack` handler sufficient for Alertmanager config reload |
| `ansible/playbooks/monitoring.yml` | Already includes `monitoring_stack` role; no new plays or tasks |
| All `ansible/host_vars/*.yml` | No per-host changes — Pushover routing is global in Alertmanager configuration |
| `.github/workflows/*.yml` | No new CI paths or workflows needed (Constitution V, C-004) |

---

## Success Criteria Coverage

| SC | Verification Method | Task(s) |
|----|--------------------|---------|
| SC-001 | Manual: fire test critical alert via Alertmanager API → push arrives within 2 min | quickstart.md |
| SC-002 | Manual: wait 2 min after critical alert → repeat notification received | quickstart.md |
| SC-003 | Manual: fire test warning alert → normal-priority push arrives | quickstart.md |
| SC-004 | Manual: fire test alert → both push AND email arrive | quickstart.md |
| SC-005 | Manual: fire then resolve test alert → resolved push arrives | quickstart.md |
| SC-006 | Automated: T006 — disabled-state rendering shows zero diff from pre-feature | T006 |
| SC-007 | Automated: run playbook with `pushover_enabled=true` + no vault creds → assert fails with expected message | T003 done-condition |
| SC-008 | Automated: T006 + T007 — email config unchanged in both enabled and disabled states | T006, T007 |
| SC-009 | Manual: run monitoring playbook twice → second run shows no changes (idempotency) | post-deploy |
| SC-010 | Automated: T007 — routing matrix shows 7 critical → pushover-critical, 11 warning → pushover-warning, 18 → email | T007 |

SC-001–SC-005 and SC-009 require deployment to the monitoring LXC (192.168.1.214) and are validated manually using procedures in `quickstart.md`. SC-006–SC-008 and SC-010 are validated during Phase 4 without requiring deployment.

---

## Constitution Compliance

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Spec-Driven Workflow | ✅ PASS | All 7 tasks trace to FRs and user stories in spec.md. `tasks.md` lives at `specs/043-alerting-pushover/tasks.md`. Feature branch is `043-alerting-pushover`. |
| II | Secrets Policy | ✅ PASS | `pushover_user_key` and `pushover_api_token` in `vault.yml` only. `no_log: true` on assert task (T003). Template uses `{{ pushover_user_key }}` variable references — never plaintext. Vault comment (T002) documents the expectation without containing values. |
| III | Separation of Concerns | ✅ PASS | Zero Terraform changes. All 4 file modifications are Ansible configuration inside the existing monitoring LXC. |
| IV | Code Economy (YAGNI) | ✅ PASS | 0 new files. 4 file modifications. Two separate receivers (critical + warning) instead of one with complex dynamic priority logic — justified because each receiver has distinct config fields (`retry`/`expire` only on critical). No `info` route deployed (FR-016 is SHOULD, not MUST; no current alert rules use `info` severity). Feature flag justified by FR-011 (CI/CD compatibility). |
| V | Dual-Provisioning Parity | ✅ PASS | `ansible/playbooks/monitoring.yml` already runs from both CI (self-hosted runner) and developer laptop. No new CI workflows or runner-specific paths introduced. Vault accessible in both contexts per existing pattern. |

---

## Requirement Traceability

| Requirement | Task(s) | Done-Condition |
|-------------|---------|----------------|
| FR-001 (Pushover channel alongside email) | T004 | `pushover-critical` and `pushover-warning` receivers present in rendered `alertmanager.yml` |
| FR-002 (severity-based priority routing) | T004 | Critical route → `pushover-critical` (priority 2), warning route → `pushover-warning` (priority 0) |
| FR-003 (emergency retry 60s, expire 1h) | T001, T004 | `retry: {{ pushover_retry_interval }}` (1m) and `expire: {{ pushover_expire_duration }}` (1h) on critical receiver only |
| FR-004 (normal priority respects quiet hours) | T004 | `priority: '0'` on `pushover-warning` — Pushover app handles quiet hours natively |
| FR-005 (title + summary in notification body) | T004 | Title template with `[CRITICAL]/[WARNING]/[RESOLVED]` prefix + alertname; message uses `{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}` |
| FR-006 (send_resolved notifications) | T004 | `send_resolved: true` on both Pushover receivers |
| FR-007 (email delivery continues unchanged) | T004 | Catch-all `email-default` child route ensures all alerts reach email; email receiver block untouched |
| FR-008 (continue: true on Pushover routes) | T004 | `continue: true` on both `pushover-critical` and `pushover-warning` child routes |
| FR-009 (email config unchanged) | T004 | `email-default` receiver's `to:`, `headers`, `html:`, `send_resolved:`, grouping, and timing all untouched |
| FR-010 (no-severity falls to email) | T004 | Alerts without severity label match neither Pushover route → fall through to catch-all `email-default` |
| FR-011 (disabled by default) | T001 | `pushover_enabled: false` in `defaults/main.yml` |
| FR-012 (credential validation when enabled) | T003 | Assert task with actionable `fail_msg` gated by `when: pushover_enabled` |
| FR-013 (credentials in vault only) | T002, T003 | Vault reference comment documents expectation; `no_log: true` on assert; template uses variable references only |
| FR-014 (role defaults with override capability) | T001 | Three variables in `defaults/main.yml` — lowest precedence, overridable at any level |
| FR-015 (severity→priority mapping: critical=2, warning=0) | T004 | Critical receiver: Go template conditional `2`/`0`; warning receiver: static `0` |
| FR-016 (info severity future-compatible) | T004 | Routing structure uses severity label matching — naturally extends to third severity without structural rework; no info route deployed (SHOULD, not MUST) |
| FR-017 (all 18 alert rules routed by severity label) | T004 | Routes match on `severity` label; all 18 existing rules have `severity: critical` or `severity: warning` labels (A-004) |
