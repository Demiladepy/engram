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

**Status.** The graph mechanism is verified end to end on real LongMemEval-S
data: a knowledge-update question (`"personal best 5K time?"`) is answered by
following a `SUPERSEDES` edge from the superseded value to the current one, with
a receipt pointing at the exact source message; an unanswerable question
(`"name of my hamster?"`) is correctly **abstained** despite 100+ facts about the
user. The Engram-vs-vector-RAG benchmark is built and runnable
([`bench/`](bench/)); the at-scale accuracy chart awaits an LLM budget past
free-tier daily token caps. Full detail — worked examples, limitations, and how
to run the benchmark — in [`docs/RESULTS.md`](docs/RESULTS.md).

## How HydraDB is used

HydraDB **is** the memory. It is an object-store-native OpenCypher graph database
(Rust; Bolt on `:7687`, HTTP on `:8443`). Engram runs it as a server and drives
it from Python over the Neo4j Bolt driver — no Rust is forked. HydraDB does the
graph work that matters:

- **Typed multi-hop traversal** over `STATES`/`ABOUT`/`SUPERSEDES` retrieves each
  answer's facts *and* their source messages in one query
  (`(:Message)-[:STATES]->(:Fact)-[:ABOUT]->(:Entity)`).
- **Native path procedures** (`algo.SSpaths` by integer node id) return whole
  provenance subgraphs for the receipt.
- **Temporal filtering** over the fact model below resolves supersession to the
  fact that is current (or true as-of a date).
- Each question is loaded into its own **scoped database**, so haystacks never
  contaminate each other.

Every write respects HydraDB's OpenCypher subset (integer node ids, no null/list
properties, `CREATE` builds relationship paths, batches via `UNWIND $rows`).

Without HydraDB, Engram loses the entire multi-hop temporal recall and the
provenance the demo is built on.

### Temporal provenance data model

```
(:Session)-[:CONTAINS]->(:Message)-[:STATES]->(:Fact)-[:ABOUT]->(:Entity)
(:Fact)-[:SUPERSEDES]->(:Fact)     knowledge updates / temporal reasoning
```

A `:Fact` carries `{predicate, object, valid_from, valid_to, status, confidence}`
with integer-epoch times; `status ∈ {current, superseded}`. HydraDB
stores no nulls, so an open interval is a far-future `valid_to` sentinel rather
than `null`. Every `:Fact` keeps a `STATES` edge back to its source `:Message` —
that edge is the receipt.

## Setup

Engram's client/harness is Python; HydraDB is a native server (Rust + SuiteSparse
GraphBLAS + libcypher-parser). See [`docs/RUNBOOK.md`](docs/RUNBOOK.md) for the
full HydraDB build. Quick start once a local node is running:

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                            # add GROQ_API_KEY
export HYDRA_PASSWORD="$(cat ~/hydra/engram-node/auth-token)"
python -m engram.graph                          # Bolt round-trip smoke
```

**LLM stack.** Engram talks to any OpenAI-compatible endpoint (Groq by default;
point `ENGRAM_LLM_BASE_URL` at Ollama or another provider). Fact extraction and
answering use function-calling for structured output; the vector-RAG baseline
embeds locally with `fastembed`, so only the answer step hits the network. Models
are chosen per role (`ENGRAM_EXTRACT_MODEL`, `ENGRAM_ANSWER_MODEL`,
`ENGRAM_JUDGE_MODEL`) and all calls are cached to disk.

Run the benchmark and demo:

```bash
python -m bench.run_longmemeval --n 5   # Engram vs vector-RAG, per-category CSV
python -m bench.plot                     # results/engram_vs_baseline.png
streamlit run ui/app.py                  # receipt viewer
```

## Layout

| Path | What |
|---|---|
| `engram/graph.py`  | HydraDB Bolt client — batched `UNWIND` writes, typed traversal, `SSpaths` |
| `engram/ingest.py` | parse LongMemEval → batched fact extraction → link supersession by time |
| `engram/answer.py` | retrieve → temporal filter → answer from evidence → receipt / abstain |
| `engram/llm.py`    | provider-agnostic (OpenAI-compatible) extraction / answering / judge, cached |
| `bench/`           | LongMemEval-S harness, vector-RAG + full-context baselines, chart |
| `ui/app.py`        | Streamlit receipt viewer (dark, receipt + supersession) |
| `results/`         | committed CSV + chart |
| `docs/RESULTS.md`  | verified worked examples + honest limitations |
| `docs/RUNBOOK.md`  | from-scratch HydraDB build + run |
| `docs/DEMO_SCRIPT.md` · `docs/SUBMISSION.md` | 3-min video script · paste-ready form answers |

## License

[AGPL-3.0](LICENSE), mirroring HydraDB.

## Attribution

Built on [HydraDB](https://github.com/hydra-db/hydradb). Evaluated on
[LongMemEval](https://github.com/di-zhang-fdu/LongMemEval).
