#!/usr/bin/env bash
# After a run: what Hindsight actually stored. Usage: runs/hindsight/inspect.sh [project] [candidate]
# Defaults to the live harness project `memspike`; the candidate only selects the compose env files.
set -euo pipefail
cd "$(dirname "$0")/../.."
P=${1:-memspike}; export CANDIDATE=${2:-hindsight} LITELLM_SPIKE_KEY=${LITELLM_SPIKE_KEY:-unused}
export DOCKER_HOST=unix://$HOME/.docker/run/docker.sock
DC=(docker compose -p "$P" -f compose.base.yml -f compose.hindsight.yml)
q() { "${DC[@]}" exec -T hindsight-db psql -U hindsight -d hindsight -P pager=off "$@"; }
echo "== counts"
q -tAc "select 'documents',count(*) from documents union all select 'chunks',count(*) from chunks
        union all select 'memory_units',count(*) from memory_units union all select 'entities',count(*) from entities
        union all select 'mental_models',count(*) from mental_models;"
echo "== memory units by type"
q -tAc "select fact_type,count(*) from memory_units group by 1 order by 1;"
echo "== memory units (newest first)"
q -c "select fact_type, left(regexp_replace(text, '\s+', ' ', 'g'), 140) as text, document_id from memory_units order by created_at desc limit 60;"
echo "== documents per session"
q -tAc "select id, length(original_text) from documents order by created_at;" 2>/dev/null || true
echo "== async operations"
q -tAc "select operation_type, status, count(*) from async_operations group by 1,2 order by 1,2;" 2>/dev/null || true
