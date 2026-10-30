# Honcho candidate (spike 097)

Pins: server ghcr.io/plastic-labs/honcho:v3.5.0 (API + deriver, same image), pgvector/pgvector:0.8.1-pg17.
Hermes plugin = catalog entry `honcho` @ e2d2aba182862deeb846e5cd4a30a41bce0ed82a (plugin 1.0.0) with
honcho-ai 2.7.0 baked into memspike-hermes-honcho:v0.21.6-ho1.0.0 (image/Dockerfile). Plugin source in
./plugin, mounted :ro at /opt/data/plugins/honcho. No Redis (cache off).

Config: server = honcho/config.toml (every LLM module -> llmproxy `coder`, embeddings -> `embed` at 1024
dims; summary + dream OFF; deriver batch 512 tokens / 60 s). Client = runs/honcho/honcho.json
(workspace-scoped JWT, dialectic every 3rd turn at level minimal, recallSync on). JWT secret in
runs/honcho/secret.env; admin JWT in runs/honcho/admin.jwt (both 600, regenerate = new deployment).

tiktoken BPE files are pre-seeded in ./tiktoken (sha1(url) names): Honcho downloads o200k_base from
openaipublic.blob.core.windows.net at startup otherwise and crashes with no egress.

Rebuild the image:  cd image && docker build --secret id=zca,src=zscaler.pem -t memspike-hermes-honcho:v0.21.6-ho1.0.0 .
Run:               ./run.sh honcho
Inspect after run: runs/honcho/inspect.sh [project]
