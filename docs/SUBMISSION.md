# Submission — paste-ready answers

Hack Hydra 2026 · Track 03 (Memory & Context Retrieval). Add the video link
before submitting; open every link yourself first.

---

**What problem are you solving?**

Agent memory built on vector search retrieves what's *similar*, not what's *true
now*. Across many sessions that breaks: when a user updates a fact — a new
personal best, a move to a new city — similarity search returns the old value and
the new one with no way to tell which is current, and it never abstains, so it
confidently answers questions the history never covered. The result is memory
that can't track how a fact changed over time and can't show *why* it recalled
what it did.

**What did you build?**

Engram, a graph-native memory layer on HydraDB. It ingests a chat history into a
temporal *provenance graph* — sessions contain messages, messages state facts,
facts are about entities, and any fact that updates an earlier one is linked by a
`SUPERSEDES` edge. To answer, it extracts the subject, traverses the typed graph
(`STATES` / `ABOUT` / `SUPERSEDES`), filters to the fact that's current, and
answers strictly from that evidence. Two things fall out that vector memory
can't do: every answer carries a **receipt** — the exact source message and the
value it superseded — and when the graph holds no supporting fact, Engram
**abstains** instead of guessing. It ships with a benchmark harness against a
vector-RAG baseline on LongMemEval-S, and a dark receipt-viewer UI.

**How does your project use HydraDB?**

HydraDB *is* the memory, not a cache beside it. It runs as a local OpenCypher
graph node (Bolt on :7687) that Engram drives from Python over the Neo4j driver —
no Rust forked. Every operation is graph work HydraDB executes: ingest writes the
provenance graph with batched `UNWIND` upserts; answering runs a typed multi-hop
`MATCH` over the `STATES`/`ABOUT`/`SUPERSEDES` edges plus HydraDB's native
`algo.SSpaths` path procedure; knowledge-updates resolve by walking the
`SUPERSEDES` chain to the current fact; each question loads into its own scoped
database so histories stay isolated. It matters because the whole thesis — recall
the version of a fact that's true *now*, and prove where it came from — is a
multi-hop temporal traversal. Without HydraDB there is no traversal and no
provenance; the system collapses to a flat key-value lookup that can do neither.

**Tech Stack**

Python · HydraDB (OpenCypher graph, Bolt) · neo4j Bolt driver · OpenRouter
(gpt-4o-mini) through an OpenAI-compatible layer (provider-swappable) · fastembed
(local embeddings for the vector baseline) · Streamlit (UI) · matplotlib.
AGPL-3.0.

**Deployed Project URL**

https://demiladepy.github.io/engram/  — a live showcase + demo of the system
(the full interactive app runs locally against a HydraDB node; the repo has
one-command setup, and the 3-min video shows it running).
Repo: https://github.com/Demiladepy/engram

**Team contribution**

Solo project. I designed and built everything: the temporal provenance data
model, the ingest + supersession-linking pipeline, the graph read path
(traversal → temporal filter → answer → receipt → abstain), the provider-agnostic
LLM layer, the LongMemEval benchmark harness and vector baseline, and the UI.

**Demo video**

<paste unlisted YouTube link>

---

### Results (for reference — see docs/RESULTS.md)
Small LongMemEval-S sample, same model both systems, LLM-judged. Accuracy is
competitive; the differentiators are provenance + abstention, which vectors lack.
knowledge-update 71% vs 67% · multi-session 30% vs 20% · abstention 100% vs 100%
· temporal-reasoning 20% vs 60% (Engram's honest weak spot).

### Pre-submit checklist
- [ ] Repo public, AGPL-3.0, README renders, `git log` clean (post-Aug-12)
- [ ] `results/` has chart + CSV committed
- [ ] Video ≤ 3:00, unlisted, plays without an access request
- [ ] Every link opened and verified · submitted before the deadline
