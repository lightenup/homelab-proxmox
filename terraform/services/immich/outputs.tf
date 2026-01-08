output "ansible_inventory" {
  value = {
    services = {
      immich = module.immich_lxc.ipv4
    }
  }
}
