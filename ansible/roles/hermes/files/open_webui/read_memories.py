# Reads Open WebUI's own memories for the one-shot import into the shared memory (spec 097 T043,
# research R-008). Run inside hermes_open_webui by tasks/main.yml; prints one JSON object and
# writes nothing. Holds no secret.
#
# Output: {"enabled": <memories.enable, or null when the row is absent>, "memories": [retain
# items]}. Each item is ready to send as is with the admin key: document_id owui-memory-<id>
# (a re-run replaces, never duplicates), tags origin:open-webui-memory and client:open-webui (the
# admin key keeps a supplied client tag, memory_access.rewrite_retain_tags), and a label that
# says where the text came from (FR-014): a saved memory may have been written by the model's
# memory tool, so it is not marked as the owner's own words.
#
# Open WebUI 0.11.3 table `memory`: id, user_id, type, path, content, meta, updated_at,
# created_at (models/memories.py). The table is left in place (R-008).
import json, os, re, sqlite3
from datetime import datetime, timezone

SECRET = re.compile(r'hmem_[A-Za-z0-9_-]{20,}')

con = sqlite3.connect(os.environ.get('HERMES_WEBUI_DB', '/app/backend/data/webui.db'), timeout=5)
con.row_factory = sqlite3.Row
row = con.execute("SELECT value FROM config WHERE key='memories.enable'").fetchone()
enabled = json.loads(row[0]) if row and row[0] is not None else None
rows = []
if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory'").fetchone():
    rows = con.execute('SELECT * FROM memory ORDER BY created_at, id').fetchall()
con.close()

memories = []
for r in rows:
    text = SECRET.sub('<redacted>', (r['content'] or '').strip())
    if not text:
        continue
    kind = r['type'] if 'type' in r.keys() and r['type'] else 'context'
    item = {
        'content': 'Open WebUI saved memory: ' + text,
        'document_id': 'owui-memory-%s' % r['id'],
        'context': 'memory saved in Open WebUI',
        'tags': ['origin:open-webui-memory', 'client:open-webui'],
        'metadata': {'platform': 'open-webui', 'origin': 'open-webui-memory', 'memory_type': kind},
    }
    if r['created_at']:
        item['timestamp'] = datetime.fromtimestamp(int(r['created_at']), timezone.utc).isoformat(timespec='seconds')
    memories.append(item)
print(json.dumps({'enabled': enabled, 'memories': memories}, ensure_ascii=False))
