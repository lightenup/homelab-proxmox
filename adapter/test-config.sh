# test-config.sh — Project-specific test and lint commands
#
# This file is sourced by speckit-droid-adapter during the build loop.
# Customize the commands below for your project's toolchain.
#
# Both functions should return 0 on success, non-zero on failure.
# Their stdout/stderr is captured and fed back to the implement stage
# on failure.

# Run the project's test suite
# Examples:
#   npm test
#   pytest -v
#   go test ./...
#   cargo test
run_project_tests() {
  if [[ -x "scripts/ci/python-tests.sh" ]]; then
    scripts/ci/python-tests.sh 2>&1
    return $?
  fi

  if [[ -d "python" ]]; then
    PYTHON_BIN="${PYTHON_BIN:-python3}"
    export PYTHONPATH="${PYTHONPATH:-python/src}"
    "$PYTHON_BIN" -m pytest -c python/pytest.ini --cov-fail-under=80 2>&1
    return $?
  fi

  echo "⚠ Python test suite not found (expected scripts/ci/python-tests.sh or python/)"
  return 0
}

# Run the project's linter
# Examples:
#   npm run lint
#   ruff check .
#   golangci-lint run
#   cargo clippy
run_project_lint() {
  local failed=0

  if [[ -x "scripts/ci/terraform-validate.sh" ]]; then
    scripts/ci/terraform-validate.sh 2>&1 || failed=1
  elif [[ -d "terraform" ]]; then
    terraform fmt -check -recursive terraform/ 2>&1 || failed=1
    terraform -chdir=terraform init -backend=false -input=false 2>&1 || failed=1
    terraform -chdir=terraform validate 2>&1 || failed=1
  fi

  if [[ -d "ansible" ]]; then
    if command -v ansible-lint >/dev/null 2>&1; then
      ANSIBLE_ROLES_PATH="ansible/roles" ansible-lint -c .ansible-lint ansible 2>&1 || failed=1
    else
      echo "ℹ ansible-lint not installed; skipping Ansible lint"
    fi
  fi

  return $failed
}
