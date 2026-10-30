#!/usr/bin/env bash
# Run candidates one at a time after the baseline; each run tears down the previous stack.
cd "$(dirname "$0")"
until [ -s results/none/score.txt ]; do sleep 20; done
for c in "$@"; do
  echo "=== $c $(date +%T)"
  ./run.sh "$c" > "results/$c.out" 2>&1 || echo "run $c exited $?"
  [ -x "runs/$c/inspect.sh" ] && COMPOSE_PROJECT=memspike "runs/$c/inspect.sh" > "results/$c/inspect.txt" 2>&1
  [ "$c" = hindsight-chunks ] || [ "$c" = hindsight-full ] && [ -x runs/hindsight/inspect.sh ] && runs/hindsight/inspect.sh > "results/$c/inspect.txt" 2>&1
done
echo "=== done $(date +%T)"
