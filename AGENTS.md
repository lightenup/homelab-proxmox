# AGENTS.md

Guidance for AI coding agents working in this repo. Project conventions (tech stack, structure,
code style, recent changes) live in [CLAUDE.md](./CLAUDE.md). This file covers workflow rules that
are **not** obvious from the code — most importantly, how to get commits to GitHub from the dev
machine, which is behind a corporate proxy.

## Working with Git — pushing is blocked by Zscaler

The dev Mac is behind a corporate **Zscaler** transparent proxy (an MDM-managed `TRPTunnel` system
extension that cannot be removed — do not try). It blocks the two normal ways to push to GitHub:

- **`git push` over HTTPS** — the `git-receive-pack` POST (the actual pack upload) returns
  **HTTP 403**. This affects any shell on the Mac, including a plain terminal. Note that a
  *non-fast-forward* rejection can surface first and look like an ordinary git error; that is git
  bailing during ref-advertisement (a GET the proxy allows) *before* it uploads. A force-push proves
  the 403 by actually uploading the pack and then failing.
- **SSH to `github.com`** — the connection is dropped on both port 22 and 443.

**Allowed:** the GitHub REST / Git-Data API (`api.github.com` via `gh api`), git ref-advertisement
GETs (so `git fetch` / `git clone` over HTTPS work), and `gh pr create`.

Committing locally with `git commit` is fine — only the push leg is blocked.

### How to push a branch/commit (gh Git-Data API)

1. Commit locally as normal.
2. For each changed file, create a blob:
   `gh api repos/OWNER/REPO/git/blobs -f content="$(base64 < FILE | tr -d '\n')" -f encoding=base64 --jq .sha`
3. Create a tree with `base_tree` set to the parent commit's SHA (the current remote branch tip, or
   `main`): `gh api repos/OWNER/REPO/git/trees --input tree.json --jq .sha`
4. Create the commit (build the JSON with `python3` to avoid zsh globbing `parents[]`):
   `gh api repos/OWNER/REPO/git/commits --input commit.json --jq .sha`
5. Create or update the ref:
   - create: `gh api repos/OWNER/REPO/git/refs -f ref=refs/heads/BRANCH -f sha=COMMIT`
   - update: `gh api -X PATCH repos/OWNER/REPO/git/refs/heads/BRANCH -f sha=COMMIT`
6. Verify content matches: local `git rev-parse HEAD^{tree}` must equal the remote tree SHA. Commit
   SHAs will differ (the API stamps its own committer metadata) — that is expected.
7. Realign local history onto the remote (a force-push cannot work here):
   `git fetch origin BRANCH && git reset --hard origin/BRANCH`

Open the PR with `gh pr create --base main --head BRANCH ...`.

### Gotchas

- The **first `gh api` call stalls ~2 minutes** on cold TLS through the proxy — enough to trip a
  120s command timeout. Run multi-file push scripts in the background; subsequent calls are ~1s.
- Inside `while read` loops, redirect `gh api ... < /dev/null` so `gh` does not consume the loop's
  stdin (it will hang otherwise).

### Alternative: push relay via the `pve` host

The homelab Proxmox host (`ci@pve`) has **unrestricted GitHub access** (HTTPS 200, SSH negotiates).
If the API path becomes painful it can serve as a git push relay. Pipeline deploys already run on
`pve`, so they are unaffected by the Mac's push block.

## Zscaler also blocks Tailscale (dev Mac)

Same proxy, same class of block as the git push above — **the entire `tailscale.com` domain is
403'd** on the dev Mac, so Tailscale cannot log in there at all:

```text
login.tailscale.com        → 403   Server: Zscaler/6.2
controlplane.tailscale.com → 403
api.tailscale.com          → 403
derp1.tailscale.com        → 403
```

DNS for those names resolves into Zscaler's synthetic `192.200.0.x` range, and the TLS cert is
`O=Zscaler Inc., CN=Zscaler Intermediate Root CA`, not Tailscale's.

**Symptom to recognise:** clicking *Log in* in the Tailscale GUI silently does nothing — no browser
tab, no error. The app POSTs to `controlplane.tailscale.com`, gets an HTML block page instead of
JSON, fails to parse it, and gives up quietly.

