# 097 memory bake-off harness (2026-10-30)

Reusable harness behind the spike results in [`../097-hermes-long-term-memory.md`](../097-hermes-long-term-memory.md).
FR-021 makes it the quality gate before a PROD promotion that changes memory (SC-001 to SC-005).
It runs on the dev Mac: since `067` the LAB rehearsal cannot reach the gateway.

## What it does

- Runs the pinned `nousresearch/hermes-agent:v0.21.6` with the PROD-shaped, read-only `config.yaml`
  (`hermes/config.base.yaml` plus a per-candidate memory section in `runs/<candidate>/config.yaml`).
- Drives `dataset.json` through the gateway's API server the way Open WebUI does
  (`llmproxy/client.py`: full history per turn, no session header): 9 conversations of a fictional
  persona in mixed Norwegian and English, then 16 probes, each in a fresh conversation.
- Puts every container on an internal Docker network whose only exit is `llmproxy/logproxy.py`, a
  logging forwarder to LiteLLM. Any other egress fails; every LLM, embedding and rerank call is
  logged per candidate and phase to `logs/calls.jsonl` (no prompt or response bodies).
- Scores with `score.py` (keyword match, negations stripped) plus `overrides.json` for probes judged
  by hand, and records which tools answered each probe from the agent's `state.db`
  (`hermes/attribution.py`).

## Run

```sh
# one LiteLLM key, never committed
echo "LITELLM_SPIKE_KEY=sk-..." > keys/spike.env && chmod 600 keys/spike.env
./run.sh none                       # built-in memory only
./queue.sh holographic hindsight-chunks honcho   # one at a time; each run tears down the last
```

Candidates with their own services layer `compose.<candidate>.yml` over `compose.base.yml`.
`hindsight-chunks` and `hindsight-full` are symlinks to `compose.hindsight.yml`; the variant is in
`runs/<variant>/server.env`.

## The FR-021 gate: `prod-render`

The quality gate before a PROD promotion that changes memory (spec 097 FR-021, research R-017,
quickstart § 1). It runs the production configuration, not a hand-written one:

```sh
./render-prod.sh                  # renders the Ansible templates, fetches the pinned plugin
./run.sh prod-render              # pinned stock images, shim and policy mounted read-only
mv results/prod-render "results/$(date +%F)-prod-render"   # keep gate.json and fingerprint.txt
```

`run.sh` ends with `gate.py`, which writes `gate.json` (SC-001 to SC-004, the images that ran,
the fingerprint) and exits non-zero on any fail. A probe that misses its keywords prints a
`review <id> sha256=<digest>` line; judge it by hand, record
`{"pass": true|false, "answer_sha256": "<digest>"}` under `prod-render` in `overrides.json`, and
re-run `python3 score.py prod-render > results/prod-render/score.txt && python3 gate.py prod-render`.
An override applies to that exact answer only.

- `render-prod.sh` renders `roles/memory/templates/{server.env,db.env,clients.json}.j2` and
  `roles/hermes/templates/hindsight-config.json.j2` with `ansible localhost -m template`, the PROD
  group vars and role defaults, and harness-local keys in `runs/prod-render/secret.env`. Two values
  differ from PROD: the gateway (`llmproxy:4000`) and the plugin's `api_url`
  (`http://hindsight:8888`, no Caddy here). The plugin and its three packages come from the same
  pins and checksums as `roles/hermes/tasks/memory_plugin.yml`.
- `llmproxy` maps the gateway aliases `hermes-embed` and `hermes-rerank` to the Mac's `embed` and
  `rerank` (`MODEL_MAP`), as the gateway does, and logs a short hash of each caller's key.
- `runs/prod-render/fingerprint.txt` hashes the pins and files that decide memory behaviour.
  `python/tests/guardrails/test_memory_harness_gate.py` fails until a committed
  `results/*-prod-render/fingerprint.txt` matches the current configuration.
- `runs/prod-render/after-up.sh` creates the `owner` and `deploy-probe` banks with the admin key, as
  the memory deploy does (`roles/memory/tasks/bank.yml`); only `admin` may create a bank.
- `keys/spike.env`: a virtual key minted on the Mac's LiteLLM (`/key/generate` with the master key
  from `~/Development/private/local-llm/proxy/.env`), limited to `coder`, `embed` and `rerank`.
- Generated files (`runs/prod-render/build/`, `secret.env`, `fingerprint.txt`) are git-ignored.

## Not in the repo

Generate or fetch locally before a run:

- `keys/spike.env` (LiteLLM key) and `runs/*/secret.env`, `runs/honcho/admin.jwt` (random per run).
  The `api_key`/`apiKey` fields in `runs/*/hindsight-config.json` and `runs/honcho/honcho.json` are
  placeholders.
- Derived images: build from `mnemosyne/`, `hindsight/image/`, `honcho/image/` (see each README).
  The Hindsight and Honcho Dockerfiles take the corporate root CA as a build secret on the dev Mac;
  not needed on `pve`.
- Plugin sources (`hindsight/plugin/`, `honcho/plugin/`) come from the Hermes plugin catalog at the
  commits pinned in the READMEs; Honcho's tokenizer files (`honcho/tiktoken/`) from
  `openaipublic.blob.core.windows.net` (Honcho downloads them at startup otherwise).

## Results

`results/<candidate>/`: `score.txt`, `transcript.jsonl` (all answers), `attribution.jsonl`,
`mem.log`, `inspect.txt` (store contents after the run). `results/none-run1/` is the first baseline,
`results/hindsight-full/ABORTED` explains the stopped run, `results/hindsight-portability/` the
second-client and export test, `results/calls.jsonl` the full proxy log. The data is synthetic.
