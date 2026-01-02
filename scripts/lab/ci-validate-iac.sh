#!/usr/bin/env bash
set -euo pipefail

failures=()

check_ansible_defaults() {
  local cfg="ansible/ansible.cfg"
  if ! grep -Eq '^remote_user *= *ci' "$cfg"; then
    failures+=("ansible remote_user must be ci in $cfg")
  fi
  if ! grep -Eq '^become_flags *= *-n' "$cfg"; then
    failures+=("ansible become_flags must include -n in $cfg")
  fi
}

check_ansible_root_usage() {
  # Disallow remote_user: root except in bootstrap playbook
  local disallowed
  disallowed=$(grep -R "remote_user: root" ansible/playbooks || true)
  if [[ -n "$disallowed" ]] && ! grep -q "ansible/playbooks/bootstrap.yml" <<<"$disallowed"; then
    failures+=("remote_user: root found outside bootstrap playbook")
  fi
}

check_terraform_token() {
  local hits
  hits=$(grep -R "root@pam" terraform --include "*.tf" --include "*.tfvars" --include "*.tfvars.json" --include "*.tfvars.example" 2>/dev/null || true)
  if [[ -n "$hits" ]]; then
    failures+=("Terraform tokens must not use root@pam")
  fi
}

main() {
  check_ansible_defaults
  check_ansible_root_usage
  check_terraform_token

  if ((${#failures[@]})); then
    printf "CI IaC posture check failed:\n"
    printf ' - %s\n' "${failures[@]}"
    exit 1
  fi

  echo "CI IaC posture check passed"
}

main "$@"