**Consequences:**

- A pre-shared auth key does **not** help — `tailscale up --auth-key=…` still has to reach the
  control plane.
- Switching Wi-Fi or tethering does **not** help; the Zscaler Client Connector
  (`com.zscaler.zscaler.TRPTunnel`, on `utun5`) follows the Mac onto any network.
- `tailscale status` **hangs** rather than failing fast. If a `tailscale` command appears stuck,
  this is why — kill it rather than waiting.
- The GUI (App Store) build also does not expose `/var/run/tailscaled.socket`, so the CLI cannot
  talk to a *working* daemon either. Read the device's MagicDNS name from the menu-bar icon or the
  admin console instead of scripting it.

**Unaffected:** the `pve` host and the LXCs — neither is behind Zscaler. The `064-llm-router`
Tailscale sidecar runs on its LXC and is fine. Only *reaching the tailnet from the Mac* is broken.

## Deploys

Service deploys go through the gated GitHub Actions pipeline
(`Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`, both `workflow_dispatch`), which can target any
branch ref — no merge to `main` is required to deploy. Trigger with `gh workflow run`. Per-feature
runbooks live in `specs/*/quickstart.md`.

### The "LAB" stage is an isolated rehearsal (067)

`pve-service-deploy --environment lab` (the `LAB rehearsal (isolated)` job of `lxc-promote-prod.yml`,
and `lxc-lifecycle.yml` with `environment=lab`) creates a throwaway copy of the service on `vmbr99`
(`10.99.0.0/24`, LAN blocked by nftables), configures it with Ansible, probes isolation from inside,
destroys it, and proves production did not change (fingerprint before/after). It has its own state
(`state/lab/<svc>`, removed afterwards) and its tfvars are derived from `prod.tfvars`. It does **not**
change production; the PROD plan that follows is the real change. LAB cannot be deleted or kept:
there is no standing lab copy. Evidence: `reports/lab/` in the run's evidence pack. Contract:
[`specs/067-isolated-lab/contracts/pve-service-deploy-lab.md`](specs/067-isolated-lab/contracts/pve-service-deploy-lab.md).

Before the **first** deploy of a service:

- Check `ssh pve sudo pct list` for a container that already has the service's hostname or IP but is
  not in Terraform state. `pve-service-deploy` now refuses a plan that would create a duplicate
  (`scripts/lab/lib/ct_conflicts.sh`), but import or remove the stray yourself rather than finding
  out from a failed run.
- Read the plan's create count, not just the "destructive" flag. A create next to an untracked
  container is not destructive, and it still causes a duplicate IP (Home Assistant, 2026-10-28).

## Running workflows locally with `act`

`act` (with `~/.actrc` mapping `ubuntu-latest`/`self-hosted` to `catthehacker/ubuntu:act-latest`) is
the approved way to validate workflow edits (constitution, "Local Workflow Testing"):

```bash
act -l                                                     # all workflows parse
act -n -W .github/workflows/<file>.yml workflow_dispatch   # dry-run the one you changed
```

- **Docker socket**: `act` defaults to Colima's socket, which is usually down on the dev Mac
  (`Cannot connect to the Docker daemon`). Point it at Docker Desktop:
  `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock act ...`
- **`-n` is a parse check, not a test.** Jobs gated on another job's outputs (`needs.gate.outputs.run`)
  or on the PR owner/fork guard do not appear in the dry-run. Cover their logic with the guard tests
  in `python/tests/workflows/`, or extract a step's `run:` with PyYAML and execute it locally.
- Steps that SSH to `pve` or need vault secrets can't really run under `act`. A full run with
  secrets is described in `docs/operations/proxmox-ci.md`. If `act` can't be used, say why in the PR.

## Running the tests

From the repo root: `bash scripts/ci/python-tests.sh` (the same command CI runs; set `PYTHON_BIN` to
pick an interpreter). It runs `python/tests/` with `--cov-fail-under=80`.

