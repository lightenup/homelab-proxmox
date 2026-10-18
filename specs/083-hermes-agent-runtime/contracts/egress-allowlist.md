# Contract: the agent's network reach

This applies to packets whose source is the agent container's fixed address (`hermes_agent_ip`).
Open WebUI and SearXNG are unaffected.

| Destination | Reachable | Purpose |
|---|---|---|
| `agent` compose network | yes | SearXNG, replies to Open WebUI |
| public resolver :53 (LXC `resolv.conf`, 1.1.1.1) | yes, as public internet | DNS. No rule needed, and no AdGuard in this estate (Q-L6) |
| `llm_router_ip:llm_router_port` | yes | model gateway |
| each `hermes_mcp_servers` host:port | yes | tool services |
| `reverse_proxy_ip:443` | yes | ntfy (and, accepted, every Caddy vhost behind its own auth) |
| any other RFC 1918, 100.64/10 (tailnet) or 169.254/16 address | **no** | hypervisor, NAS, router, other services |
| the Hermes LXC itself (sshd, node_exporter…) | **no** | |
| public internet | yes | GitHub, Hugging Face, web |

Guarantees:
- The rules are deployment configuration, applied in the LXC's network namespace. The agent has no
  `NET_ADMIN` and cannot alter them.
- They are re-applied on every deploy and on every Docker (re)start.
- Every deploy probes from inside the agent container: each "yes" row (except the internet) must
  connect and sample "no" rows must fail. Otherwise the deploy fails (SC-009).
- A new tool service extends the allowlist through `hermes_mcp_servers` only.
