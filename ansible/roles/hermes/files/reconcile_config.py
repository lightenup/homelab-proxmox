# Reconciles Open WebUI PersistentConfig keys from a JSON object on stdin (see tasks/main.yml,
# "Reconcile the persisted Open WebUI configuration we own"). Holds no secret itself.
import json, sqlite3, sys, time

desired = json.loads(sys.stdin.read())
con = sqlite3.connect('/app/backend/data/webui.db', timeout=5)
con.execute('PRAGMA busy_timeout=5000')

cols = [r[1] for r in con.execute('PRAGMA table_info(config)')]
if 'key' not in cols or 'value' not in cols:
    sys.exit('SCHEMA DRIFT: config table has columns %s; expected key/value. '
             'Refusing to write.' % cols)

changed = []
now = int(time.time())
for key, want in sorted(desired.items()):
    row = con.execute('SELECT value FROM config WHERE key=?', (key,)).fetchone()
    current = None
    if row and row[0] is not None:
        try:
            current = json.loads(row[0])
        except (TypeError, ValueError):
            current = row[0]
    if current == want:
        continue
    con.execute(
        'INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value, '
        'updated_at=excluded.updated_at',
        (key, json.dumps(want), now),
    )
    changed.append(key)
if changed:
    con.commit()
con.close()
print('CHANGED ' + ','.join(changed) if changed else 'UNCHANGED')
