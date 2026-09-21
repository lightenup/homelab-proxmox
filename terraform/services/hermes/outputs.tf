output "ansible_inventory" {
  value = {
    services = {
      "hermes" = module.hermes_lxc.ipv4
    }
  }
}
