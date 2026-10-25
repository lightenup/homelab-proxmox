# Contract: ntfy ACL matrix (095)

Extends `082` SC-002. Checked by `scripts/healthcheck/ntfy-acl-check.sh` and by a guard test
against the rendered `server.yml`. Expected HTTP result: `200` allowed, `403` refused (with
`deny-all`, an unknown or missing token is `403`).

Read = `GET /<topic>/json?poll=1`. Write = `POST /<topic>`.

| Credential ↓ / Topic → | `hermes` R | `hermes` W | `hermes-in` R | `hermes-in` W | `actions` R | `actions` W | `alerts` W | `relay` W |
|---|---|---|---|---|---|---|---|---|
| `owner` | 200 | 403 | 200 | **200** | 200 | **200** | 403 | 403 |
| `hermes` | 403 | 200 | **200** | **403** | 403 | **403** | 403 | 403 |
| `action_relay` (P2) | 403 | 403 | 403 | **403** | 200 | **403** | 200 | 200 |
| `alertmanager` (until P2) | 403 | 403 | 403 | 403 | 403 | 403 | 200 | 403 |
| `pve_backup`, `version_check`, `mutation` | 403 | 403 | 403 | **403** | 403 | **403** | 403 | 403 |
| none | 403 | 403 | 403 | **403** | 403 | **403** | 403 | 403 |

The bold cells carry the feature's safety argument:

- The `hermes` credential (the agent) can **never** write `hermes-in` or `actions`.
- The only writer of `hermes-in` and `actions` is `owner`.

## LAB scratch pair (spec FR-011)

| Credential ↓ / Topic → | `hermes-lab-in` R | `hermes-lab-in` W | `hermes-lab` R | `hermes-lab` W | any production topic |
|---|---|---|---|---|---|
| `owner` | 200 | **200** | 200 | 403 | as above |
| `hermes_lab` | **200** | **403** | 403 | 200 | **403** (read and write) |
| every other credential, none | 403 | **403** | 403 | 403 | as above |

`hermes_lab` is rendered only on the LAB rig. It can never reach a production topic, so a LAB agent
cannot read `hermes-in` or touch `actions`.
