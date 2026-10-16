output "ansible_inventory" {
  value = {
    services = {
      "ntfy" = module.ntfy_lxc.ipv4
    }
  }
}
