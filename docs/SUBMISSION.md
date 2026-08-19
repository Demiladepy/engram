# Submission — paste-ready answers

Hack Hydra 2026 · Track 03 (Memory & Context Retrieval). Fill the video link
before submitting. Submit hours early; open every link yourself first.

---

**Project name**
Engram

**One-line description**
Graph-native agent memory on HydraDB that answers cross-session questions by
traversing a temporal provenance graph, returns a receipt for every recalled
fact, and abstains with evidence when the answer isn't in the history.

**Problem**
Vector memory retrieves what's *similar*, not what's *true now*. Across sessions
that breaks: when a user updates a fact — a new personal best, a move to a new
city — similarity search pulls back the old value and the new one with no way to
tell which is current, and it never abstains, so it hallucinates on questions the
history doesn't answer. That's exactly the failure HydraDB was built to fix.

**What we built**
Engram ingests a chat history into a HydraDB provenance graph —
`(:Session)-[:CONTAINS]->(:Message)-[:STATES]->(:Fact)-[:ABOUT]->(:Entity)` with
`(:Fact)-[:SUPERSEDES]->(:Fact)` linking each update to what it overrode. To
answer, it extracts the query entity, runs a typed multi-hop traversal over
`STATES`/`ABOUT`/`SUPERSEDES`, temporally filters to the current fact, and answers
strictly from that evidence — attaching a receipt (the exact source message and
the value it superseded) to every fact used. When the traversal finds no support,
it abstains instead of guessing. A Streamlit UI renders the answer and its
receipt; a benchmark harness scores it against a vector-RAG baseline.

**How HydraDB is used**
HydraDB *is* the memory. It runs as a local OpenCypher graph node (Bolt on 7687)
driven from Python over the Neo4j driver — no Rust forked. Every answer is graph
work HydraDB executes: batched `UNWIND` upserts on ingest; a typed multi-hop
`MATCH` over the provenance edges plus the native `algo.SSpaths` path procedure on
read; supersession resolution by walking `SUPERSEDES`. Each question loads into
its own scoped database so haystacks stay isolated. Without HydraDB there is no
cross-session traversal and no provenance — the whole thing collapses to a flat
lookup.

**Results**
On a small LongMemEval-S sample, LLM-judged, same model (gpt-4o-mini) for both
systems — Engram vs a vector-RAG baseline. Accuracy is close; the differentiators
are provenance and abstention, which vectors lack.
- knowledge-update: 5/7 (71%) vs 4/6 (67%)
- multi-session: 3/10 (30%) vs 2/10 (20%)
- abstention: 5/5 (100%) vs 5/5 (100%)
- temporal-reasoning (date arithmetic): 1/5 (20%) vs 3/5 (60%) — Engram's honest
  weak spot; extracted facts lose the exact event dates raw chunks keep.
Every Engram answer additionally carries a receipt (source message + superseded
value) and abstains with an empty evidence set when unsupported — behaviours the
baseline cannot produce. Chart + CSV in `results/`; worked examples in
`docs/RESULTS.md`.

**Tech stack**
HydraDB (OpenCypher graph, Bolt) · Python · neo4j Bolt driver · OpenRouter
(gpt-4o-mini) via an OpenAI-compatible layer, swappable to any provider ·
fastembed (local embeddings, vector baseline) · Streamlit (receipt UI) ·
matplotlib (chart). AGPL-3.0.

**Contributions / what's original**
The temporal provenance data model and the supersession-aware read path — answer
+ receipt + evidence-backed abstention — built to HydraDB's OpenCypher subset
(integer node ids, no-null properties, `UNWIND` batches), plus a same-harness
benchmark against a vector baseline.

**Repository**
https://github.com/Demiladepy/engram

**Demo video**
<paste unlisted YouTube link>

---

### Pre-submit checklist
- [ ] Repo public, AGPL-3.0, README renders, `git log` clean (post-Aug-12)
- [ ] `results/` has chart + CSV committed
- [ ] Video ≤ 3:00, unlisted, plays without an access request
- [ ] Every link opened and verified
- [ ] Submitted before the deadline
