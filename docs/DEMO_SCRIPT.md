# 3-minute demo script

Hard cap 3:00. Record at 1080p; keep the receipt readable. Screens to have
ready: (A) the results chart `results/engram_vs_baseline.png`, (B) the Streamlit
receipt UI (`streamlit run ui/app.py`), (C) a terminal on the HydraDB node, (D)
a browser tab for a full-context/vector baseline answer.

---

### 0:00–0:25 — The enemy

> "This founder raised to kill vector search, because *similar* isn't
> *relevant*. The hardest proof is memory across sessions: to answer 'what's my
> personal best now?' you must follow the update that overrode last month's
> value. Vectors retrieve both the old and the new by similarity — with no way
> to tell which is current."

**Show (A):** the chart — point at the knowledge-update bars.

### 0:25–1:30 — The build, and the receipt

> "Engram ingests a chat history into a temporal provenance graph on HydraDB —
> sessions, messages, and extracted facts, linked by `SUPERSEDES` when a value
> changes."

**Show (B):** pick the knowledge-update question, hit **Ingest + Ask**.

> "The user set a 5K personal best of 27:12, then months later 25:50. Ask
> Engram."

**Answer appears: `25:50`.** Expand the **Receipt**.

> "This is the graph showing its work: the exact source message, and the earlier
> `27:12` it superseded. That's a supersession edge traversed on HydraDB —
> something a vector index structurally cannot do."

### 1:30–2:20 — The kill shot: abstention

**Show (D) then (B) side by side.** Ask: *"What's the name of my hamster?"* —
never stated.

> "Full-context prompting invents a name." (baseline hallucinates on the left)
> "Engram finds no supporting fact and abstains — it declines instead of
> guessing." (right: ABSTAINED, empty evidence)

### 2:20–3:00 — The number

**Show (A)** full chart.

> "On LongMemEval-S, on the category built for this — knowledge-update — Engram
> beats the vector-RAG baseline, and every answer ships with a receipt. Graph
> memory beat vector memory on the one thing vectors can't do: traverse a
> supersession edge across sessions. Benchmarked, with provenance, on HydraDB."

**End card:** repo URL + "AGPL-3.0 · built on HydraDB".

---

Notes:
- If time is tight, cut the multi-session/temporal categories from the pitch —
  knowledge-update + abstention are the clean wins; don't oversell the rest.
- Keep the receipt on screen long enough to read the source message.
