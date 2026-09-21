# ~~An expired PAT silently disarmed every PROD apply for 69 days~~ — RESOLVED

**Status**: **RESOLVED 2026-09-21**, by deleting the secret rather than rotating it.
**Impact while live**: `lxc-apply-prod.yml` failed at its first step for any service, any ref.
No production change was possible through the gated pipeline. Nothing alerted.

## What happened

The first PROD apply attempted since 2026-07-14 failed immediately:

```
ERROR: Failed to list artifacts for run_id=35565947104 (HTTP 401).
{ "message": "Bad credentials", "status": "401" }
```

`lxc-apply-prod.yml`'s first step fetches the promotion metadata artifact from the
corresponding promote run, using:

```yaml
GH_TOKEN: ${{ secrets.GH_ACTIONS_READ_TOKEN || github.token }}
```

`GH_ACTIONS_READ_TOKEN` is a fine-grained PAT, added 2026-01-12 (`d7f86a6`, "ci: allow PAT
fallback for cross-run artifact fetch"). It had **expired**. Note the failure is **401**, not
403 — an absent secret would have fallen through to `github.token`; a present-but-dead one
does not.

## This was the second occurrence, and the previous fix caused this one

`gh secret list` reports `GH_ACTIONS_READ_TOKEN` last updated **2026-06-20T20:07:15Z**. The
PROD apply history either side of that timestamp:

| time (UTC) | event |
|---|---|
| 2026-06-20 19:54 | PROD apply — **failure** |
| 2026-06-20 20:07:15 | `GH_ACTIONS_READ_TOKEN` updated |
| 2026-06-20 20:08 | PROD apply — **success**, 60 seconds later |

Someone hit this identical wall three months ago, rotated the token, and shipped. **That
rotation armed the fuse that fired today**: 2026-06-20 + 90 days (the fine-grained PAT
default ceiling) = **2026-09-18**. Today is day 93.

Corroborated from the other side: the last successful PROD apply was **2026-07-14**, day 24
— comfortably inside validity.

A cluster of six failures on 2026-02-23 followed by a success fits the same signature, and
2026-02-23 → 2026-06-20 is 117 days. **Unconfirmed** — GitHub retains logs ~90 days and
February's are gone. If it holds, this is the third occurrence of one bug.

## Why it went unnoticed for 69 days

Three things compounded, and only the first is about the token.

1. **Nothing exercises the path.** Zero `lxc-apply-prod` runs between 2026-07-14 and
   2026-09-21. The only scheduled workflow is `nightly-deeper-verification.yml`
   (`0 3 * * *`), which references neither `lxc-apply-prod`, `promotion_run_id`, nor
   `GH_ACTIONS_READ_TOKEN`.
2. **The break is in the apply half only.** `lxc-promote-prod.yml` still runs green end to
   end — it produces the artifact, it does not consume one. Every signal a human sees during
   promotion stayed healthy.
3. **The LAB path had become the de facto deploy mechanism.** `064` shipped 2026-09-19/20
   entirely through `lxc-deploy-lab.yml`; so did `065` (Hermes) on 2026-09-21. That works
   because of [`067`](./067-lab-prod-same-address-space.md): `lab.tfvars.template` and
   `prod.tfvars.template` are byte-identical, so a LAB apply provisions the real LXC at its
   production address.

## The part worth keeping

**`067` has quietly made the gated PROD pipeline vestigial, and that is why its decay was
invisible.** `067` is currently filed as a safety problem — a run labelled LAB can change
production. This is its mirror image and the concrete second symptom that note asks for: because
LAB reaches production, the reviewed, evidence-producing, confirmation-gated chain can rot for
two months and nobody finds out, because the *unreviewed* path works fine.

A gate nobody walks through is not a gate. The estate has two deploy paths; the one with all
the safety properties is the one that stopped working, and the one still in daily use is the one
`067` was raised about.

## The fix

**Deleted the secret. Did not rotate it.**

```bash
gh secret delete GH_ACTIONS_READ_TOKEN
```

With the secret gone, `${{ secrets.GH_ACTIONS_READ_TOKEN || github.token }}` falls through to
`github.token`, which is minted per-run and **cannot expire**. Verified immediately afterwards:
run `35570688286` passed every step including `Fetch promotion metadata artifact`.

So the PAT was **never required** for this repo — the org does not restrict cross-run artifact
reads. It was added 2026-01-12 as a defensive fallback for a policy that does not apply here,
and in nine months it contributed nothing except two outages. Rotating it again would have
rebooked this failure for roughly **2026-12-20**.

The workflow's inline comment and its 403 remediation text are still correct and worth keeping
for anyone who forks this into an org that *does* restrict it — the 401/403 distinction is what
tells you which world you are in.

## Still open

- **Nothing proves the PROD chain still works.** The fix removes this failure mode, but the
  underlying condition — a production path exercised every few months, whose breakage surfaces
  only when someone needs it — is unchanged. A cheap periodic smoke of `lxc-apply-prod` against
  a no-op service, or folding the artifact fetch into the nightly, would convert "discovered
  when you need it" into "discovered next morning".
- **`067` deserves re-reading with this as evidence**, alongside the note already there from
  the `072` incident.
