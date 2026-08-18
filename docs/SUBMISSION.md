# Submission — Hack Hydra 2026, Track 03 (Memory & Context Retrieval)

*(Draft answers for the submission form. Final benchmark numbers filled from
`results/summary.csv` once the run completes.)*

**Project name:** Engram

**One-line description:** Graph-native agent memory on HydraDB that answers
cross-session questions by traversing a temporal provenance graph, returns a
receipt for every recalled fact, and abstains when the answer isn't in memory.

**Problem:** Vector memory retrieves what's *similar*, not what's *current* or
*true*. Across sessions this breaks: when a user updates a fact (a new job, a
new personal best), similarity search surfaces the old value, the new value, or
both, with no way to tell which holds now — and it can't show why it recalled
anything. Agents need memory that tracks how facts change over time and can
prove its answers.

**What we built:** Engram ingests chat histories into a temporal provenance
graph — `(:Session)-[:CONTAINS]->(:Message)-[:STATES]->(:Fact)-[:ABOUT]->
(:Entity)` with `(:Fact)-[:SUPERSEDES]->(:Fact)` for updates. Answering is a
typed multi-hop traversal + temporal filter that resolves each question to the
*current* fact and emits a **receipt** (the source message + the value it
superseded). When no fact supports the question, it **abstains** instead of
hallucinating. A benchmark harness scores it against a vector-RAG baseline on
LongMemEval-S, and a Streamlit UI shows the receipt for any question.

**How HydraDB is used:** HydraDB *is* the memory. It runs as a local node; Engram
drives it over the Bolt driver (no Rust forked). Every answer is a graph
traversal on HydraDB — typed multi-hop `MATCH` over `STATES`/`ABOUT`/`SUPERSEDES`
plus native `algo.SSpaths`; writes are batched `UNWIND` upserts; each question
gets its own scoped database. Without HydraDB there is no multi-hop temporal
recall and no provenance — the whole demo is the graph.

**Results (LongMemEval-S):** On **knowledge-update** — the category built for
supersession — Engram beats the vector-RAG baseline (Engram 5/5 vs vector 3/5 in
the partial run; final numbers in `results/`), with a receipt on every answer.
It abstains correctly on unanswerable questions where full-context prompting
hallucinates. Honest limitation: it's weaker on temporal date-arithmetic.

**Stack:** HydraDB (OpenCypher graph DB), Python + Neo4j Bolt driver, any
OpenAI-compatible LLM endpoint (OpenRouter / `gpt-4o-mini` by default; Groq and
local Ollama also supported), fastembed for the vector baseline, Streamlit UI.

**Repo:** https://github.com/Demiladepy/engram — AGPL-3.0.

**Video:** _(unlisted YouTube link — see docs/DEMO_SCRIPT.md)_

**What's original vs reused:** Original — the temporal provenance data model,
ingest/extraction/supersession pipeline, the traversal-based read path with
receipts and abstention, the benchmark harness and baselines, the UI. Reused —
HydraDB (the graph engine), LongMemEval-S (evaluation data), off-the-shelf LLM
endpoints and the fastembed model.
