output "ansible_inventory" {
  value = {
    services = {
      immich        = module.immich_lxc.ipv4
      homeassistant = module.homeassistant_lxc.ipv4
      reverse_proxy = module.reverse_proxy_lxc.ipv4
      monitoring    = module.monitoring_lxc.ipv4
      jellyfin      = module.jellyfin_lxc.ipv4
    }
  }
}
