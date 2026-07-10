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

## Deploys

Service deploys go through the gated GitHub Actions pipeline
(`Prod 1 - LXC Promote` → `Prod 2 - LXC Apply`, both `workflow_dispatch`), which can target any
branch ref — no merge to `main` is required to deploy. Trigger with `gh workflow run`. Per-feature
runbooks live in `specs/*/quickstart.md`.

## Spec-driven workflow

Features are developed spec-first under `specs/NNN-*/` via the speckit skills
(`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`). `CLAUDE.md` is
auto-generated from feature plans; put durable manual guidance in its `MANUAL ADDITIONS` block or
here in `AGENTS.md` (which speckit does not regenerate).
