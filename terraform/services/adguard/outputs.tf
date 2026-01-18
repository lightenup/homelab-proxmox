output "ansible_inventory" {
  value = {
    services = {
      adguard = module.adguard_lxc.ipv4
    }
  }
}
