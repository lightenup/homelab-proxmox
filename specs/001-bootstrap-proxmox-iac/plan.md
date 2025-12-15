# Plan: Iteration 1 - Cleanup & Correctness

## Proposed Changes

### 1. Terraform Variables Refactor
We will introduce new variables in `variables.tf` to abstract environment-specific settings:
- `ssh_public_keys` (list(string)): The public key content to inject into containers.
- `network_gateway` (string): The default gateway (e.g., `192.168.1.1`).
- `service_ips` (map(string)): A map of service names to their CIDR IPs (e.g., `{ immich = "192.168.1.213/24" }`).

### 2. Module Updates (`modules/lxc_service`)
- Add `ssh_public_keys` variable (type `string` - module receives joined string or list, but resource needs string. We will pass list to module and join inside, or pass string. Decision: Pass `string` to module, root converts list to string).x_lxc` resource.
- Add `onboot` variable (default `true`) and pass it to the resource.
- Add `unprivileged` variable (default `true`) and pass it to the resource.
- Ensure `start` is set to `true` so containers boot immediately.

### 3. Main Configuration Updates (`main.tf`)
- Update all module calls to use `var.service_ips["service_name"]` instead of hardcoded strings.
- Pass `var.network_gateway` and `var.ssh_public_keys` to all modules.

### 4. Documentation & Examples
- Create `terraform.tfvars.example` showing the correct structure for the `192.168.1.x` network.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **IP Collisions** | We are manually assigning static IPs in the `.200+` range (210-213) to avoid DHCP conflicts on the LAN. |
| **SSH Key Format** | Terraform can be picky about newlines. We will document that the variable should be a single line or properly escaped string. |
| **Destructive Re-creation** | Changing IPs or `unprivileged` status will force resource recreation. This is acceptable for Iteration 1 as we are bootstrapping. |

## Validation Steps
1.  **Plan Check**: Run `terraform plan` and verify it proposes replacing the existing (wrong IP) containers with new ones on the correct subnet.
2.  **Apply**: Run `terraform apply`.
3.  **Ping Check**: `ping 192.168.1.210` (AdGuard), etc.
4.  **SSH Check**: `ssh root@192.168.1.210` should succeed without a password prompt.
5.  **Reboot Check**: Reboot one container (`pct reboot <vmid>`) and ensure it comes back up.
