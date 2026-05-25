# Internal Reverse Proxy (Caddy)

## Overview

This project uses [Caddy](https://caddyserver.com/) as an internal reverse proxy running on a dedicated LXC container (`reverse_proxy` / `192.168.1.211`).

The proxy serves as a single entry point for internal services, handling:
-   HTTPS termination with valid Let's Encrypt certificates.
-   Automated certificate issuance and renewal via DNS-01 ACME challenges.
-   Centralized logging.

## Architecture

-   **Host**: `reverse_proxy` (LXC)
-   **Software**: Custom Caddy v2 binary built with `xcaddy` (includes `caddy-dns/domainnameshop` module)
-   **Domain**: `*.hus-sky.no` (Domeneshop)
-   **TLS**: Automatic via DNS-01 challenges against the Domeneshop API
-   **Config Structure**: Modular
    -   Main Config: `/etc/caddy/Caddyfile` (global ACME settings)
    -   Site Configs: `/etc/caddy/conf.d/*.caddy`
    -   Secrets: `/etc/caddy/domeneshop.env` (systemd EnvironmentFile, mode 0600)

## Ansible Role: `reverse_proxy`

The configuration is managed entirely via Ansible.

### Structure

-   `tasks/main.yml`: Installs Caddy, builds custom binary with xcaddy, deploys configs, manages systemd overrides.
-   `defaults/main.yml`: DNS provider, plugin list, domain settings.
-   `templates/Caddyfile.j2`: Global configuration (ACME DNS settings).
-   `templates/*.caddy.j2`: Individual service site blocks (e.g., `immich.caddy.j2`).
-   `templates/domeneshop.env.j2`: API credentials for DNS-01 challenges.
-   `templates/caddy-domeneshop.conf.j2`: Systemd drop-in override for secrets injection.
-   `handlers/main.yml`: Handles daemon-reload and Caddy restart when configs change.

### Secrets

Domeneshop API credentials are stored in Ansible vault (`group_vars/services/vault.yml`) and injected at runtime via a systemd EnvironmentFile. They are never written to the Caddyfile — Caddy reads them via `{$DOMENESHOP_API_TOKEN}` and `{$DOMENESHOP_API_SECRET}` parse-time substitution.

## How to Add a New Service

To proxy a new service (e.g., `homeassistant`), follow these steps:

1.  **Create a Template**:
    Create a new template file in `ansible/roles/reverse_proxy/templates/service_name.caddy.j2`.

    ```caddy
    # ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2
    homeassistant.hus-sky.no {
        reverse_proxy {{ homeassistant_ip }}:{{ homeassistant_port }}
    }
    ```

2.  **Define Variables**:
    Ensure the upstream IP and port are defined in `ansible/group_vars/services/vars.yml` (or similar).

3.  **Add Task**:
    Add a task to `ansible/roles/reverse_proxy/tasks/main.yml` to deploy the new template.

    ```yaml
    - name: Deploy Home Assistant Caddy configuration
      ansible.builtin.template:
        src: homeassistant.caddy.j2
        dest: "{{ caddy_conf_dir }}/homeassistant.caddy"
        owner: caddy
        group: caddy
        mode: '0644'
      notify: Restart caddy
    ```

4.  **Deploy**:
    Run the services playbook.

    ```bash
    ansible-playbook ansible/playbooks/services.yml -i ansible/inventories/generated/hosts.yml
    ```

## Troubleshooting

-   **Check Status**: `systemctl status caddy`
-   **View Logs**: `journalctl -u caddy -f`
-   **Validate Config**: `DOMENESHOP_API_TOKEN=x DOMENESHOP_API_SECRET=x caddy validate --config /etc/caddy/Caddyfile` (env vars required for parse-time substitution)
-   **Check Certs**: `caddy list-modules 2>/dev/null | grep domainnameshop` (verify DNS module loaded)
-   **Cert Status**: Check `/var/lib/caddy/.local/share/caddy/certificates/` or Caddy logs for issuance

## How to Remove a Service

To remove a service from the reverse proxy:

1. Delete the service template in `ansible/roles/reverse_proxy/templates/<service>.caddy.j2`.
2. Remove the corresponding task from `ansible/roles/reverse_proxy/tasks/main.yml`.
3. Run the services playbook to apply changes.
4. Confirm the service no longer appears in proxy routes.
