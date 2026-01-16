# Quickstart: Mutmut Shared Cache

## Goal

Persist mutmut cache on shared storage so `mutmut results/show/apply/browse` works from both the PVE host and a developer laptop.

## Shared cache layout

- Shared storage mount (example): `/mnt/nas/homelab_ci/`
- Cache file (example): `/mnt/nas/homelab_ci/mutmut-cache/<branch>`

## PVE workflow (example)

1. Ensure the NAS share is mounted on PVE (currently `/mnt/nas/homelab_ci`).
2. In the repo root, point `.mutmut-cache` at the shared cache:

   - `ln -s /mnt/nas/homelab_ci/mutmut-cache/<branch> .mutmut-cache`

3. Run mutation testing:

   - `mutmut run --paths-to-mutate python/src/homelab_proxmox_orchestrator --tests-dir python/tests --runner "env PYTHONPATH=python/src python -m pytest -q -c python/pytest.ini"`

## Developer laptop workflow (example)

1. Mount the same NAS share on the laptop.
2. In the repo root, point `.mutmut-cache` at the mounted share.
3. Use `mutmut results`, `mutmut show <id>`, `mutmut apply <id>`, or `mutmut browse` without re-running mutations.

## Troubleshooting

- If the cache is missing or unwritable, mutation runs should fail with a clear message indicating the mount path and required permissions.
