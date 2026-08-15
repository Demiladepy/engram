# Engram

**Graph-native agent memory on [HydraDB](https://github.com/hydra-db/hydradb).**
Engram answers cross-session questions by traversing a temporal *provenance
graph*, returns a **receipt** for every recalled fact, and **abstains with
evidence** when the answer isn't in the history — the thing vector search
structurally cannot do.

> Built for **Hack Hydra 2026 · Track 03 (Memory & Context Retrieval)**.

## Why a graph, not vectors

Similarity is not relevance. The hardest place that shows is memory *across
sessions*: to answer "what does the user prefer now?" you have to chain a fact
stated in session 1, follow the update that overrode it in session 5, and filter
by time — a bounded path over shared entities. Vectors retrieve the nearest
chunk; they cannot traverse a supersession edge. Graphs can.

On the LongMemEval-S subsets where this matters — **multi-session reasoning,
knowledge-update, temporal reasoning, and abstention** — a graph memory layer
should beat a vector baseline and full-context prompting, *and* show its work.

_Benchmark numbers and the comparison chart land in [`results/`](results/) as the
harness comes online._

## How HydraDB is used

HydraDB **is** the memory. It is an object-store-native OpenCypher graph database
(Rust; Bolt on `:7687`, HTTP on `:8443`). Engram runs it as a server and drives
it from Python over the Neo4j Bolt driver — no Rust is forked. HydraDB does the
graph work that matters: the native `algo.MSpaths` traversal that collects the
evidence subgraph for every answer, plus temporal filtering over the fact model
below.

Without HydraDB, Engram loses the entire multi-hop temporal recall and the
provenance the demo is built on.

### Temporal provenance data model

```
(:Session)-[:CONTAINS]->(:Message)-[:STATES]->(:Fact)-[:ABOUT]->(:Entity)
(:Fact)-[:SUPERSEDES]->(:Fact)     knowledge updates / temporal reasoning
(:Fact)-[:CONTRADICTS]->(:Fact)    conflict surfacing
(:Entity)-[:SAME_AS]->(:Entity)    entity resolution / alias merge
```

A `:Fact` carries `{predicate, object, valid_from, valid_to, status, confidence}`;
`status ∈ {current, superseded, retracted}` and `valid_to = null` means "still
true". Every `:Fact` keeps a `STATES` edge back to its source `:Message` — that
edge is the receipt.

## Setup

Engram's client/harness is Python; HydraDB is a native server (Rust + SuiteSparse
GraphBLAS + libcypher-parser). See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the
full HydraDB build. Quick start once a local node is running:

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # add ANTHROPIC_API_KEY
python -m engram.graph                          # Bolt round-trip smoke
```

## Layout

| Path | What |
|---|---|
| `engram/graph.py`  | HydraDB Bolt client, Cypher builders, `MSpaths` call |
| `engram/ingest.py` | parse LongMemEval → extract facts → resolve entities → link supersession |
| `engram/answer.py` | retrieve → temporal filter → answer from evidence → receipt / abstain |
| `bench/`           | LongMemEval-S harness, baselines, comparison chart |
| `ui/`              | minimal receipt viewer |
| `results/`         | committed CSV + chart |

## License

[AGPL-3.0](LICENSE), mirroring HydraDB.

## Attribution

Built on [HydraDB](https://github.com/hydra-db/hydradb). Evaluated on
[LongMemEval](https://github.com/di-zhang-fdu/LongMemEval).
