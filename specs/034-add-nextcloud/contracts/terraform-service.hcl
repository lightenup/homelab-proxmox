# Contract: Nextcloud Terraform Service Module
#
# This contract defines the expected interface for the Nextcloud LXC
# provisioned via Terraform, following the existing lxc_service module pattern.
#
# Traces to: FR-018 (dedicated LXC), FR-015 (auto-start), FR-014 (NFS mount)

# --- Input Contract ---
# These values are passed via service_ips and service_mountpoints in tfvars.

# service_ips["nextcloud"] = "192.168.20.216/24"
#
# service_mountpoints = {
#   nextcloud = {
#     data = {
#       mp     = "/mnt/nextcloud"
#       volume = "/mnt/nas/homelab_nextcloud"
#     }
#   }
# }

# --- Module Instantiation Contract ---
# module "nextcloud_lxc" {
#   source = "./modules/lxc_service"
#
#   name         = "nextcloud-lxc"
#   hostname     = "nextcloud"
#   cores        = 4
#   memory       = 4096
#   disk_gb      = 32
#
#   # NFS feature mount for host-side bind mount
#   features_mount = "nfs"
#
#   # Bind mount from host NFS to container
#   mountpoints = values(lookup(var.service_mountpoints, "nextcloud", {}))
#
#   # Standard pass-through variables
#   node, ostemplate, storage_pool, bridge, ip, gateway,
#   nameserver, searchdomain, ssh_public_keys
# }

# --- Output Contract ---
# output "ansible_inventory" {
#   value = {
#     services = {
#       nextcloud = module.nextcloud_lxc.ipv4
#     }
#   }
# }

# --- Sizing Rationale ---
# 4 cores:  Nextcloud + MariaDB + Redis + built-in CODE editor
# 4096 MB:  PHP processes (1GB limit each) + MariaDB buffer pool + Redis + OS
# 32 GB:    OS (~2GB) + Docker images (~5GB) + MariaDB data (~2GB) + headroom
#           User data is on NAS, not local disk.
