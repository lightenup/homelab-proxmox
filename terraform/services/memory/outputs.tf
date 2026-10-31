output "ansible_inventory" {
  value = {
    services = {
      "memory" = module.memory_lxc.ipv4
    }
  }
}
