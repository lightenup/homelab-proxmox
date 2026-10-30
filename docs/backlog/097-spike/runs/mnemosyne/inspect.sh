#!/usr/bin/env bash
# Print what Mnemosyne actually stored, read straight from SQLite (not through the agent),
# to catch writes the agent reported but that never landed (#1177). Run after ./run.sh mnemosyne.
set -euo pipefail
cd "$(dirname "$0")/../.."
export DOCKER_HOST=unix://$HOME/.docker/run/docker.sock CANDIDATE=mnemosyne
P=${COMPOSE_PROJECT:-memspike}
docker compose -p "$P" -f compose.base.yml -f compose.mnemosyne.yml exec -T -u hermes hermes \
  /opt/hermes/.venv/bin/python - <<'PY'
import glob, sqlite3
dbs = sorted(glob.glob("/opt/data/mnemosyne/**/*.db", recursive=True))
print("databases:", dbs or "NONE")
for db in dbs:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    tables = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '%fts%' and name not like 'vec%'")]
    print(f"\n== {db}")
    for t in tables:
        n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
        if n: print(f"  {t}: {n}")
    for t in ("working_memory", "episodic_memory", "memories", "triples"):
        if t in tables:
            cols = [r[1] for r in c.execute(f'pragma table_info("{t}")')]
            col = next((x for x in ("content", "text", "summary", "object") if x in cols), None)
            if col:
                print(f"  -- {t}.{col}:")
                for (v,) in c.execute(f'select "{col}" from "{t}" order by rowid'):
                    print("    *", str(v).replace("\n", " ")[:160])
PY
docker compose -p "$P" -f compose.base.yml -f compose.mnemosyne.yml exec -T -u hermes hermes sh -c \
  'echo; echo "== built-in memory"; for f in /opt/data/memories/*.md; do echo "-- $f"; cat "$f"; done 2>/dev/null || true'
