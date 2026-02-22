output "ansible_inventory" {
  value = {
    services = {
      nextcloud = module.nextcloud_lxc.ipv4
    }
  }
}
