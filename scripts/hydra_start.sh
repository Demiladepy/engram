#!/usr/bin/env bash
# Start the Engram HydraDB node (detached) if not already up, then wait until
# it reports ready on the admin port. Idempotent.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="${ENGRAM_NODE_LOG:-$HOME/hydra/engram-node.log}"
PIDF="${ENGRAM_NODE_PID:-$HOME/hydra/engram-node.pid}"

if [[ -f "$PIDF" ]] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDF"))"
else
  nohup bash "$HERE/hydra_up.sh" >"$LOG" 2>&1 &
  echo $! >"$PIDF"
  echo "started pid $(cat "$PIDF")"
fi

for i in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:9090/readyz >/dev/null 2>&1; then
    echo "READYZ_OK ($i)"
    exit 0
  fi
  if ! kill -0 "$(cat "$PIDF")" 2>/dev/null; then
    echo "NODE_DIED"
    tail -30 "$LOG"
    exit 1
  fi
  sleep 0.5
done

echo "TIMEOUT waiting for readyz"
tail -30 "$LOG"
exit 1
