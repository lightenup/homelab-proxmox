output "ansible_inventory" {
  value = {
    services = {
      reverse_proxy = module.reverse_proxy_lxc.ipv4
    }
  }
}
