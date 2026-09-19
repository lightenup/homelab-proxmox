# Fault-injecting the llm-router doctor

`scripts/healthcheck/llm-router-doctor.py` has never been observed to fail
against a real gateway. It was written on the dev Mac, which Zscaler keeps off
the tailnet, so every check has only ever been *run* — not *tested*.

That distinction is not pedantry. On the sibling setup a doctor written
specifically to catch inert configuration **shipped with the exact bug it
existed to catch**: its environment check inherited the variable from its calling
process, so it passed even with the variable deleted from the file that defined
it. It reported success and could never have reported anything else. The bug was
found by trying to break it, not by running it.

**This doctor has now had two such bugs, and the second is the sharper lesson.**

The first: its context check read `os.environ["OLLAMA_CONTEXT_LENGTH"]` — the environment
of whatever box runs the doctor, which is the LXC or a laptop, never the Mac it is asking
about. Caught by review.

The second, found 2026-09-15 by trying to break it: the replacement check asked the Mac
properly, but `aliases_from_vars()` never parsed `provider_model` or `context_window`, so
its set of models-to-assert was always empty and it returned `"nothing to assert"` as a
**PASS**. It was a second reachability check wearing a residency check's label, and it
could not have reported anything else. Reading the code did not catch it; neither did
running it, because it was green and green was the expected answer. What caught it was
asking what the check would do if the thing it guards were broken.

The lesson is the one this document opens with, now demonstrated twice on this very file:
**a check that has never failed is a check that has never been tested** — and the failure
mode is not a crash, it is a green tick that means nothing.

So: break each check once and confirm it goes red. Which environment each row belongs
to is in the table below.

## Order

Do these after a successful deploy, when the checks in scope are green — a red
baseline proves nothing. Restore after each one before moving to the next.

**Revised 2026-09-15 for oMLX.** Rows 1–4 targeted Ollama over the tailnet; the local
tier is now oMLX over the LAN, so the levers differ — stop the oMLX server rather than
quitting Ollama.app, unpin a model rather than unsetting `OLLAMA_KEEP_ALIVE`. Rows 5–7
are unchanged. **Rows 1–4 need the Mac reachable and therefore need PROD**: LAB sits on
`192.168.20.0/24`, mDNS does not cross subnets, and the local tier is unreachable there
by design (`deploy-plan.md` § *LAB and the local tier*). Rows 5 and 7 run in LAB today.

| # | Break | Should fail | Defends | env |
|---|---|---|---|---|
| 1 | Stop the oMLX server on the Mac | `oMLX reachable on the LAN` | FR-016 | PROD |
| 2 | …and while it is stopped, call all three aliases | **nothing should fail** — this is SC-001 | SC-001 | PROD |
| 3 | Unpin an aliased model, let it evict | `oMLX serves the declared context, resident` | FR-016 | PROD |
| 4 | Serve an aliased model below its declared `context_window` | the same check, on its context half | FR-016 / SC-009 | PROD |
| 5 | Call the doctor with a key that has no budget | `calling key carries a budget` | SC-010 | LAB |
| 6 | Add a raw provider model ID to the config and deploy | `raw provider model IDs are not addressable` | FR-002 | LAB |
| 7 | Revert `enable_pre_call_checks` to false | `enable_pre_call_checks is set` | SC-009 | LAB |

### Rows 3 and 4 were already injected — against a simulated oMLX

Done 2026-09-15, before any deploy, because the check turned out to be unfailable and a
simulator was the only way to prove the fix without the Mac. A stub served
`/admin/api/models` in four states; the check behaved as:

| scenario | result |
|---|---|
| both models loaded + pinned at 131072 (plus an unrelated 3B at 32k) | **PASS** |
| one aliased model loaded but unpinned | **FAIL** — row 3 |
| one aliased model evicted | **FAIL** |
| one aliased model serving 32768 against a declared 131072 | **FAIL** — row 4 |

The unrelated 3B not causing a failure matters: an earlier version asserted over every
resident model and went red on checkpoints outside its remit, which trains people to
ignore the doctor. Re-run rows 3 and 4 against the real Mac in PROD — a simulator proves
the logic, not the endpoint's actual shape.

### Notes on the ones that are not obvious

**#2 is the important one and it is inverted.** With oMLX stopped, the doctor
should still report every alias answering — that is the fallback working.
If a check goes red here, the fallback is broken, not the doctor. This is the
cheap half of SC-001; the expensive half is `T035`, under *What cannot be
fault-injected* below.

