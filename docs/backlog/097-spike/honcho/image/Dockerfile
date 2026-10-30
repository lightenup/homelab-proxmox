# Spike 097: pinned Hermes Agent + the Honcho provider's Python deps, installed at BUILD time
# (the runtime network has no egress). The plugin source is NOT baked in: it is mounted
# read-only at /opt/data/plugins/honcho, the same pattern as prod's platforms/ntfy plugin.
#
# Stage 1 lets Hermes' own package manager resolve the plugin's declared deps against the
# pinned runtime (catalog entry honcho @ e2d2aba, plugin 1.0.0: honcho-ai>=2.2.0,<3, httpx).
# Only honcho-ai is new; httpx is already in the base venv. The Zscaler root is a build secret
# for the dev Mac's TLS interception only and never reaches a layer.
FROM nousresearch/hermes-agent:v0.21.6 AS resolve
USER hermes
ENV HERMES_HOME=/tmp/hh
RUN --mount=type=secret,id=zca,uid=10000,required=false \
    cat /etc/ssl/certs/ca-certificates.crt $( [ -f /run/secrets/zca ] && echo /run/secrets/zca ) > /tmp/ca.pem && \
    export SSL_CERT_FILE=/tmp/ca.pem GIT_SSL_CAINFO=/tmp/ca.pem REQUESTS_CA_BUNDLE=/tmp/ca.pem && \
    mkdir -p /tmp/hh && \
    hermes plugins install honcho --ref e2d2aba182862deeb846e5cd4a30a41bce0ed82a --yes-deps --enable && \
    SP=$(ls -d /tmp/hh/installs/*/environments/*/venv/lib/python3.14/site-packages) && \
    mkdir -p /tmp/deps && cd "$SP" && cp -a honcho honcho_ai-2.7.0.dist-info /tmp/deps/

FROM nousresearch/hermes-agent:v0.21.6
COPY --from=resolve /tmp/deps/ /opt/hermes/.venv/lib/python3.14/site-packages/
RUN /opt/hermes/.venv/bin/python -c "import honcho, importlib.metadata as m; print('honcho-ai', m.version('honcho-ai'))"
