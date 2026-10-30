# Spike 097: pinned Hermes Agent + the Hindsight provider's Python deps, installed at BUILD time
# (the runtime network has no egress). The plugin source itself is NOT baked in: it is mounted
# read-only at /opt/data/plugins/hindsight, the same pattern as prod's platforms/ntfy plugin.
#
# Stage 1 lets Hermes' own package manager resolve the plugin's declared deps against the
# pinned runtime; deps are only resolved on enable, and the config it writes stays in this stage
# (catalog entry hindsight @ d56c4ac, plugin 1.2.1, requires_hermes >=0.21.4).
# The Zscaler root is a build secret for the dev Mac's TLS interception only; it never
# reaches a layer. pve (prod) has no interception, so a prod build drops the secret.
FROM nousresearch/hermes-agent:v0.21.6 AS resolve
USER hermes
ENV HERMES_HOME=/tmp/hh
RUN --mount=type=secret,id=zca,uid=10000,required=false \
    cat /etc/ssl/certs/ca-certificates.crt $( [ -f /run/secrets/zca ] && echo /run/secrets/zca ) > /tmp/ca.pem && \
    export SSL_CERT_FILE=/tmp/ca.pem GIT_SSL_CAINFO=/tmp/ca.pem REQUESTS_CA_BUNDLE=/tmp/ca.pem && \
    mkdir -p /tmp/hh && \
    hermes plugins install hindsight --ref d56c4acdf59c41957613d399094cdf8c489b060c --yes-deps --enable && \
    SP=$(ls -d /tmp/hh/installs/*/environments/*/venv/lib/python3.14/site-packages) && \
    mkdir -p /tmp/deps && cd "$SP" && \
    cp -a aiohttp_retry aiohttp_retry-2.9.1.dist-info \
          hindsight_client hindsight_client_api hindsight_client-0.10.3.dist-info \
          hindsight_embed hindsight_embed-0.10.3.dist-info /tmp/deps/

FROM nousresearch/hermes-agent:v0.21.6
COPY --from=resolve /tmp/deps/ /opt/hermes/.venv/lib/python3.14/site-packages/
RUN /opt/hermes/.venv/bin/python -c "import hindsight_client, hindsight_embed, aiohttp_retry; print('hindsight deps ok')"
