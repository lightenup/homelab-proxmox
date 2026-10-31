#!/usr/bin/env bash
# Usage: ./render-prod.sh, then ./run.sh prod-render   (spec 097 FR-021, research R-017)
#
# Builds the prod-render candidate from the production Ansible templates, so the harness gate
# tests what PROD will run:
#   - memory server: roles/memory/templates/{server.env,db.env,clients.json}.j2
#   - agent plugin:  roles/hermes/templates/hindsight-config.json.j2
# rendered with `ansible localhost -m template`, the PROD group vars and role defaults, and
# harness-local keys. Only two values differ from PROD: the gateway (llm_router_ip/port ->
# llmproxy:4000, the logging proxy) and the plugin's api_url (-> http://hindsight:8888; there is
# no Caddy in the harness). The plugin and its three packages are fetched from the same pins and
# checksums as roles/hermes/tasks/memory_plugin.yml.
#
# Everything generated lands in runs/prod-render/build/ and runs/prod-render/secret.env, both
# git-ignored. runs/prod-render/fingerprint.txt is the FR-021 fingerprint
# (python/tests/guardrails/test_memory_harness_gate.py); run.sh copies it into the results.
set -euo pipefail
cd "$(dirname "$0")"
REPO=$(git rev-parse --show-toplevel)
# Needs PyYAML: the repo's venv (scripts/ci/python-tests.sh uses the same one).
PY=${PYTHON:-$REPO/.venv/bin/python}
export ANSIBLE_PYTHON_INTERPRETER=auto_silent ANSIBLE_LOCALHOST_WARNING=False
OUT=runs/prod-render
BUILD=$OUT/build
mkdir -p "$BUILD"
chmod 700 "$OUT" "$BUILD"

# 1. Harness-local keys, generated once. Never real vault values.
if [ ! -f "$OUT/secret.env" ]; then
    (umask 077; python3 - > "$OUT/secret.env" <<'EOF'
import secrets
for name in ("memory_client_hermes_key", "memory_client_open_webui_key", "memory_client_claude_code_key",
             "memory_client_control_plane_key", "memory_admin_key", "memory_ui_access_key"):
    print(f"{name}=hmem_{secrets.token_urlsafe(32)}")
print(f"memory_db_password={secrets.token_urlsafe(24)}")
print(f"llm_router_client_memory_key=sk-harness-{secrets.token_urlsafe(16)}")
EOF
    )
fi
(umask 077; python3 -c 'import json,sys; print(json.dumps(dict(l.strip().split("=",1) for l in open(sys.argv[1]) if "=" in l)))' \
    "$OUT/secret.env" > "$BUILD/secrets.json")

# 2. Render the production templates. -e has the highest precedence, so the two harness
# overrides come last.
ANSIBLE_ARGS=(
    localhost -c local -i localhost,
    -e "@$REPO/ansible/group_vars/services/vars.yml"
    -e "@$REPO/ansible/roles/memory/defaults/main.yml"
    -e "@$REPO/ansible/roles/hermes/defaults/main.yml"
    -e "@$BUILD/secrets.json"
    -e '{"llm_router_ip": "llmproxy", "llm_router_port": 4000, "hermes_memory_api_url": "http://hindsight:8888"}'
)
render() {
    ansible "${ANSIBLE_ARGS[@]}" -m ansible.builtin.template \
        -a "src=$REPO/ansible/roles/$1 dest=$PWD/$BUILD/$2 mode=0600" >/dev/null
}
render memory/templates/server.env.j2 server.env
render memory/templates/db.env.j2 db.env
render memory/templates/clients.json.j2 clients.json
render hermes/templates/hindsight-config.json.j2 hindsight-config.json
# The API container runs as uid 1000 and reads clients.json; on the dev Mac the bind mount maps
# the owner, so 0644 inside the 0700 build dir is enough.
chmod 644 "$BUILD/clients.json" "$BUILD/hindsight-config.json"

# 3. The plugin and its packages from the production pins (same checksums as the deploy).
"$PY" - "$REPO" "$BUILD" <<'EOF'
import hashlib, io, shutil, subprocess, sys, tarfile, zipfile
from pathlib import Path
import yaml

repo, build = Path(sys.argv[1]), Path(sys.argv[2])
version = yaml.safe_load((repo / "ansible/group_vars/services/vars.yml").read_text())["hermes_hindsight_plugin_version"]
defaults = yaml.safe_load((repo / "ansible/roles/hermes/defaults/main.yml").read_text())

def fetch(url, sha256):
    # curl, not urllib: curl uses the system trust store (the dev Mac's TLS interception).
    data = subprocess.run(["curl", "-fsSL", "--max-time", "120", url], check=True, capture_output=True).stdout
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        sys.exit(f"checksum mismatch for {url}: {digest} != {sha256}")
    return data

plugin, deps = build / "plugin", build / "memory-deps"
for d in (plugin, deps):
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
url = defaults["hermes_hindsight_plugin_url"].replace("{{ hermes_hindsight_plugin_version }}", version)
with tarfile.open(fileobj=io.BytesIO(fetch(url, defaults["hermes_hindsight_plugin_sha256"]))) as tar:
    for member in tar.getmembers():
        parts = member.name.split("/")
        if parts[1:3] == ["hindsight-integrations", "hermes"] and len(parts) > 3 and member.isfile():
            target = plugin.joinpath(*parts[3:])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
manifest = yaml.safe_load((plugin / "plugin.yaml").read_text())
if str(manifest["version"]) != version:
    sys.exit(f"plugin manifest is {manifest['version']}, pin is {version}")
for wheel in defaults["hermes_hindsight_plugin_wheels"]:
    zipfile.ZipFile(io.BytesIO(fetch(wheel["url"], wheel["sha256"]))).extractall(deps)
(build / "hermes-memory-deps.pth").write_text("/opt/hermes-memory-deps\n")  # as memory_plugin.yml
print(f"plugin {version} and {len(defaults['hermes_hindsight_plugin_wheels'])} packages unpacked")
EOF

# 4. The FR-021 fingerprint of what was just rendered.
"$PY" -c "import sys; sys.path.insert(0, '$REPO/python/tests/guardrails'); \
from test_memory_harness_gate import fingerprint_file; sys.stdout.write(fingerprint_file())" > "$OUT/fingerprint.txt"
echo "prod-render ready: $(head -1 "$OUT/fingerprint.txt")"