**LAB gives you #1 and #2 for free, permanently.** The local tier is unreachable there
by design, so LAB's steady state *is* the row-1 break. That makes `every alias answers
right now` the check to watch on the LAB run — it is row 2, arriving without being
staged. What LAB cannot do is *restore*, which is why rows 3 and 4 need PROD.

**#3 and #4 are one check with two failure modes.** A model serving 32768 while
the gateway believes 131072 truncates silently rather than escalating a tier,
which is SC-009 failing quietly. A model that has been evicted takes a cold load on
the next request and can trip the gateway timeout into a *false* fallback — the
gateway reports the Mac down when it is merely slow. Both are invisible to a
liveness check.

**Pinning, not residency, is what row 3 asserts.** A model that is loaded but unpinned
is evictable a moment later, so passing on `loaded` alone reports a state with no shelf
life. The check was corrected on 2026-09-15 to fail on unpinned rather than merely
annotate it.

**#6 changes config and needs a deploy**, so batch it with another change rather
than doing a round trip for it alone.

## What cannot be fault-injected from a script

**SC-001 with the Mac powered off (`T035`).** This is a genuinely different
failure mode from a stopped server (`T034`) and the handoff flags it as one of
the three things most likely to bite: **a stopped server refuses fast, a
vanished LAN host can hang to timeout.** (The transport changed from tailnet to
LAN; the distinction did not — an absent host still black-holes rather than
refusing.) A hang is not a failure the doctor can distinguish from slowness, and it is the case LiteLLM's routing-pool defect
shows up in. Power the Mac off, run the doctor, and watch the wall clock — if it
hangs rather than falling back, that is the result.

**SC-013, the silent-green case.** Every backend failing with *no client traffic
flowing* must still raise an alert within one canary interval. The doctor
generates traffic by definition, so it cannot observe this; that is what the
canary timer is for.

**SC-011**, background health-check spend under 1% of a week's total, needs a
week of real operation. `T062` is correctly marked as not verifiable at deploy
time.

## Recording it

Append results to `specs/064-llm-router/HANDOFF.md` or a sibling note — which
checks were injected, which went red, and which did not. A check that failed to
fail is a finding, not a formality, and is worth more than the green run that
preceded it.

---

# Executed 2026-09-19, against the deployed gateway

Run against `192.168.1.220` after the deploy went green, with a 13/13 baseline before
and after. Restored between rows. Two defects found, both fixed and re-verified; one
requirement is still not fully met and is recorded as open rather than closed.

**The table's environment column is obsolete.** It assigns rows to LAB or PROD on the
assumption they are different networks. They are not — `lab.tfvars.template` and
`prod.tfvars.template` are byte-identical for this service, so every row ran against the
one gateway at `192.168.1.220`, which shares the Mac's subnet. See RUNBOOK.md's
correction banner.

| # | row | result |
|---|---|---|
| 1 | stop the Mac's LiteLLM | ✅ **red as designed** — both local-tier checks fail (`URLError`) |
| 2 | …and call all three aliases | ❌ **FAILED: hung past 300s, returned nothing.** Fixed; now a bounded HTTP 500 naming the model group |
| 3 | unpin an aliased model | ⚠️ **not injectable** — needs the oMLX admin credential, and the check no longer exists here |
| 4 | serve below the declared `context_window` | ⚠️ **not injectable** — same check, same reason |
| 5 | call the doctor with a budget-less key | ✅ **red as designed** — "calling key has NO max_budget — SC-010 cannot hold" |
| 6 | make a raw provider model ID addressable | ❌ **FAILED: the check could not fail, and the gap it hid was real.** Both fixed |
| 7 | revert `enable_pre_call_checks` to false | ✅ **red as designed** — 4/5, naming SC-009 |

## Row 2 — the hang, and why the doc's premise was wrong

With the Mac's LiteLLM stopped, every alias hung past 300s and returned **nothing**: no
status, no error, no fallback. Not slow — silent.

The cause is the Mac's MDM-enforced **stealth mode**, the same control behind the mDNS
finding: it DROPS the SYN rather than refusing it.

| from the LXC, nothing listening on :4000 | result |
|---|---|
| Mac (stealth mode on) | hung the full 25s test window |
| `pve` (stealth mode off) | `Connection refused` in **0.001s** |

So this document's premise — *"a stopped server refuses fast, a vanished LAN host can hang
to timeout"* — **does not hold on this Mac. Both hang.** T034 and T035 are the same test
here, and the hang is the only failure mode rather than the rare one. That also removes
most of T035's distinct value: powering the Mac off exercises the same blackhole a stopped
container already produces.

**It silently defeated the health checking too.** A background check that blackholes never
completes, so it never reports a failure, so `allowed_fails` never accrues and the
deployment is never ejected. Eight minutes after the backend died, requests still hung.
`background_health_checks: true` was configured and **inert** — the exact class of bug this
doctor exists to catch, sitting underneath the doctor.

Fixed with an explicit per-deployment `timeout` (180s, `llm_router_request_timeout`) and an
explicit `num_retries: 0`, since the caller's wait is `timeout x (1 + num_retries)` and the
upstream default is not 0. Re-verified by blackholing the container's path to the Mac with
a `DOCKER-USER` DROP rule — the same failure mode without taking the Mac down:

```
call 1: http=500 total=136.4s
call 2: http=500 total=135.1s
call 3: http=500 total=135.1s
  {"error":{"message":"litellm.InternalServerError: ... Connection error..
             Received Model Group=hermes-fast\nAvailable Model Group Fallbacks=None"}}
```

### Resolved: why nothing was ever ejected

First measurement after the timeout fix: ~135s on **every** request, not just the first.
The dead deployment was never ejected, and our own settings were the reason. Setting
`allowed_fails` at all takes the legacy path in LiteLLM's
`router_utils/cooldown_handlers.py`:

```python
current_fails = failed_calls.get_cache(key=deployment) or 0   # TTL = cooldown_time
updated_fails = current_fails + 1
if updated_fails > allowed_fails: return True                 # cooldown
```

The failure **counter** is cached with a TTL of `cooldown_time`. A threshold above 0 is
therefore only reachable if failures arrive closer together than `cooldown_time`. Each
failure took a full request timeout (~135s) while `cooldown_time` was 60s, so the counter
expired between failures, never climbed past 1, and `allowed_fails: 2` could not be
reached. Configured, plausible, unreachable — the same class as the inert health checks
above, from the opposite direction.

Dropping `allowed_fails` entirely is worse: the v2 path only cools a single-deployment
model group at `percent_fails == 1.0` **and** >= 1000 requests/minute
(`SINGLE_DEPLOYMENT_TRAFFIC_FAILURE_THRESHOLD`), which a homelab never reaches — and every
`hermes-*` group has exactly one deployment since the metered tiers were dropped.

**`allowed_fails: 0`** cools the deployment down on the first failure. Measured end to end:

```
blackhole inserted
  call 1: http=500  134.7s   "Connection error.. Received Model Group=hermes-fast"
  call 2: http=429    0.048s "No deployments available... Try again in 60 seconds"
  call 3: http=429    0.030s
  call 4: http=429    0.031s
blackhole removed
  t+51s   http=200            recovered, no operator action
```

### SC-008, final state

| clause | result |
|---|---|
| a clear error attributing the failure to the unreachable backend | ✅ names the model group |
| never a hang | ✅ bounded and repeatable |
| rejoins within one health-check interval | ✅ **51s**, no operator action |
| within the health-check interval | ⚠️ holds for every request except the first |

The **first** request after an outage begins still costs one request timeout (~135s) —
that is the cost of discovering a blackhole, and it is irreducible without capping
`llm_router_request_timeout` below the length of a legitimate generation. Every request
after it, for the next `cooldown_time`, fails in ~0.03s. Left at 180s deliberately;
lowering it is a latency-versus-generation-length choice for the operator.

## Row 6 — a check that could not fail, hiding a real bypass

The check probed the literal `claude-sonnet-5`, a name that left the config when the
frontier tier was dropped. It was refused for **not existing** rather than for being a
provider ID, so it passed while testing nothing.

Behind it was a genuine FR-002 bypass:

| probed with a client key | before | after |
|---|---|---|
| `claude-sonnet-5` (what the check asked) | refused 400 | n/a — no longer probed |
| `fast`, `coder`, `reasoner` | refused 400 | refused |
| **`openai/fast`** (the declared `provider_model`) | **200, a real completion** | refused 401 |

A client could address the provider model directly, bypassing the alias and with it the
`context_window` and fallback behaviour the alias declares. Fixed by scoping client keys
with LiteLLM's `models` parameter — the same mechanism the Mac already applies to the key
it mints for this gateway — and the check now derives its probes from the declared
`provider_model` values, in both qualified and bare form, so it tracks the mapping instead
of a name frozen when it was written. Verified red before the fix, green after: "all 6
provider IDs refused".

## What still has not been exercised

- **Rows 3 and 4** (residency and declared context on oMLX). `/admin/api/models` needs an
  admin credential absent from `proxy/.env`, and the check it defended moved to the Mac
  side of RUNBOOK § 1, where it is a manual UI check. Pinning remains an **unverified
  assumption**.
- **SC-013**, the silent-green case — needs the canary timer to fire with no client
  traffic, which a doctor run cannot observe by definition.
- **SC-011**, health-check spend under 1% of a week — needs a week, and is moot while every
  tier is local and unpriced.
