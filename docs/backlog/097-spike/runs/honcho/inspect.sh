#!/usr/bin/env bash
# After a run: what Honcho actually stored. Usage: runs/honcho/inspect.sh [project]
# Defaults to the live harness project `memspike`. Read-only queries against honcho-db.
set -euo pipefail
cd "$(dirname "$0")/../.."
P=${1:-memspike}; export CANDIDATE=honcho LITELLM_SPIKE_KEY=${LITELLM_SPIKE_KEY:-unused}
export DOCKER_HOST=unix://$HOME/.docker/run/docker.sock
DC=(docker compose -p "$P" -f compose.base.yml -f compose.honcho.yml)
q() { "${DC[@]}" exec -T honcho-db psql -U honcho -d honcho -P pager=off "$@"; }
echo "== counts"
q -tAc "select 'workspaces',count(*) from workspaces union all select 'peers',count(*) from peers
        union all select 'sessions',count(*) from sessions union all select 'messages',count(*) from messages
        union all select 'message_embeddings',count(*) from message_embeddings
        union all select 'documents (observations/conclusions)',count(*) from documents where deleted_at is null
        union all select 'queue pending',count(*) from queue where not processed
        union all select 'queue processed',count(*) from queue where processed
        union all select 'queue errors',count(*) from queue where error is not null;"
echo "== queue by task type"
q -tAc "select task_type, processed, (error is not null) as errored, count(*) from queue group by 1,2,3 order by 1,2,3;"
echo "== queue errors (first 5)"
q -tAc "select task_type, left(error, 160) from queue where error is not null order by id limit 5;"
echo "== documents by level (observer -> observed)"
q -tAc "select level, observer, observed, count(*) from documents where deleted_at is null group by 1,2,3 order by 1,2,3;"
echo "== documents (newest first)"
q -c "select level, observed, left(regexp_replace(content, '\s+', ' ', 'g'), 140) as content
      from documents where deleted_at is null order by created_at desc limit 60;"
echo "== peer cards"
q -c "select name, left(coalesce(internal_metadata->>'peer_card', internal_metadata::text), 600) as card
      from peers order by name;"
echo "== messages per session"
q -tAc "select session_name, count(*) from messages group by 1 order by 1;"
