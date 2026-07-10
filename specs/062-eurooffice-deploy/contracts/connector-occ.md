# Contract: Nextcloud `eurooffice` Connector (occ)

Runs on the **nextcloud** LXC via `docker exec -u www-data nextcloud_app php occ ...`
(extends `ansible/roles/nextcloud/tasks/main.yml`, mirroring its existing occ idioms).

## Preflight (FR-009 — hard block)
```
occ status --output=json  →  versionstring MUST start with "33." or higher (NC >= 33)
```
Fail loudly if below 33; MUST NOT install the connector otherwise.

## Install + enable (FR-007)
```
occ app:install eurooffice     # tolerate "already installed"
occ app:enable  eurooffice     # tolerate "already enabled"
```

## Configure (idempotent, FR-007 / FR-003)
```
occ config:app:set eurooffice DocumentServerUrl         --value "https://eurooffice.hus-sky.no/"
occ config:app:set eurooffice DocumentServerInternalUrl --value "http://{{ eurooffice_ip }}/"   # port 80 (eurooffice_port pinned to 80, F1)
occ config:app:set eurooffice jwt_secret                --value "{{ eurooffice_jwt_secret }}"   # no_log
```

## Exclusivity (FR-010 / SC-006)
`nextcloud_apps_remove` already contains `richdocumentscode`, `richdocuments` (removed by prior
Nextcloud work). Re-assert: after apply, `occ app:list` shows `eurooffice` enabled and no
`richdocuments*`.

## Contract assertions
- Install task guarded so re-runs don't fail ("already installed"/"already enabled").
- `config:app:set` is declarative → idempotent; `jwt_secret` value MUST equal the server's
  `JWT_SECRET` (same vault var) — mismatch surfaces as the editor failing to load.
- `jwt_secret` task uses `no_log: true`.

**To confirm at implement time** (D-005): app-store id (`eurooffice`) is installable via
`occ app:install` on NC 34; exact config keys against the Euro-Office Nextcloud integration doc. If
not app-store-installable, fall back to fetching the v11.0.1 release tarball into the apps volume.
