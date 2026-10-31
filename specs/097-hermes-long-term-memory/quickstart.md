# Quickstart / validation: Long-term memory for Hermes (097)

Runbook-style checks. Each maps to a spec success criterion.

- **Keys**: read them from the vault on `pve` or a laptop (constitution V). Never paste them into
  chat or logs. `$MEM` below means `https://memory-api.hus-sky.no/v1/default/banks`.
- **Synthetic data**: PROD checks use clearly synthetic facts ("my test parrot is called
  Probe-097") and remove them afterwards (§ 8).

## 0. Preconditions

- **NAS share** (T001): `homelab_memory` created on the Synology by the owner, 2026-10-31. The
  `pve` mount `/mnt/nas/homelab_memory` is written to `/etc/fstab` by `proxmox_mounts`
  (`ansible.posix.mount`, `state: mounted`) at the first deploy; on 2026-10-31 it had no fstab
  entry yet, as expected.
- **Address** (T001): `pct list` on `pve`, 2026-10-31: 12 containers (VMIDs 100–112, no
  `memory`), and no `/etc/pve/lxc/*.conf` uses `192.168.1.223`.

## 1. Harness gate on the dev Mac (FR-021: SC-001 to SC-005)

Run before the first PROD promotion that turns memory on, and again for every later change to
the provider, its version or mode, the policy module or an adapter.

```sh
cd docs/backlog/097-spike
./render-prod.sh                 # research R-017: renders server.env, clients.json, plugin config from Ansible
./run.sh prod-render             # pinned images + shim + rendered config, dataset.json
python3 llmproxy/portability.py --clients hermes,open-webui,claude-code   # SC-005 + scope checks
```

Expected:

| Criterion | Pass condition |
|---|---|
| SC-001 | `score.txt` ≥ 14/16, all 8 volume probes, strictly above the latest baseline (`results/none*`) |
| SC-002 | Both update probes current, the negative probe "don't know" |
| SC-003 | `calls.jsonl` shows 0 chat calls for the memory phase; embed and rerank calls only, under the memory key |
| SC-004 | No egress attempt in the proxy log beyond the gateway |
| SC-005 | 6/6 cross-client recalls; read-only retain refused (403); forged tag replaced |

Record the results under `results/<YYYY-MM-DD>-prod-render/` and link them in the PR.

## 2. LAB rehearsal (SC-008)

Runs inside `Prod 1 - LXC Promote` for `memory`, then for `hermes`.

- **memory**:
  - The lab copy at `10.99.0.223` starts with no gateway, and `scripts/healthcheck/memory.sh`
    passes on `/health`.
  - The deploy probe (R-019) and the backup timer are listed in `reports/lab/skipped-checks.txt`.
  - Record the `/metrics` metric names for R-015:
    `curl -s http://10.99.0.223:8888/metrics | grep -E '^hindsight_' | cut -d'{' -f1 | sort -u`.
- **hermes**:
  - The agent's `/health` is healthy with memory unreachable.
  - One API-server turn returns the gateway's 429 without a crash (R-016).
  - The Open WebUI filter loads and fails open (R-007).
- **memory web UI**: the lab copy answers `GET http://10.99.0.223:9999/api/health` with 200 and
  serves `/login` without showing data. Record its resident memory for SC-007 (R-020).
- **Both**: the production fingerprint is unchanged, and no scrape target, probe or backup timer
  exists for a lab copy.

## 3. memory in PROD: deploy probe and auth (FR-010, FR-011, R-019)

1. The deploy log shows the `deploy-probe` retain, recall and delete passing.
2. Unauthenticated and wrong-key requests both return 401:

   ```sh
   curl -s -o /dev/null -w '%{http_code}\n' "$MEM/owner/stats"
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer hmem_wrong' "$MEM/owner/stats"
   ```

3. `GET $MEM/owner/stats` with the Hermes key returns 200.
4. A `DELETE $MEM/owner/memories` (clear bank) with the Hermes key returns 403.
5. Creating a webhook (`POST $MEM/owner/webhooks`) and changing the bank config
   (`PATCH $MEM/owner/config`) both return 403 with the Hermes key, and also with the admin key
   for the webhook (research R-001: refused for every scope).

## 4. Hermes remembers (US-1, FR-005)

1. Tell Hermes (Open WebUI with the agent model, or ntfy) "my test parrot is called Probe-097".
2. Open a **new** conversation and ask, as the first message, "what is my parrot called?". The
   answer is Probe-097.
3. Ask in Norwegian, "hva heter papegøyen min?", and get the same answer.
4. Ask about a cat that was never mentioned. The agent says it does not know.
5. In the store, the unit carries `client:hermes`:

   ```sh
   curl -s -H "Authorization: Bearer $HERMES_KEY" "$MEM/owner/tags"
   ```

## 5. Cost and locality (US-3, SC-003, SC-004)

1. After a day of use, in Grafana (`llm-router` dashboard), the `memory` key shows only
   `hermes-embed` and `hermes-rerank` requests.
2. Directly with the memory key: `POST http://192.168.1.220:4000/v1/chat/completions` with
   model `coder` returns 401 or 403 (model not in key scope, R-011).
3. On the memory LXC, `ss -tnp` over an hour shows connections only to `192.168.1.220:4000`
   (gateway) and from the reverse proxy.
4. Stop the memory stack. A Hermes conversation still completes, a plugin failure line appears
   in Loki within 5 minutes (SC-010), and Open WebUI chat still works. Restart the stack.

## 6. Shared memory and Claude Code scopes (US-2, SC-005, SC-009)

Precondition: the accepted risk is confirmed against the Claude Enterprise Guidance &
Guidelines, and the hooks are enabled in one private repository only (R-010).

1. In Open WebUI (plain model, not the agent), say "my test sister lives in Probe-by". In Claude
   Code in the private repository, ask "where does my test sister live?". The answer is Probe-by.
2. Tell Claude Code "my test boat is called Probe-båt". Ask Hermes over ntfy and get it back.
3. `list_tags` (MCP from any client) shows `client:open-webui` and `client:claude-code` on those
   units.
4. Open Claude Code in a work repository. Neither hook runs (no settings entry), and the store
   shows no new `cc-` document.
5. Set `claude-code` to `readonly` and deploy `memory`. A Claude Code retain is refused (403 in
   the hook log), recall still works, and Hermes and Open WebUI are unaffected.
6. Remove `claude-code` and deploy. Claude Code gets 401, the others are unaffected. Restore the
   original scope.

## 7. Open WebUI migration (FR-016)

1. Before the deploy, note the row count of Open WebUI's `memory` table.
2. After the deploy, the store has the same number of `owui-memory-*` documents, tagged
   `origin:open-webui-memory`.
3. The Personalisation › Memory setting is gone (memories off), and a fact from the imported set
   is answered in a new chat through the filter.

## 8. Correct and forget (US-5, R-012)

1. Ask "what do you remember about my test parrot?". The listing shows the Probe-097 unit.
2. Correct the parrot's name to Probe-098 (`update_memory`). Every client now answers Probe-098.
3. Forget it by asking any client to forget the parrot (`update_memory` redacting the fact, or
   `invalidate_memory`). No client recalls it.
4. **Resurrection check** (R-012 UNVERIFIED): in the same Hermes session as step 1, add two
   more turns, then ask in a new conversation. The parrot is still forgotten. If it comes back,
   switch the adapters to per-turn documents (R-012) and repeat.
5. Remove every `Probe-*` test fact the same way.

## 9. Restore drill (US-4, SC-006)

```sh
ansible-playbook -i ansible/inventories/prod/hosts.yml ansible/playbooks/memory-restore-drill.yml
```

Expected:

- `pg_restore` completes, and the stats match `stats.json`.
- Each probe in `drill-probes.json` finds its unit in the top 3 recall results.
- The export ZIP imports into an empty bank with the same document count.
- The teardown leaves no container or directory behind.

## 10. Size (SC-007)

After the Open WebUI import and a week of use, peak memory use on the LXC
(`node_memory_MemAvailable_bytes` in Grafana) stays below 70 % of 2048 MB.

## 11. Web UI (FR-023, SC-011)

1. The portal page shows a "Memory" tile linking to `https://memory.hus-sky.no`.
2. In a private browser window, the tile opens `/login`, and no bank, document or memory is
   visible. `curl -s -o /dev/null -w '%{http_code}\n' https://memory.hus-sky.no/api/banks` returns
   401.
3. Sign in with `memory_ui_access_key`. Browse bank `owner`. Search for "test parrot" and correct
   the unit. Hermes, Open WebUI and Claude Code all recall the corrected text, and `list_tags`
   shows `client:control-plane` on a memory added in the UI.
4. Delete the test conversation's document in the UI, and confirm that no client recalls it.
5. Try bank settings, adding a webhook and a reflect query in the UI. Each shows an error (403),
   and the API container log shows the refusal. The UI does not crash or restart
   (`docker ps` uptime unchanged).
6. An empty login key is caught before deploy, by the role's preflight and by
   `test_memory_config.py`. No PROD test is needed: the guard test runs in CI.

## Runbook: failed retains (`MemoryRetainFailures`)

1. Open the web UI's operations page (or `GET $MEM/owner/operations?status=failed` with the
   admin key) and list the failed operations.
2. Fix the cause. It is usually the gateway or the Mac.
3. Retry each operation in the web UI, or with `POST $MEM/owner/operations/{id}/retry`.
