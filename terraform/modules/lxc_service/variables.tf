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

variable "ssh_public_keys" {
  type        = list(string)
  description = "List of SSH public keys to inject into the container"
}

variable "onboot" {
  type        = bool
  description = "Whether to start the container on boot"
  default     = true
}

variable "unprivileged" {
  type        = bool
  description = "Whether the container is unprivileged"
  default     = true
}

variable "vmid" {
  type        = number
  description = "The VMID to assign to the container. Set to 0 for auto-assignment."
  default     = 0
}
