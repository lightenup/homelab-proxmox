# Quickstart: Automated Testing Refactor

This quickstart is for contributors implementing `027-automated-testing-refactor`.

## Local validation (intended)

These are the intended checks to be easy to run locally during implementation.

- Terraform:
  - `terraform fmt -check -recursive terraform/`
  - `terraform validate` (module-by-module)
  - `terraform test` (where feasible without requiring live Proxmox access)

- Ansible:
  - `ansible-lint` (where configured)
  - `ansible-playbook --syntax-check ...`
  - `molecule test` (starting with one service role)

- Python automation runner:
  - `PYTHONPATH=python/src .venv/bin/python -m pytest -c python/pytest.ini` (unit + golden + workflow contract tests)
  - (Optional) Use `uv` for fast, reproducible installs (CI uses this):
    - `uv venv --python 3.11`
    - `uv pip sync --python .venv/bin/python --require-hashes python/requirements-test.lock.txt`
    - Nightly toolchain: `uv pip sync --python .venv/bin/python --require-hashes python/requirements-nightly.lock.txt`
    - Regenerate lockfiles: `bash scripts/ci/uv-lock.sh`
  - `mutmut run --paths-to-mutate python/src/homelab_proxmox_orchestrator --tests-dir python/tests --runner "env PYTHONPATH=python/src python -m pytest -q -c python/pytest.ini"` (optional locally; required in nightly CI)

- Workflow YAML (when editing workflows):
  - `act -l`
  - `act workflow_dispatch -W .github/workflows/lxc-deploy-lab.yml -j plan --dryrun -e /tmp/act-lxc-deploy-lab.json`
  - `act workflow_dispatch -W .github/workflows/lxc-apply-prod.yml --dryrun -e /tmp/act-lxc-apply-prod.json`

## CI validation strategy (intended)

- Pull requests (fast): format/validate + unit/golden tests.
- Nightly (deeper): mutation testing + broader infra/role checks.

Pointers:
- PR workflow: `.github/workflows/ci.yml`
- Nightly workflow: `.github/workflows/nightly-deeper-verification.yml`
- CI scripts: `scripts/ci/python-tests.sh`, `scripts/ci/terraform-validate.sh`

## Operator workflow validation (intended)

Some changes (especially those affecting remote executor behavior or evidence pack layout) must be validated by running real GitHub Actions workflows against LAB.

Minimum recommended validation run:
- Promote/deploy a single service to LAB and confirm:
  - evidence packs are produced
  - run summary is bounded and actionable
  - no secrets appear in logs/summaries
