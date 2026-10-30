# Hindsight candidate (spike 097)

Pins: server ghcr.io/vectorize-io/hindsight:1.1.0-slim, pgvector/pgvector:0.8.1-pg17,
Hermes plugin = catalog entry `hindsight` @ d56c4acdf59c41957613d399094cdf8c489b060c (plugin 1.2.1,
requires_hermes >=0.21.4) with hindsight-client 0.10.3, hindsight-embed 0.10.3, aiohttp-retry 2.9.1
baked into memspike-hermes-hindsight:v0.21.6-hs1.2.1 (image/Dockerfile). Plugin source mounted :ro.

Variants (run with ./run.sh <name>):
  hindsight         concise extraction, observations + auto-consolidation off, recall all fact types
  hindsight-chunks  zero LLM: verbatim chunks, embeddings + rerank only
  hindsight-full    upstream defaults: observations + consolidation after each retain, recall = observations

Rebuild the image:  cd image && docker build --secret id=zca,src=zscaler.pem -t memspike-hermes-hindsight:v0.21.6-hs1.2.1 .
Inspect after a run: runs/hindsight/inspect.sh memspike <variant>
