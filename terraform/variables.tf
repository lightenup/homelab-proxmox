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

variable "ssh_public_keys" {
  type        = list(string)
  description = "SSH public keys to inject into the LXC"
}

variable "network_gateway" {
  type        = string
  description = "Default gateway for the LXC network"
  default     = "192.168.20.1"
}

variable "service_ips" {
  type        = map(string)
  description = "Map of service names to IP addresses (CIDR format)"
}

variable "nameserver" {
  type        = string
  description = "LXC DNS nameserver(s) as a space-separated string (e.g. '192.168.1.210 1.1.1.1'). If null, provider defaults apply."
  default     = null
}

variable "searchdomain" {
  type        = string
  description = "LXC DNS search domain (e.g. 'home.arpa'). If null, provider defaults apply."
  default     = null
}

variable "service_mountpoints" {
  type = map(map(object({
    mp      = string
    volume  = string
    size    = optional(string)
    slot    = optional(number)
    key     = optional(string)
    storage = optional(string)
  })))
  description = "Per-service bind mounts (host path in volume, container path in mp). Keys under service name."
  default     = {}
}
