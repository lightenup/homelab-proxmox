output "ansible_inventory" {
  value = {
    services = {
      "eurooffice" = module.eurooffice_lxc.ipv4
    }
  }
}
