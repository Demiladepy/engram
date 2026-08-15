# Runbook — HydraDB + Engram, from scratch

Verified on Ubuntu 24.04 (WSL2), Rust 1.95. Engram's client is Python; HydraDB
is a native Rust server. HydraDB is **not** vendored — you build it once and run
it as a local node.

## 1. Native toolchain (once)

```bash
sudo apt-get update && sudo apt-get install -y \
  build-essential ca-certificates clang cmake curl libclang-dev \
  libcypher-parser-dev libgraphblas-dev pkg-config \
  python3-pip python3-venv
# Rust (if absent): curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
```

`libcypher-parser-dev` and `libgraphblas-dev` are exactly what HydraDB's
`just native-check` looks for; no source builds needed.

## 2. Build HydraDB

```bash
mkdir -p ~/hydra && cd ~/hydra
git clone https://github.com/hydra-db/hydradb
cd hydradb
# The gate: builds graph-node, starts a node, runs a Python neo4j round-trip.
CARGO_HTTP_TIMEOUT=300 CARGO_NET_RETRY=10 \
  PYTHON=~/hydra/venv/bin/python bash scripts/runtime_smoke.sh   # -> "runtime-smoke-ok"
```

First build compiles ~400 crates (incl. `aws-lc-sys`/`ring` via cmake); allow a
few minutes. `runtime_smoke.sh` sets `RUST_MIN_STACK=33554432` — without it the
node serves `/readyz` then aborts on the first query.

## 3. Run a persistent Engram node

```bash
# from the engram repo:
bash scripts/hydra_start.sh          # detached; waits for readyz on :9090
# stop: kill "$(cat ~/hydra/engram-node.pid)"
```

Bolt `:7687`, HTTP `:8443`, admin/metrics `:9090`. Plaintext (no TLS) but a
token is still required: it's written to `~/hydra/engram-node/auth-token`.

## 4. Engram client

```bash
python3 -m venv ~/hydra/venv && ~/hydra/venv/bin/pip install -r requirements.txt
cp .env.example .env    # add ANTHROPIC_API_KEY
export HYDRA_PASSWORD="$(cat ~/hydra/engram-node/auth-token)"
PYTHONPATH=. ~/hydra/venv/bin/python -m engram.graph   # Bolt round-trip -> OK
```

## HydraDB Cypher subset (shapes the data model)

HydraDB implements a deliberate subset (see `cypher-compat.md` in its repo).
The load-bearing constraints for Engram:

- **Node `id` is a non-negative integer.** Every node gets an int id; human keys
  live in other properties.
- **Property values are int/float/bool/string only** — no null, no lists. So a
  fact's open interval is `status='current'` + integer epoch `valid_from/valid_to`
  (sentinel for "open"), never `valid_to = null`.
- **`CREATE` only builds relationship paths.** Standalone nodes are
  `MERGE (n {id}) SET n:Label, n.prop = ...`.
- **One statement per request**; batches go through `UNWIND $rows AS row ...`
  with a parameter list-of-maps.
- Whole paths come back only from `algo.SPpaths/SSpaths/MSpaths`.
