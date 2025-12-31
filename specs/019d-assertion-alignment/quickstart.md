# Quickstart: Assertion Alignment

## How to Write an Assertion

1. **Identify the Check ID**: Refer to the Check Catalog or create a new one (e.g., `NET-001`).
2. **Create a Block**: Wrap the check logic and assertion in a `block`.
3. **Register Result**: Use `ansible.builtin.assert` and register the result.
4. **Accumulate Evidence**: Use `set_fact` in the `always` section of the block to append to `assertion_results`.

### Example

```yaml
- name: "[NET-001] Verify DNS resolution"
  block:
    - name: "Check DNS resolution"
      ansible.builtin.command: getent hosts deb.debian.org
      register: dns_check
      ignore_errors: true

    - name: "Assert DNS resolution success"
      ansible.builtin.assert:
        that:
          - dns_check.rc == 0
        fail_msg: "[NET-001] DNS resolution failed. Remediation: Check /etc/resolv.conf."
        success_msg: "[NET-001] DNS resolution OK."
  always:
    - name: "Record assertion result"
      ansible.builtin.set_fact:
        assertion_results: "{{ assertion_results | default([]) + [{
          'check_id': 'NET-001',
          'title': 'Verify DNS resolution',
          'result': (dns_check.rc == 0) | ternary('PASS', 'FAIL'),
          'reason': dns_check.stderr | default('DNS lookup failed'),
          'remediation': 'Check /etc/resolv.conf'
        }] }}"
```

## How to Generate the Report

Ensure the playbook ends with a task to write the report:

```yaml
- name: "Generate Assertion Report"
  ansible.builtin.copy:
    content: |
      {{
        {
          'run_id': run_id | default('manual'),
          'profile_id': profile_id | default('default'),
          'phase': 'bootstrap',
          'timestamp': ansible_date_time.iso8601,
          'assertions': assertion_results | default([])
        } | to_nice_json
      }}
    dest: "{{ evidence_dir }}/reports/assertions.bootstrap.json"
  delegate_to: localhost
```
