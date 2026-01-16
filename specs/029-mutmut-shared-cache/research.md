# Research: Mutmut cache behavior and shared cache practices

**Branch**: `029-mutmut-shared-cache`  
**Date**: 2026-01-16  
**Status**: Complete

## Scope
Understand how `mutmut` stores its cache, how to point it at a shared location, and what breaks when sharing `.mutmut-cache` across machines or CI runners.

## Sources
- mutmut 2.5.1 source: `mutmut/cache.py`, `mutmut/__main__.py`
- mutmut 2.5.1 metadata docs (installed package)

## Findings

### F1: Cache location is a single SQLite file in the working directory
**What**: `mutmut` binds its SQLite database to `os.path.join(os.getcwd(), '.mutmut-cache')`. There is no CLI flag or config setting for an alternate cache path.

**Implication**: The cache path is controlled by *where you run mutmut* and what exists at `.mutmut-cache` in that directory. The cache is a **file**, not a folder.

**Best practices**
- Run mutmut from the repo root so file paths in the cache remain consistent across machines.
- To share cache across hosts, point `.mutmut-cache` to a shared file (symlink or bind mount).

---

### F2: Cache invalidation is conservative and versioned
**What**: The cache contains a schema version and per-test-suite hash. If the schema version changes, mutmut prints “cache is out of date” and rebuilds. If test hashes change, mutants are marked `UNTESTED` and rerun.

**Best practices**
- Keep the same mutmut version across machines to avoid automatic cache resets.
- When configuration changes (e.g., `mutmut_config.py`), manually delete `.mutmut-cache` to ensure re-evaluation.

---

### F3: Sharing across machines requires path consistency
**What**: Cache entries store filenames exactly as provided (relative paths when run from repo root, absolute paths when invoked with absolute paths). Later operations open these paths directly.

**Failure mode**: If the path stored in the cache does not exist on the consuming machine (different checkout location or working directory), `mutmut results/show/apply/browse` can fail when it tries to open source files.

**Best practices**
- Use relative paths by always running mutmut from the repo root with the same `paths_to_mutate`.
- Avoid mixing cache data from runs that used different path forms (absolute vs relative).

---

### F4: Symlink and shared-storage considerations
**What**: Because `.mutmut-cache` is a single SQLite file, symlinking is the simplest way to re-point it. SQLite requires reliable file locking.

**Best practices**
- Symlink `.mutmut-cache` → `/mnt/nas/.../mutmut-cache/<branch>` (note: target must be a file, not a directory).
- Ensure the shared filesystem supports POSIX locks; avoid concurrent writers on the same cache file.
- Prefer *one writer at a time* (nightly CI writes; developer machines read for `mutmut browse`).

---

## Practical guidance (shared cache workflow)
1. Create per-branch cache file on shared storage (e.g., `/mnt/nas/homelab_ci/mutmut-cache/<branch>`).
2. In the repo root, symlink `.mutmut-cache` to the shared file.
3. Run mutmut from the repo root using the same relative `paths_to_mutate` on all machines.
4. If a run fails due to corruption or schema mismatch, delete the shared `.mutmut-cache` and rerun.

## Failure modes & mitigations
| Failure mode | Cause | Mitigation |
| --- | --- | --- |
| Cache resets unexpectedly | Mutmut schema version changed | Pin mutmut version across machines; expect a one-time rebuild |
| Cache ignored for mutants | Test hash changed or `NO_TESTS_FOUND` | Accept re-run; ensure tests are discoverable |
| `FileNotFoundError` during results/show | Paths in cache don’t exist on the host | Keep consistent working directory and relative paths |
| SQLite locking errors or corruption | Concurrent writers or unsupported NFS locking | Single-writer policy; verify NAS supports locks |
| Cache changes not reflected | `mutmut_config.py` changed | Manually delete `.mutmut-cache` before rerun |

## Decision
Adopt a shared, per-branch `.mutmut-cache` *file* on NAS, referenced via symlink from the repo root. Enforce a single-writer policy and consistent working directory to keep cache entries valid across machines.

## Decision: Validate workflow edits with actionlint and act

**Rationale**: actionlint provides fast static validation, while act exercises workflow execution locally. This aligns with the repo constitution and reduces CI feedback loops when editing `.github/workflows/*.yml`.

**Alternatives considered**:
- CI-only validation (rejected due to slower feedback).
- actionlint-only or act-only (rejected because they cover different validation layers).
