# Ansible Deprecation Cleanup — Feature 020 (US3)

Date: 2026-01-01
Scope: roles/assertion_utils generate_report uses ansible_facts['date_time']['iso8601'] to avoid injected fact deprecation. No templates in role.
Result: Rebuild run lab-20260101-084955 completed with zero Ansible deprecation warnings (T017 PASS).
