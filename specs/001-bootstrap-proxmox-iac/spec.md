# Spec: Iteration 1 - Cleanup & Correctness

## Goal
Refactor the existing Terraform codebase to be usable on the current physical network (192.168.1.x) and prepare it for Ansible configuration. This involves moving hardcoded values to variables, fixing the network topology to match reality, and ensuring SSH access is correctly provisioned.

## Scope
- **Terraform Root**: `main.tf`, `variables.tf`, `outputs.tf`.
- **Terraform Module**: `modules/lxc_service`.
- **Configuration**: `terraform.tfvars.example` (and local `prod.tfvars`).

## Non-Goals
- Implementing the "Services VLAN" (192.168.20.x). This is deferred.
- Setting up GitHub Actions/CI.
- Writing Ansible playbooks (this spec only enables them).

## Current State Summary
- **Network Mismatch**: `main.tf` defines containers on `192.168.20.0/24` with gateway `192.168.20.1`. The actual network is `192.168.1.0/24` with gateway `192.168.1.1`.
- **Hardcoded Values**: IPs are embedded in resource blocks.
- **Missing Access**: The `lxc_service` module does not inject SSH public keys, making Ansible automation impossible without manual intervention.
- **Missing Defaults**: Containers are not set to start on boot.

## Constraints
- **Single Node**: All resources target a single Proxmox node.
- **Laptop Runner**: Terraform is executed locally.
- **No Secrets**: No sensitive data (passwords, keys) in git.
- **Provider**: Must use `telmate/proxmox`.

## Acceptance Criteria
1.  **Configurability**: Service IPs and Gateway can be changed via `terraform.tfvars` without editing `main.tf`.
2.  **Connectivity**: Applied containers are reachable on the `192.168.1.x` network.
3.  **Access**: `root` user in containers has the correct SSH public key authorized immediately after provisioning.
4.  **Resilience**: Containers are configured to start on boot (`onboot = true`) and have `nesting = true` enabled (for NFS/FUSE support).
5.  **Clean Apply**: `terraform apply` completes with no errors against the current Proxmox host.

## Clarifications
### Session 2025-12-15
- Q: How to handle NFS/FUSE support in unprivileged containers? → A: Enable `nesting = true` feature for all containers.
- Q: What data type should `ssh_public_keys` use? → A: `list(string)` (module joins them with newlines).
