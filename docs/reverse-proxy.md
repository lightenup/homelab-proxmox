# Internal Reverse Proxy (Caddy)

## Overview

This project uses [Caddy](https://caddyserver.com/) as an internal reverse proxy running on a dedicated LXC container (`reverse_proxy` / `192.168.1.211`).

The proxy serves as a single entry point for internal services, handling:
-   Simple HTTP routing (currently).
-   Future SSL termination (if needed).
-   Centralized logging.

## Architecture

-   **Host**: `reverse_proxy` (LXC)
-   **Software**: Caddy v2 (installed via official Apt repository)
-   **Configuration Mode**: HTTP-only (`auto_https off`)
-   **Config Structure**: Modular
    -   Main Config: `/etc/caddy/Caddyfile`
    -   Site Configs: `/etc/caddy/conf.d/*.caddy`

## Ansible Role: `reverse_proxy`

The configuration is managed entirely via Ansible.

### Structure

-   `tasks/main.yml`: Installs Caddy, creates directories, deploys the main Caddyfile, and deploys individual site configurations.
-   `templates/Caddyfile.j2`: The global configuration template.
-   `templates/*.caddy.j2`: Individual service configuration templates (e.g., `immich.caddy.j2`).
-   `handlers/main.yml`: Handles restarting/reloading Caddy when configs change.

## How to Add a New Service

To proxy a new service (e.g., `homeassistant`), follow these steps:

1.  **Create a Template**:
    Create a new template file in `ansible/roles/reverse_proxy/templates/service_name.caddy.j2`.

    ```caddy
    # ansible/roles/reverse_proxy/templates/homeassistant.caddy.j2
    http://homeassistant.local {
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
-   **Validate Config**: `caddy validate --config /etc/caddy/Caddyfile`