- **Coverage measures five modules only** (`orchestrator`, `evidence`, `summary_from_evidence`,
  `summary_markdown`, `version_currency`; see `addopts` in `python/pytest.ini`). The other modules
  are not in the percentage at all; the mutation gate is their check.
- `python/tests/workflows/` and `python/tests/guardrails/` are guard tests: they assert the shape of
  workflows and repo files, not runtime behaviour. Workflow edits usually need one here, because
  `act -n` and yamllint miss logic and shell errors (see `test_workflow_heredocs.py`).

## Mutation testing (mutmut 3)

Use the Taskfile wrappers; they pick whichever venv actually has mutmut (`.venv`, else
`.venv-mutmut`). `.venv-mutmut` must be Python 3.11, the nightly's version: mutmut's cache keys on
`ast.dump`, so on any other version the first run after a pull re-tests everything. Setup is in
`docs/operations/mutation-testing.md`:

| Task | Use |
|---|---|
| `task mutmut:pull` | Fetch `main`'s nightly results from the NAS into `mutants/` (via `ci@pve`) |
| `task mutmut:status` | Print score, gate and top survivor modules from `mutants/report.json` |
| `task mutmut:run` | Re-test changed source. After editing **tests**, pass the module: `task mutmut:run -- "homelab_proxmox_orchestrator.<module>*"` (mutmut does not notice test-only edits) |
| `task mutmut:browse` | Survivor TUI (interactive — not for agents) |
| `task mutmut:gate` | Full CI-equivalent gate, ~2 min. **Deletes `mutants/` first** |

Score = killed / (killed + survived); floor in `python/mutmut-threshold.txt`, gate = floor − 1.
The PR gate (`mutation.yml`) only runs for paths in `scripts/ci/mutation-gate-paths.txt`. Do not
add incremental/seeded modes. Details: `docs/operations/mutation-testing.md`.

## The `allow-protected-path-changes` label

**What it is.** `ci.yml`'s "Guardrail: protected paths must not change" fails any PR that touches a
protected path unless the PR carries this label. Protected paths (`.guardrails/protected-paths.json`):
`.specify/**`, `adapter/**`, `scripts/lab/**`, `mkdir/**`.

**When it is used.** Only when the PR changes one of those paths on purpose, for example
`scripts/lab/pve-service-deploy` or `scripts/lab/lib/*`, a new entry in
`scripts/lab/service-scope-allowlist.json`, or an edit to `.specify/memory/constitution.md`. Check
each PR with `git diff --name-only origin/main... | grep -E '^(\.specify|adapter|scripts/lab|mkdir)/'`;
do not assume from the previous PR (a follow-up often touches no protected path and needs no label).

**Who approves it.** The operator. The label switches off a safety check, so an agent adds it only
after the operator has said so for that PR, and approval for one PR does not carry to the next. Ask
when you open the PR, list the protected files in the PR body, and add the label once approved.

**How to add it.** Use REST, not `gh pr edit` (which needs a scope the token lacks behind Zscaler):

```bash
gh api repos/OWNER/REPO/issues/N/labels -f 'labels[]=allow-protected-path-changes'
```

**Timing.** `ci.yml` runs on `opened, synchronize, reopened, labeled, unlabeled`, so adding the label
after opening re-runs the guardrail with the label in the payload. Do not use `gh run rerun` for this:
it replays the old, label-less payload and fails the same way. If a run still reads the old labels,
close and reopen the PR:

```bash
gh api -X PATCH repos/OWNER/REPO/pulls/N -f state=closed
gh api -X PATCH repos/OWNER/REPO/pulls/N -f state=open
```

## Note on `gh` and Zscaler

`gh pr create` may fail where plain API calls succeed — the proxy blocks the git pack upload and
SSH, but `api.github.com` POSTs go through fine. Prefer the non-interactive form for anything
write-shaped:

```bash
gh api repos/OWNER/REPO/pulls --input pr.json
```

## Spec-driven workflow

Features are developed spec-first under `specs/NNN-*/` via the speckit skills
(`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`). `CLAUDE.md` is
auto-generated from feature plans; put durable manual guidance in its `MANUAL ADDITIONS` block or
here in `AGENTS.md` (which speckit does not regenerate).
