# Adding a New ntfy Publisher

Procedure for onboarding a new sending system to the estate's ntfy push channel (spec `082`).
The interface contract is in `specs/082-ntfy-push-service/contracts/publisher-interface.md`.

## Prerequisites

- The new system has a stable identity (a name that will not change).
- You have access to `ansible-vault edit` (vault password).

## Steps

### 1. Add the account to the role defaults

In `ansible/roles/ntfy/defaults/main.yml`, add an item to `ntfy_users`:

```yaml
ntfy_users:
  # ... existing entries ...
  - name: "<publisher>"
    topic: "<topic>"          # must be new; a topic has exactly one publisher
    password_hash: "{{ ntfy_<publisher>_password_hash }}"
    token: "{{ ntfy_<publisher>_token }}"
```

Rules (data-model.md):
- The topic name must be new. Reuse an existing topic only if the publisher is replacing it.
- No account gets role `admin`.

### 2. Add the two vault secrets

```bash
ansible-vault edit ansible/group_vars/services/vault.yml
```

Add:

```yaml
ntfy_<publisher>_password_hash: "<bcrypt hash, cost >= 10>"
ntfy_<publisher>_token: "<tk_ + 29 chars>"
```

Generate them:

```bash
# Password hash (enter a random password you will then discard — publishers authenticate
# by token only, the hash exists only because ntfy requires one on every account):
docker run --rm -it binwiederhier/ntfy:v2.28.0 user hash

# Token:
docker run --rm binwiederhier/ntfy:v2.28.0 token generate
```

### 3. Deploy ntfy

```bash
scripts/lab/pve-service-deploy apply --environment prod --service ntfy
```

The role re-renders `server.yml` on every deploy, so the new account, ACL and token are
applied automatically. No manual step on the LXC.

### 4. Subscribe in the phone app

The owner's `*` read grant already covers the new topic. In the ntfy Android app:

1. Subscribe to `<topic>` (the app will use the existing `owner` credentials).
2. Verify "instant delivery" is on for the topic.

### 5. Extend the ACL check matrix

In `scripts/healthcheck/ntfy-acl-check.sh`, add a new row for the publisher token:

- `read <each existing topic>` → `deny`
- `read <new topic>` → `deny`
- `write <new topic>` → `allow`
- `write <each other topic>` → `deny`

Run the check against PROD:

```bash
NTFY_URL=https://ntfy.hus-sky.no \
NTFY_OWNER_TOKEN=… NTFY_ALERTMANAGER_TOKEN=… NTFY_HERMES_TOKEN=… NTFY_<PUBLISHER>_TOKEN=… \
  scripts/healthcheck/ntfy-acl-check.sh
```

All cells must PASS before the publisher is considered onboarded.

### 6. Hand the token to the publisher

`ntfy_<publisher>_token` goes into the publisher's own secret store (vault entry, environment
variable, etc.). It is never committed to source control, placed in URLs, or logged.
