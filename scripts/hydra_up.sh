#!/usr/bin/env bash
# Start a local plaintext HydraDB node for Engram development.
#
# Runs in the foreground (exec) so a supervisor/background launcher owns the
# PID. Store + cache + auth token live in WSL-native fs for speed. Ports are the
# standard HydraDB ones the Engram client defaults to.
set -euo pipefail

HYDRADB="${HYDRADB:-$HOME/hydra/hydradb}"
NODE="${ENGRAM_NODE_ROOT:-$HOME/hydra/engram-node}"
# Prefer the optimized release binary (stable under load, no write timeouts);
# fall back to debug.
if [[ -x "$HYDRADB/target/release/graph-node" ]]; then
  BIN="$HYDRADB/target/release/graph-node"
else
  BIN="$HYDRADB/target/debug/graph-node"
fi

if [[ ! -x "$BIN" ]]; then
  echo "graph-node not built at $BIN — run the HydraDB build first" >&2
  exit 1
fi
echo "using node binary: $BIN" >&2

mkdir -p "$NODE/store" "$NODE/cache"
TOKEN_FILE="$NODE/auth-token"
if [[ ! -f "$TOKEN_FILE" ]]; then
  # Local dev token; must be >=32 chars. Not a secret — plaintext local node.
  printf '%s\n' "engram-local-dev-token-0000000000000000" > "$TOKEN_FILE"
fi
echo "auth token file: $TOKEN_FILE" >&2

# Without this the node serves /readyz then aborts on the first query. See
# HydraDB justfile:18 and scripts/runtime_smoke.sh.
export RUST_MIN_STACK="${RUST_MIN_STACK:-33554432}"

export CLOUD_PROVIDER=local
export LOCAL_PATH="$NODE/store"
export GRAPH_NAMESPACE=default
export GRAPH_ID=default
export GRAPH_CELL_ID=cell-0
export GRAPH_CELLS=cell-0
export GRAPH_DATA_PATH=data
export GRAPH_ALLOW_PLAINTEXT=true
export GRAPH_AUTH_TOKEN_FILE="$TOKEN_FILE"
export GRAPH_DATA_CACHE_BYTES=67108864
export GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687
export GRAPH_NODE_ID=node-0
export GRAPH_BOLT_ADDR=127.0.0.1:7687
export GRAPH_HTTP_ADDR=127.0.0.1:8443
export GRAPH_ADMIN_ADDR=127.0.0.1:9090
export GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687
export GRAPH_DATA_CACHE_DIR="$NODE/cache"
export RUST_LOG="${RUST_LOG:-warn}"

echo "starting graph-node: bolt :7687  http :8443  admin :9090" >&2
exec "$BIN"
