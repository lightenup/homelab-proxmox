# Plan: Internal Reverse Proxy Baseline

## Phase 1: Ansible Role Development

- [ ] Create `ansible/roles/reverse_proxy` directory structure.
- [ ] Implement `tasks/main.yml` to install Caddy (add official Caddy repo, install package).
- [ ] Create `templates/Caddyfile.j2` with basic reverse proxy configuration.
- [ ] Implement `handlers/main.yml` to restart Caddy on config change.
- [ ] Add tasks to deploy `Caddyfile` and enable/start Caddy service.

## Phase 2: Integration

- [ ] Update `ansible/playbooks/services.yml` to include `reverse_proxy` role for the `reverse_proxy` host group (or specific host).
- [ ] Define necessary variables (e.g., `immich_ip`, `immich_port`) in `ansible/group_vars/services/vars.yml` or role defaults.

## Phase 3: Verification

- [ ] Run playbook to deploy Caddy.
- [ ] Verify Caddy is running (`systemctl status caddy`).
- [ ] Verify HTTP access to `http://192.168.1.211/` proxies to Immich.
- [ ] Verify headers are correctly forwarded (check logs or inspect request).
- [ ] Verify idempotency (run playbook again).
- [ ] Verify persistence (reboot LXC).

## Phase 4: Documentation

- [ ] Create `docs/reverse-proxy.md` documenting the setup, Caddyfile structure, and update procedure.
