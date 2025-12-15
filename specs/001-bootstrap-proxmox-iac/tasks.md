# Tasks: Iteration 1 - Cleanup & Correctness

**Feature**: Bootstrap Proxmox IaC (Cleanup & Correctness)
**Status**: Approved
**Spec**: [specs/001-bootstrap-proxmox-iac/spec.md](specs/001-bootstrap-proxmox-iac/spec.md)

## Phase 1: Setup
*Project initialization and configuration preparation.*

- [x] T001 Create [terraform/terraform.tfvars.example](terraform/terraform.tfvars.example) with 192.168.1.x network values and SSH key placeholder
- [x] T002 Verify or create local `terraform/prod.tfvars` (gitignored) using values from example

## Phase 2: Foundational
*Module updates required for the refactor.*

- [x] T003 Update [terraform/modules/lxc_service/variables.tf](terraform/modules/lxc_service/variables.tf) to add `ssh_public_keys`, `onboot`, and `unprivileged`
- [x] T004 Update [terraform/modules/lxc_service/main.tf](terraform/modules/lxc_service/main.tf) to map new variables and enable `nesting = true`

## Phase 3: User Story 1 - Refactor Network & Access
*Implement dynamic IP assignment and SSH key injection.*

- [x] T005 [US1] Update [terraform/variables.tf](terraform/variables.tf) to add `ssh_public_keys` (list), `network_gateway`, and `service_ips` (map)
- [x] T006 [US1] Update [terraform/main.tf](terraform/main.tf) to use `var.service_ips`, `var.network_gateway` and pass joined SSH keys

## Phase 4: Verification & Polish
*Validate changes and apply.*

- [x] T007 Run `terraform fmt -recursive` and `terraform validate` in [terraform/](terraform/)
- [x] T008 Run `terraform plan` and review resource replacements (STOP POINT: Ensure IPs match 192.168.1.x)
- [x] T009 Run `terraform apply` to provision updated containers
- [x] T010 Verify SSH access to new container IPs (e.g. `ssh root@192.168.1.210`)

## Dependencies
- US1 depends on Phase 2 (Module Updates)

## Implementation Strategy
- Update module first to expose necessary variables.
- Update root config to pass values down.
- Verify plan carefully as this involves resource recreation.
