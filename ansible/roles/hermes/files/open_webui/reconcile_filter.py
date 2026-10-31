# Upserts the shared-memory filter into Open WebUI's `function` table (spec 097 T042, research
# R-007). Run inside hermes_open_webui by tasks/main.yml with a JSON payload on stdin, never in
# argv (the payload carries the memory key and the agent key). Holds no secret itself.
#
# Payload: {id, name, description, content, valves: {url, key, bank}, models_url, models_key}.
# The agent's model ids are read here, inside the container, which shares the compose network
# with the agent, and written into the `agent_model_ids` valve. An empty list fails: it means the
# agent connection is missing or renamed, and the filter would then store agent chats twice.
#
# Verified against Open WebUI 0.11.3: inlet and outlet re-read the function content and valves
# from the database on every request (utils/plugin.py get_function_module_from_cache,
# utils/filter.py FilterContext), so a change takes effect without a restart. Valves are stored
# as plain JSON unless ENABLE_VALVE_ENCRYPTION is on, which this script refuses.
import json, os, sqlite3, sys, time, urllib.request

want = json.loads(sys.stdin.read())

request = urllib.request.Request(want['models_url'], headers={'Authorization': 'Bearer ' + want['models_key']})
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        ids = sorted({m['id'] for m in json.load(response).get('data') or [] if m.get('id')})
except Exception as e:
    sys.exit('AGENT MODELS: listing %s failed (%s). Refusing to configure the memory filter '
             'without the agent model ids.' % (want['models_url'], type(e).__name__))
if not ids:
    sys.exit('AGENT MODELS: %s listed no models. The agent connection is missing or renamed; '
             'the memory filter would store agent chats twice.' % want['models_url'])

if os.environ.get('ENABLE_VALVE_ENCRYPTION', 'false').lower() == 'true':
    sys.exit('VALVE ENCRYPTION is on: this script writes plain JSON valves. Refusing to write.')

con = sqlite3.connect(os.environ.get('HERMES_WEBUI_DB', '/app/backend/data/webui.db'), timeout=5)
con.execute('PRAGMA busy_timeout=5000')
COLUMNS = ('id', 'user_id', 'name', 'type', 'content', 'meta', 'valves', 'is_active', 'is_global',
           'updated_at', 'created_at')
cols = {r[1] for r in con.execute('PRAGMA table_info(function)')}
if not set(COLUMNS) <= cols:
    sys.exit('SCHEMA DRIFT: function table has columns %s; expected %s. Refusing to write.'
             % (sorted(cols), list(COLUMNS)))

row = con.execute('SELECT name, type, content, meta, valves, is_active, is_global FROM function '
                  'WHERE id=?', (want['id'],)).fetchone()
current = {}
if row:
    current = {'name': row[0], 'type': row[1], 'content': row[2], 'meta': json.loads(row[3] or '{}'),
               'valves': json.loads(row[4] or '{}'), 'is_active': bool(row[5]), 'is_global': bool(row[6])}
# meta: keep what the app adds (manifest, toggle), own the description.
meta = dict(current.get('meta') or {}, description=want['description'])
meta.setdefault('manifest', {})
desired = {'name': want['name'], 'type': 'filter', 'content': want['content'], 'meta': meta,
           'valves': dict(want['valves'], agent_model_ids=ids), 'is_active': True, 'is_global': True}
changed = [k for k in desired if current.get(k) != desired[k]]

now = int(time.time())
values = (desired['name'], 'filter', desired['content'], json.dumps(meta), json.dumps(desired['valves']),
          1, 1, now)
if not row:
    admin = con.execute('SELECT id FROM "user" WHERE role=\'admin\' ORDER BY created_at LIMIT 1').fetchone()
    con.execute('INSERT INTO function (name, type, content, meta, valves, is_active, is_global, updated_at, '
                'id, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                values + (want['id'], admin[0] if admin else None, now))
elif changed:
    con.execute('UPDATE function SET name=?, type=?, content=?, meta=?, valves=?, is_active=?, '
                'is_global=?, updated_at=? WHERE id=?', values + (want['id'],))
con.commit()
con.close()
print('CHANGED ' + ','.join(changed) if changed else 'UNCHANGED')
