# Tasks: 046-financial-scenario-deploy

## Phase 1 — Terraform

- [X] T001: Add `module "financial_scenario_lxc"` to `terraform/main.tf`
- [X] T002: Add `financial-scenario` IP to `terraform/environments/lab.tfvars` (192.168.20.218/24)
- [X] T003: Add `financial-scenario` IP to `terraform/environments/lab.tfvars.template` (192.168.1.217/24)
- [X] T004: Add `financial-scenario` IP to `terraform/environments/prod.tfvars.template` (192.168.1.217/24)

## Phase 2 — Ansible Role

- [X] T005: Create `ansible/roles/financial_scenario/defaults/main.yml`
- [X] T006: Create `ansible/roles/financial_scenario/tasks/preflight.yml`
- [X] T007: Create `ansible/roles/financial_scenario/tasks/main.yml`
- [X] T008: Create `ansible/roles/financial_scenario/templates/docker-compose.yml.j2`
- [X] T009: Create `ansible/roles/financial_scenario/handlers/main.yml`
- [X] T010: Create `ansible/playbooks/financial_scenario.yml`

## Phase 3 — Inventory & Vars

- [X] T011: Add `financial_scenario_*` vars to `ansible/group_vars/services/vars.yml`
- [X] T012: Add `financial-scenario` host to `ansible/inventories/prod/hosts.yml`
- [X] T013: Create `ansible/host_vars/financial-scenario.yml` with healthcheck_url and monitoring_contract

## Phase 4 — Pipeline Registration

- [X] T014: Add `financial-scenario` to service choices in `.github/workflows/lxc-deploy-lab.yml`
- [X] T015: Add `financial-scenario` entry to `scripts/lab/service-scope-allowlist.json`

## Phase 5 — Monitoring Infrastructure

- [X] T016: Add `http_2xx` module to `ansible/roles/monitoring_stack/templates/blackbox.yml.j2`
- [X] T017: Add `blackbox-http` job (liveness_targets from contracts) to `ansible/roles/monitoring_stack/templates/prometheus.yml.j2`
