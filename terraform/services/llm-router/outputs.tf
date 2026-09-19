output "ansible_inventory" {
  value = {
    services = {
      "llm-router" = module.llm_router_lxc.ipv4
    }
  }
}
