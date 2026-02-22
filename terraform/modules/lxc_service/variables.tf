variable "name" {
  type = string
}

variable "hostname" {
  type = string
}

variable "node" {
  type = string
}

variable "ostemplate" {
  type = string
}

variable "storage_pool" {
  type = string
}

variable "cores" {
  type = number
}

variable "memory" {
  type = number
}

variable "disk_gb" {
  type = number
}

variable "bridge" {
  type = string
}

variable "ip" {
  type        = string
  description = "IPv4 address in CIDR notation, e.g. 192.168.20.10/24"
}

variable "gateway" {
  type        = string
  description = "Default gateway for this container, e.g. 192.168.20.1"
}

variable "nameserver" {
  type        = string
  description = "DNS nameserver(s) as a space-separated string (e.g. '192.168.1.210 1.1.1.1'). If null, provider defaults apply."
  default     = null
}

variable "searchdomain" {
  type        = string
  description = "DNS search domain (e.g. 'home.arpa'). If null, provider defaults apply."
  default     = null
}

variable "mountpoints" {
  description = "List of mount points for the container"
  type = list(object({
    mp       = string
    volume   = string
    size     = optional(string)
    slot     = optional(number)
    key      = optional(string)
    storage  = optional(string)
    readonly = optional(bool)
  }))
  default = []
}

variable "ssh_public_keys" {
  type        = string
  description = "SSH public keys to inject into the LXC"
  default     = null
}

variable "features_mount" {
  type        = string
  description = "Proxmox LXC feature mount types to allow inside the container (e.g. 'nfs', 'nfs;cifs'). Empty string means default/none."
  default     = ""
}
