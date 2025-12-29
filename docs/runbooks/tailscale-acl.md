# Tailscale ACL Management

## Source of Truth
The canonical source for Tailscale ACLs is `docs/tailscale/policy.hujson`.

## Format
We use **HuJSON** (Human JSON), which supports comments. This allows us to document *why* a rule exists directly in the file.

## ⚠️ CRITICAL: GitHub Identity Format
If you use GitHub for authentication, you **MUST** use the format `login@github`.
**DO NOT** use email addresses (e.g., `user@example.com`).
Using an email address will result in the user being unrecognized and denied access, even if the email is associated with the GitHub account.

## Workflow

### Option A: Manual Application (Recommended/Fallback)
1. Edit `docs/tailscale/policy.hujson`.
2. Validate the JSON syntax (e.g., using VS Code).
3. Commit and push your changes to the repo.
4. Open the [Tailscale Admin Console](https://login.tailscale.com/admin/acls).
5. Copy the content of `policy.hujson`.
6. Paste it into the ACL editor.
7. The editor will validate the config. If valid, click **Save**.

### Option B: Automated Application (Safe Mode)
**Prerequisite**: `tailscale_safe_mode` must be set to `true` in Ansible variables.

1. Run the Ansible playbook with the `acl` tag:
   ```bash
   ansible-playbook playbooks/tailscale.yml --tags acl
   ```
2. The playbook will:
   - Backup the current ACL.
   - Validate the new policy.
   - Push the new policy.
   - Verify connectivity.
   - **Rollback** automatically if connectivity is lost.

## Troubleshooting
- **Access Denied**: Check if you used an email address instead of `login@github`.
- **Syntax Error**: Ensure you didn't leave a trailing comma (standard JSON rules apply after comment stripping, though HuJSON is lenient).
