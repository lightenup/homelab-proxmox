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

**This doctor already had one such bug.** Its context check read
`os.environ["OLLAMA_CONTEXT_LENGTH"]` — the environment of whatever box runs the
doctor, which is the LXC or a laptop, never the Mac it is asking about. It now
probes Ollama's `/api/ps` instead. That one was caught by review; the rest have
not been caught by anything.

So: during the first LAB deploy, break each check once and confirm it goes red.
A check that has never failed is a check that has never been tested.

## Order

Do these after the first successful deploy, when everything is green — a red
baseline proves nothing. Restore after each one before moving to the next.

| # | Break | Should fail | Defends |
|---|---|---|---|
| 1 | Stop Ollama on the Mac | `Ollama reachable on the tailnet` | FR-016 |
| 2 | …and while it is stopped, call all three aliases | **nothing should fail** — this is SC-001 | SC-001 |
| 3 | `launchctl unsetenv OLLAMA_CONTEXT_LENGTH`, restart Ollama | `Ollama serves the declared context` | FR-016 / SC-009 |
| 4 | `launchctl setenv OLLAMA_KEEP_ALIVE 0`, wait for unload | `…resident` half of the same check | FR-016 |
| 5 | Call the doctor with a key that has no budget | `calling key carries a budget` | SC-010 |
| 6 | Add a raw provider model ID to the config and deploy | `raw provider model IDs are not addressable` | FR-002 |
| 7 | Revert `enable_pre_call_checks` to false | `enable_pre_call_checks is set` | SC-009 |

### Notes on the ones that are not obvious

**#2 is the important one and it is inverted.** With Ollama stopped, the doctor
should still report every alias answering — that is the fallback working.
If a check goes red here, the fallback is broken, not the doctor. This is the
cheap half of SC-001; the expensive half is #8 below.

**#3 and #4 are one check with two failure modes.** A model serving 4096 while
the gateway believes 32768 truncates silently rather than escalating a tier,
which is SC-009 failing quietly. A model that has unloaded takes a cold load on
the next request and can trip the gateway timeout into a *false* fallback — the
gateway reports the Mac down when it is merely slow. Both are invisible to a
liveness check.

**#6 changes config and needs a deploy**, so batch it with another change rather
than doing a round trip for it alone.

## What cannot be fault-injected from a script

**SC-001 with the Mac powered off (`T035`).** This is a genuinely different
failure mode from a stopped daemon (`T034`) and the handoff flags it as one of
the three things most likely to bite: **a stopped daemon refuses fast, a
vanished tailnet peer can hang to timeout.** A hang is not a failure the doctor
can distinguish from slowness, and it is the case LiteLLM's routing-pool defect
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
