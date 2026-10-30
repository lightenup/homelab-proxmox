# Derived Hermes image with Mnemosyne baked in at BUILD time (the spike's `int` network has
# no egress, and prod's egress allowlist would block a runtime pip install the same way).
# The pinned image ships no pip/uv, so uv is copied in for the build step only.
ARG HERMES_TAG=v0.21.6
FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM nousresearch/hermes-agent:${HERMES_TAG}
COPY --from=uv /uv /usr/local/bin/uv
# [mcp] adds the MCP server (mnemosyne mcp); no [llm] extra, so no llama-cpp and no
# huggingface_hub: the local-GGUF fallback cannot download anything, it can only fail.
RUN uv pip install --python /opt/hermes/.venv/bin/python --no-cache \
      "mnemosyne-memory[embeddings,mcp]==4.0.0" "mnemosyne-hermes==0.7.7" \
 && rm /usr/local/bin/uv \
 && /opt/hermes/.venv/bin/python -c "import mnemosyne, mnemosyne_hermes; print('mnemosyne', mnemosyne.__version__ if hasattr(mnemosyne,'__version__') else '?')"
