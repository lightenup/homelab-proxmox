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
