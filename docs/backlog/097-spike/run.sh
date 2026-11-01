#!/usr/bin/env bash
# Usage: ./run.sh <candidate>   (needs runs/<candidate>/config.yaml and keys/spike.env)
# Drives dataset.json through Hermes: 5 multi-turn sessions, then 8 probes in fresh sessions.
set -euo pipefail
cd "$(dirname "$0")"
export DOCKER_HOST=unix://$HOME/.docker/run/docker.sock CANDIDATE=$1
set -a; . keys/spike.env; set +a
# prod-render: the image references rendered from the PROD pins (render-prod.sh).
if [ -f "runs/$1/build/images.env" ]; then set -a; . "runs/$1/build/images.env"; set +a; fi
EXTRA=(); [ -f compose.$1.yml ] && EXTRA=(-f compose.$1.yml)
DC=(docker compose -f compose.base.yml "${EXTRA[@]}")
OUT=results/$1; mkdir -p "$OUT" logs
echo "$1" > logs/RUN; echo startup > logs/RUN.phase
rm -f logs/injected.jsonl   # this run's injected recall blocks only (recall_from_injected.py)
"${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${DC[@]}" up -d --wait 2>&1 | tail -3
"${DC[@]}" config --images > "$OUT/images.txt"
# Per-candidate setup after start-up (prod-render: the banks, as the memory deploy creates them).
if [ -x "runs/$1/after-up.sh" ]; then "runs/$1/after-up.sh"; fi
sleep 15
# peak memory sampler
( while sleep 5; do docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep "^memspike-" | grep -v prep; done ) > "$OUT/mem.log" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null || true' EXIT
# Drive the gateway API server from inside the internal network, as Open WebUI does.
"${DC[@]}" exec -T llmproxy python -u /app/client.py "$1" > "$OUT/transcript.jsonl"
echo final > logs/RUN.phase
sleep 30   # let async writes/consolidation land
"${DC[@]}" cp dataset.json hermes:/tmp/dataset.json >/dev/null 2>&1 && "${DC[@]}" cp hermes/attribution.py hermes:/tmp/attribution.py >/dev/null 2>&1 \
  && "${DC[@]}" exec -T hermes python3 /tmp/attribution.py /tmp/dataset.json > "$OUT/attribution.jsonl" 2>&1 || true
# SC-001's retrieval leg for preference probes (gate.py): the preference's rank in the recall
# block injected into the probe's first request, before the probes' own answers were stored.
python3 recall_from_injected.py "$1" > "$OUT/recall.jsonl"
cp logs/injected.jsonl "$OUT/injected.jsonl" 2>/dev/null || true   # the evidence behind recall.jsonl
"${DC[@]}" logs --no-color > "$OUT/compose.log" 2>&1
python3 score.py "$1" | tee "$OUT/score.txt"
# FR-021 (spec 097): the gate's fingerprint travels with the results. Archive as
# results/<YYYY-MM-DD>-prod-render/ (README) so test_memory_harness_gate.py finds it.
# The verdict (gate.py) is what test_memory_harness_gate.py accepts; it exits non-zero on a fail.
if [ "$1" = prod-render ]; then
    cp runs/prod-render/fingerprint.txt "$OUT/fingerprint.txt"
    # SC-005 (097 T045): each client's turn format with its own key, read back by the other two,
    # in a bank of its own so the dataset's facts do not crowd the recall. gate.py reads the JSON.
    rm -f logs/porta/clients.json
    "${DC[@]}" exec -T llmproxy python -u /app/portability.py clients porta-clients \
        --clients hermes,open-webui,claude-code | tee "$OUT/portability.txt" || true
    cp logs/porta/clients.json "$OUT/portability.json" 2>/dev/null || true
    # T071 (research R-012): retired and edited turns stay so after the conversation goes on.
    rm -f logs/porta/durability.json
    "${DC[@]}" exec -T llmproxy python -u /app/portability.py durability durability \
        | tee "$OUT/durability.txt" || true
    cp logs/porta/durability.json "$OUT/durability.json" 2>/dev/null || true
    python3 gate.py "$1" | tee "$OUT/gate.txt"
fi
