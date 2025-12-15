variable "proxmox_api_url" {
  type        = string
  description = "Proxmox API URL, e.g. https://proxmox.example:8006/api2/json"
}

variable "proxmox_api_token_id" {
  type        = string
  description = "Proxmox API token ID, e.g. terraform@pve!token"
}

variable "proxmox_api_token_secret" {
  type        = string
  description = "Proxmox API token secret value"
  sensitive   = true
}

variable "proxmox_node" {
  type        = string
  description = "Name of the Proxmox node to place LXCs on"
}

variable "lxc_template" {
  type        = string
  description = "LXC template path, e.g. local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
}

variable "storage_pool" {
  type        = string
  description = "Name of the storage pool for rootfs"
  default     = "local-lvm"
}

variable "services_bridge" {
  type        = string
  description = "Bridge name for services network"
  default     = "vmbr0"
}

variable "network_gateway" {
  type        = string
  description = "Default gateway for the network"
}

variable "service_ips" {
  type        = map(string)
  description = "Map of service names to their IPs (CIDR)"
}

variable "ssh_public_keys" {
  type        = list(string)
  description = "List of SSH public keys to inject into containers"
}
