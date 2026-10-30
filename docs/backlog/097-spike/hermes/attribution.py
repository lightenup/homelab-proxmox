"""Which tools answered each probe: reads the agent's state.db (run inside the hermes container).
A probe is a session whose first user message is a probe question."""
import json, sqlite3, sys
d = json.load(open(sys.argv[1]))
probes = {p["q"]: p["id"] for p in d["probes"]}
c = sqlite3.connect("file:/opt/data/state.db?mode=ro", uri=True)
first = {}
for sid, content in c.execute("select session_id, content from messages where role='user' order by id"):
    first.setdefault(sid, content)
for sid, q in first.items():
    for pq, pid in probes.items():
        if q and pq in q:
            tools = [r[0] for r in c.execute(
                "select tool_name from messages where session_id=? and role='tool' order by id", (sid,))]
            print(json.dumps({"probe": pid, "tools": tools}))
