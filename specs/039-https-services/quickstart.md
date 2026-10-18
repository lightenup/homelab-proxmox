# Quickstart: HTTPS for All Homelab Services

**Feature**: 039-https-services
**Branch**: `039-https-services`

---

## Prerequisites

Before deploying, complete these one-time manual steps:

### 1. Domeneshop DNS Records (Registrar)

Log in to [Domeneshop control panel](https://www.domeneshop.no/admin) → DNS → `hus-sky.no`:

- Add a **wildcard A record**: `*.hus-sky.no` → `192.168.1.211`
- (Or add individual A records for each subdomain: `nextcloud`, `immich`, `grafana`, `jellyfin`)

### 2. Domeneshop API Credentials

Generate API credentials:
1. Go to Domeneshop control panel → Settings → API
2. Create a new API token
3. Save the **token** and **secret**

Add to Ansible vault:
```bash
cd ansible
ansible-vault edit group_vars/services/vault.yml
```

Add these entries:
```yaml
domeneshop_api_token: "YOUR_TOKEN_HERE"
domeneshop_api_secret: "YOUR_SECRET_HERE"
```

## Deployment

### From Developer Laptop

```bash
# Deploy reverse proxy with HTTPS configuration
cd ansible
ansible-playbook playbooks/services.yml --tags reverse_proxy \
  -i inventories/prod/hosts.yml \
  --ask-vault-pass

# Deploy Nextcloud domain migration
ansible-playbook playbooks/nextcloud.yml \
  -i inventories/prod/hosts.yml \
  --ask-vault-pass

# Deploy Grafana domain migration
ansible-playbook playbooks/monitoring.yml \
  -i inventories/prod/hosts.yml \
  --ask-vault-pass
```

### From CI/CD (GitHub Actions)

Use the existing `lxc-deploy-lab.yml` workflow:
1. Service: `reverse_proxy` → deploys HTTPS-enabled Caddy
2. Service: `nextcloud` → deploys domain migration
3. Service: `monitoring` → deploys Grafana domain update

---

## Verification

### Quick Checks (from any LAN machine)

```bash
# Check HTTPS and certificate for each service
for svc in nextcloud immich grafana jellyfin; do
  echo "--- $svc ---"
  curl -sI "https://$svc.hus-sky.no" | head -5
  echo | openssl s_client -connect "$svc.hus-sky.no:443" -servername "$svc.hus-sky.no" 2>/dev/null | openssl x509 -noout -issuer -dates
done
```

### Expected Results

- Each `curl` returns HTTP 200 (or 301/302 for login redirects)
- Each certificate shows:
  - Issuer: `Let's Encrypt`
  - Not After: ~90 days from issuance
  - No errors

### Mobile App Testing

1. **Nextcloud**: Install app → Server URL: `https://nextcloud.hus-sky.no` → Login → Verify file sync
2. **Immich**: Install app → Server URL: `https://immich.hus-sky.no` → Login → Verify photo backup

### Data Preservation Check

- Nextcloud: All user accounts and files accessible at new URL
- Immich: All photos and albums accessible at new URL
- Grafana: All dashboards intact at `https://grafana.hus-sky.no`

---

## Rollback

If something goes wrong:

1. **Revert Caddy to HTTP-only**: Set `caddy_custom_binary: false` and re-run the reverse proxy playbook. This restores the stock Caddy with `auto_https off`.
2. **Revert Nextcloud domain**: Change `nextcloud_domain` back to `nextcloud.local` and `nextcloud_overwrite_protocol` back to `http`. Re-run the Nextcloud playbook.
3. **Revert Grafana domain**: Change `grafana_domain` back to `monitoring.local` and `grafana_protocol` back to `http`. Re-run the monitoring playbook.

---

## Adding a New Service (Future)

To add HTTPS for a new service:

1. Create a new Caddy site template: `ansible/roles/reverse_proxy/templates/<service>.caddy.j2`
2. Add the deploy task to `ansible/roles/reverse_proxy/tasks/main.yml`
3. Define `<service>_ip` and `<service>_port` in group vars
4. (Optional) Add an A record at Domeneshop if not using wildcard
5. Run the reverse proxy playbook
