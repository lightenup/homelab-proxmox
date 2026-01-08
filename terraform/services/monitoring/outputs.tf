output "ansible_inventory" {
  value = {
    services = {
      monitoring = module.monitoring_lxc.ipv4
    }
  }
}
