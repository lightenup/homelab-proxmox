#!/usr/bin/env bash
# prod-render (spec 097): create the banks with the admin key, as roles/memory/tasks/bank.yml
# does on every memory deploy. Only admin may create a bank, so without this every client
# retain is refused with "scope readwrite may not create_bank".
set -euo pipefail
cd "$(dirname "$0")/../.."
ADMIN=$(grep '^memory_admin_key=' runs/prod-render/secret.env | cut -d= -f2-)
for bank in owner deploy-probe; do
    docker compose -f compose.base.yml -f compose.prod-render.yml exec -T -e ADMIN="$ADMIN" hindsight \
        python -c "import json,os,sys,urllib.request
r = urllib.request.Request('http://localhost:8888/v1/default/banks/' + sys.argv[1], method='PUT',
    data=json.dumps({'name': sys.argv[1]}).encode(),
    headers={'Authorization': 'Bearer ' + os.environ['ADMIN'], 'Content-Type': 'application/json'})
print('bank', sys.argv[1], urllib.request.urlopen(r, timeout=10).status)" "$bank"
done
