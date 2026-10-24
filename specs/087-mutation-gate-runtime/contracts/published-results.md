# Contract: published main results

The nightly writes this. `task mutmut:pull` on the Mac reads it. The PR gate does not read it
(FR-004).

## Location

```text
/mnt/nas/homelab_ci/mutmut/            # on pve; NAS share /volume1/homelab_ci
├── main -> main-20261025T030512Z      # symlink, the only path readers use
├── main-20261025T030512Z/             # current set
└── main-20261024T030447Z/             # previous set, kept for one more run
```

Readers resolve `main/` (with the trailing slash) and never list `main-*`.

## Contents of one set

```text
main-<UTC>/
├── report.json                        # written last, before the symlink swap
├── survivors.txt
├── mutmut-cicd-stats.json
├── mutmut-stats.json
└── src/homelab_proxmox_orchestrator/**/*.py.meta
```

Paths are relative to `mutants/`, so a reader can copy the set into its own `mutants/` as it is.
The set never contains mutated sources or copied tests (research R7).

## `report.json`

```json
{
  "schema": 1,
  "commit": "9d80372…",
  "finished_at": "2026-10-25T03:05:12Z",
  "mutmut_version": "3.8.0",
  "counts": {"killed": 1717, "survived": 1061, "no_tests": 1337, "timeout": 2,
             "suspicious": 0, "skipped": 0, "segfault": 0, "total": 4117},
  "score": 61.81,
  "floor": 61.0,
  "margin": 1.0,
  "gate": 60.0,
  "passed": true,
  "survivors_by_module": [
    {"module": "orchestrator", "survived": 312, "killed": 540, "no_tests": 101}
  ]
}
```

- `commit` is the full SHA the run tested. `finished_at` is UTC with a `Z` suffix.
- `score` is rounded to two decimals. `passed` is `score >= gate`.
- `survivors_by_module` lists every module, ordered as in data-model.md.
- A reader must reject a set whose `schema` it does not know.

## `survivors.txt`

The same ranking as plain text, one module per line, for people and for the job summary:

```text
312  orchestrator
188  service_lifecycle
…
```

## Publish procedure (writer)

1. Check that `/mnt/nas/homelab_ci` is mounted and writable. If not, fail with
   `::error::Shared mount missing at /mnt/nas/homelab_ci on PVE.` (as today).
2. Copy the result files into `mutmut/main-<UTC>/`, with `report.json` last.
3. `ln -sfn main-<UTC> mutmut/main.tmp && mv -T mutmut/main.tmp mutmut/main`.
4. Delete every `main-*` directory except the newest two.

Any failure in steps 1–3 fails the nightly job (FR-002).
