# Immich Maintenance Guide

## Updating Immich

Immich is deployed via Ansible using Docker Compose. To update Immich to a new version:

1.  **Check Release Notes**: Review the [Immich Release Notes](https://github.com/immich-app/immich/releases) for any breaking changes.

2.  **Update Version Variable**:
    Edit `ansible/group_vars/services.yml` and update the `immich_version` variable.

    ```yaml
    immich_version: "v1.121.0" # Update this to the desired version
    ```

3.  **Run Playbook**:
    Run the services playbook to apply the update.

    ```bash
    ansible-playbook ansible/playbooks/services.yml -i ansible/inventories/generated/hosts.yml -e "ansible_user=root" --vault-password-file ~/.ansible_vault_pass
    ```

    This will:
    -   Update the `docker-compose.yml` and `.env` files if necessary.
    -   Pull the new Docker images.
    -   Recreate the containers with the new version.
    -   Remove orphaned containers (e.g., if services were removed).

## Backup and Restore

The Immich data is stored in `/mnt/immich` on the LXC host, which is a bind mount from the Proxmox host (or a separate disk).

-   **Database**: The database is stored in `/mnt/immich/postgres`.
-   **Uploads**: The uploaded assets are in `/mnt/immich/library`, `/mnt/immich/uploads`, etc.

Ensure these directories are backed up regularly.

## Troubleshooting

-   **Check Logs**:
    ```bash
    ansible immich -m shell -a "docker logs immich_server --tail 100" -i ansible/inventories/generated/hosts.yml -e "ansible_user=root"
    ```

-   **Check Status**:
    ```bash
    ansible immich -m shell -a "docker ps" -i ansible/inventories/generated/hosts.yml -e "ansible_user=root"
    ```
