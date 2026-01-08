output "ansible_inventory" {
  value = {
    services = {
      homeassistant = module.homeassistant_lxc.ipv4
    }
  }
}
