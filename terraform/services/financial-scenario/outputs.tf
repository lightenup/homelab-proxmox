output "ansible_inventory" {
  value = {
    services = {
      "financial-scenario" = module.financial_scenario_lxc.ipv4
    }
  }
}
