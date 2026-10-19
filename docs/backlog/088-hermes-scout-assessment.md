# Backlog: Hermes assesses each promising model against the lineup's roles

**Status**: In progress — raised 2026-10-19.
- The script side is merged in `local-llm` (PR #3).
- The job is installed on PROD.
- The probe key is in the `scout-probe-key` branch.
**Order**: After `083` (the agent runtime it runs on). Independent of everything else.

## Why this exists

The model scout (`083` FR-019) is a script-only job: every morning it reports new MLX models
that would fit the Mac, with a verdict and the commands to gate them. It cannot tell the owner
whether a candidate could actually replace anything. Since `local-llm` PR #2, the scout's JSON
report carries the four roles the lineup serves (`coder`, `reasoner`, `agent`, `long`), each with
its incumbent, the measured bar to beat, and which roles the candidate's config rules out. Turning
that into "worth the Mac's hours or not" is a judgement, so it needs an agent job.

An agent job needs the Mac, because every model behind Hermes runs on it. Hermes cannot wait for
the Mac on its own:
- Its re-run ladder (5, 15, 30 min, `cron/unreachable_retry.py`) fires only on transport errors
  to the provider.
- The provider is the llm-router, which stays up and answers 500 or 429 while the Mac sleeps.
- So a plain agent job fails for the day.

## Current state (verified 2026-10-19)

- `model-scout` runs daily at 07:30, no-agent, delivering to ntfy `hermes`.
  - It ran on time on 10-18 and 10-19, and both runs were `silent (empty output)`. Nothing was
    new, and a quiet run printed nothing.
  - `local-llm` PR #2 makes it print one line instead.
- Hermes' outbound traffic is allowlisted in the container firewall: the llm-router `:4000`,
  market-model and the Hub. Prometheus and the Mac are rejected, so the job cannot check
  `up{job="llm-queue"}`. The router is the only path to the Mac.
- Agent jobs with a `--script` (not `--no-agent`): empty stdout is a silent success with **no
  model call** (`cron/scheduler_prompt.py:315`, `cron/scheduler.py:2307`). Non-empty stdout
  becomes "## Script Output" in the prompt.
- `last_run_at` is stamped when a run completes (`cron/jobs.py:2372`).
- **Job scripts get a cleaned environment** (`build_subprocess_env`, `cron/scheduler_script.py`).
  - `AUXILIARY_HERMES_API_KEY` is stripped on purpose (R-004), so a script cannot use the agent's
    gateway key.
  - Found the hard way: the first two PROD ticks (2026-10-19 08:45, 09:00) probed with an empty
    key and got 401 from the router. The gate failed safe (silent), so nothing ran.
  - A test with `docker exec` had passed, because that gets the full container environment.
- `hermes cron create` and `edit` have no toolset option. The job's `enabled_toolsets` can only be
  set in `jobs.json`, so an agent job gets the `hermes-cron` bundle by default, shell and web
  included.

## Requirements

- **FR-001** The assessment is a Hermes agent job installed as job content (`083` FR-019/FR-020):
  - name `scout-assess`, schedule `*/15 * * * *`
  - model `hermes-deep` (the Mac's `reasoner`, thinking on)
  - delivery ntfy `hermes`, with failures following the delivery target (`083` FR-013)
- **FR-002** Its script is `local-llm`'s `scout/hermes-assess.sh`, installed as a wrapper that
  sets `SCOUT_ROUTER_URL` and execs the clone's copy. The router address stays out of the public
  repo, and changes arrive with `git pull`.
- **FR-003** A tick makes no model call unless a promising family is pending **and** the Mac
  answers a 1-token probe through the router within 20 s. While the Mac is away, every tick is
  silent.
- **FR-004** The first tick after the Mac answers is the retry. There is no daily window to miss.
- **FR-008** The probe uses its own router client, `scout_probe`:
  - rpm 2 and $1 per 30 days, so a leaked copy is worth little; the agent's terminal sees it too.
  - The key reaches the script through `hermes_agent_env_passthrough` (R-004).
  - The installed wrapper sets `SCOUT_ROUTER_KEY_ENV=LLM_ROUTER_CLIENT_SCOUT_PROBE_KEY`.
- **FR-005** One family per run, so one phone message per candidate. A family is assessed once:
  - It is marked done when the job's next completed run is `ok`.
  - Otherwise it is handed over again, and given up after 3 attempts, so a broken path cannot
    notify every 15 minutes.
- **FR-006** `model-scout.sh` is reinstalled as a wrapper that execs the clone's
  `scout/hermes-cron.sh`. That script writes the JSON report the assessment reads.
- **FR-007** The agent works from the handed-over JSON only. It does not browse, does not read
  model cards, and does not run `next_steps` (`local-llm` `scout/assess.md`).

## Success criteria

- **SC-000** The probe succeeds from a real cron tick, not from `docker exec`. The router logs a
  200 for the `scout_probe` key.
- **SC-001** With the Mac asleep, `hermes cron runs scout-assess` shows only silent ticks, and
  the router logs no `hermes-deep` traffic from the agent beyond the probe.
- **SC-002** After the Mac wakes with a family pending, one assessment reaches the phone within
  two ticks plus the run time. Measured on the Mac: about 8 minutes for `reasoner`.
- **SC-003** The family shows `assessed` in `$HERMES_HOME/state/scout_assess.json` on the
  following tick, and is not assessed again.
- **SC-004** A forced failure (an unreachable model name) produces at most 3 failure notices for
  one family.

## Out of scope / later

- **Restricting the job's toolsets.** No CLI option exists. Either set `enabled_toolsets` in
  `jobs.json` by hand, or raise it upstream. Until then, FR-007 rests on the prompt.
- **A Prometheus-based "Mac up for 10 minutes" check.** It needs an egress rule for Hermes to the
  monitoring host. The probe makes it unnecessary.
- **Backlog `075`** (the first request after the Mac leaves hangs). The probe's 20 s timeout
  bounds it here, but it does not fix it.
