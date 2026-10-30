# Intentionally empty (067).
#
# The ten combined-root `module "*_lxc"` blocks that used to live here were replaced by the
# per-service roots under services/<svc>/, each with its own state at
# /var/lib/homelab-proxmox/state/<env>/<svc>/terraform.tfstate. The combined root never had a
# state on the PVE host, so there is nothing to remove from state.
#
# The provider and variable declarations stay so `terraform validate` on this directory and the
# shared tfvars files keep working.
