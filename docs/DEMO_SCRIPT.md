# 3-minute demo script

Hard cap 3:00 — anything past it may be ignored. Record unlisted on YouTube.
Have two things open: the results chart (`results/engram_vs_baseline.png`) and the
Engram UI (`streamlit run ui/app.py`, dark receipt viewer). Speak to the beats;
the bracketed lines are what's on screen.

---

## 0:00 – 0:25 · The thesis  *[show the chart]*

> "HydraDB's whole bet is that similar isn't relevant. The hardest place to prove
> that is memory across sessions — where you have to follow how a fact *changed*
> over time. Here's Engram, a graph memory layer on HydraDB, versus a vector-RAG
> baseline on LongMemEval. On knowledge-update — questions where an earlier answer
> got overwritten — Engram scores 100%, vector 60%. Let me show you why."

## 0:25 – 1:30 · The build  *[Engram UI, knowledge-update sample selected]*

> "This user mentioned their personal-best 5K time in one session — 27:12 — and
> weeks later, in a different session, a new best: 25:50. I ask Engram: what's my
> personal best 5K time?"

*[press Ingest + Ask — the answer hero fills in]*

> "25:50 — the current value. And this is the part vectors can't do: every answer
> comes with a receipt."

*[point at the receipt card]*

> "Here's the exact source message it came from. And here's the supersession edge —
> the old 27:12, struck through, superseded by 25:50. Engram walked that edge across
> two sessions to the value that's true *now*. A vector search would pull back both
> numbers by similarity and have no idea which one is current."

## 1:30 – 2:20 · The kill shot  *[switch to the abstention sample]*

> "The other half is knowing what you *don't* know. I ask about something never
> stated — the name of a hamster the user doesn't have."

*[press Ingest + Ask — the amber ABSTAINED state appears]*

> "Engram holds over a hundred facts about this user — including their cat, Luna —
> finds nothing about a hamster, and abstains. It declines instead of inventing a
> name. A plain LLM with the whole history in context hallucinates one. Engram
> returns an empty evidence set and says: not in memory."

## 2:20 – 3:00 · The number, on HydraDB  *[back to the chart]*

> "Both systems abstain perfectly and tie on aggregation. Engram wins the category
> it's built for — supersession — and it's honest where it's weaker, on date
> arithmetic. Every bit of this runs on HydraDB: the provenance graph, the typed
> multi-hop traversal, the supersession chain, the native path procedures. Graph
> beat vector on the one thing vectors structurally can't do — traverse a
> supersession edge across sessions. That's the thesis, benchmarked, on HydraDB."

---

### Capture checklist
- [ ] Chart full-screen, readable
- [ ] UI at a comfortable zoom; the receipt card and supersession row clearly visible
- [ ] The amber ABSTAINED state on the abstention question
- [ ] Total runtime ≤ 3:00 (rehearse once; trim the build section if over)
- [ ] Export 1080p, upload unlisted, confirm it plays without sign-in
