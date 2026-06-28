# Quickstart: Market-Model Service Deploy

Verifies the deploy end-to-end: provision → deploy healthy → MCP round-trip → upgrade safety →
disposability → posture. Run from CI (`lxc-deploy-lab` / promote workflows) or laptop
(`pve-service-deploy market-model ...`) — both paths are equivalent (Dual-Provisioning Parity).

## 0. Operator prerequisites (one-time)

- Allocate a free services-bridge IP for `market-model` (proposed prod `192.168.1.218/24`, lab
  `192.168.20.219/24`) in `service_ips` / the network plan. **No** NAS/NFS prereq (D-001).
- Confirm the GHCR pull token (`ghcr_pull_username` / `ghcr_pull_token`) can read
  `ghcr.io/lightenup/market-model`.

## 1. Provision the LXC (Terraform)

```bash
# plan-only first (gated pipeline)
scripts/lab/pve-service-deploy market-model            # plan
scripts/lab/pve-service-deploy market-model --apply    # apply (after review)
```

Expect: `module.market_model_lxc` created; **no** `features_mount` shown. The host appears in the
generated inventory.

## 2. Deploy the stack (Ansible)

Pin `market_model_version` in `ansible/group_vars/services/vars.yml` (e.g. `"0.3.0"`), then run the
service playbook (invoked by the orchestrator as `ansible/playbooks/market-model.yml`).

**Verify health**:

```bash
curl -fsS http://<market-model-ip>:8000/healthz      # → 200
curl -fsS http://<market-model-ip>:8000/ | jq .      # → path-source index (curated + generator)
docker -H ssh://root@<market-model-ip> ps            # api + mcp healthy; only 8000 + 8001 published
```

Expect: both `market_model_api` and `market_model_mcp` healthy; no GUI container; no Caddy route.

## 3. MCP round-trip (US2)

From a tailnet client against `http://<market-model-ip>:8001`:

```text
list_calibrations / list_stress_scenarios   → entries returned (mcp forwards to api:8000)
generate_path_set(<calibration>)            → returns { id, version }; api persists the row
get_path_set(<id>)                          → byte-identical blob
```

Confirm the row exists on the host:

```bash
ssh root@<market-model-ip> \
  "sqlite3 {{ market_model_data_dir }}/data/path-sets.sqlite 'SELECT count(*) FROM path_sets;'"
```

## 4. Topology assertions

```bash
docker -H ssh://root@<market-model-ip> inspect market_model_mcp \
  --format '{{json .Config.Env}} {{json .HostConfig.Binds}}'
# API_BASE_URL=http://api:8000, MCP_TRANSPORT=http, NO data bind (localtime only)

ssh root@<market-model-ip> "stat -c '%u:%g %a' {{ market_model_data_dir }}/data"
# → 100:65534 0755   (D-006 — a root:root dir would fail to persist)
```

## 5. Upgrade safety (US3)

```bash
# bump market_model_version, then redeploy
scripts/lab/pve-service-deploy market-model --apply   # or CI promote workflow
```

Expect: both containers healthy on the new tag; existing assembled/generated rows intact; curated
library re-seeded idempotently (`INSERT OR IGNORE`) — never clobbered.

## 6. Disposability (US3 / DR)

```bash
ssh root@<market-model-ip> "rm -f {{ market_model_data_dir }}/data/path-sets.sqlite"
# restart the stack
```

Expect: stack returns healthy; curated library re-seeded from the image; a previously assembled set
is reproducible by re-POSTing identical inputs (same `sha256:` id).

## 7. Posture & monitoring

- Only `8000` + `8001` published; no GUI, no Caddy route, no landing-page card.
- Blackbox liveness probe `market-model-api` green in the monitoring contract; `MarketModelDown`
  fires when the service is stopped.
- `scripts/healthcheck/market-model.sh --profile lan` → 200.

## Negative check (preflight, SC-007)

Set `market_model_version: ""` (or `latest`) and run — preflight MUST reject before any change.
