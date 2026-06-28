output "ansible_inventory" {
  value = {
    services = {
      "market-model" = module.market_model_lxc.ipv4
    }
  }
}
