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

variable "mountpoints" {
  description = "List of mount points for the container"
  type = list(object({
    mp     = string
    size   = string
    slot   = number
    key    = string
    storage = string
    volume = string
  }))
  default = []
}

variable "ssh_public_keys" {
  type        = string
  description = "SSH public keys to inject into the LXC"
  default     = null
}
