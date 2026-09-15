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
