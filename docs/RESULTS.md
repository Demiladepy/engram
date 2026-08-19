# Results — what is verified, and what is pending

## Verified end to end (real LongMemEval-S data)

### 1. Knowledge-update — follow `SUPERSEDES` to the current fact

Question `6a1eabeb`: *"What was my personal best time in the charity 5K run?"*
The user states `27:12` in one session and, weeks later, `25:50` in another.
Engram ingests both, links them by time, and answers with the current value and
a receipt:

```
A: Your personal best time in the 5K was 25:50.        gold: 25:50  ✓
   RECEIPT · personal_best_5k_time = 25:50  [status=current]
       stated in session answer_a25d4a91_2: "...hoping to beat my
       personal best time of 25:50 this time around."
       superseded earlier value: 27:12  (valid until 2023-05-30)
```

The supersession chain, straight from HydraDB:

```
personal_best_5k_time: '27:12' (superseded)  --SUPERSEDES-->  '25:50' (current)
lives_in:              'Tokyo' (superseded)  --SUPERSEDES-->  'Canada' (current)
owns_vehicle:      'motorcycle' (superseded) --SUPERSEDES-->  'SUV'    (current)
```

A vector search over chunks retrieves *both* `27:12` and `25:50` by similarity
with no way to tell which is current — the failure the `SUPERSEDES` edge fixes.

### 2. Abstention — decline when the graph has no support

Question `0862e8bf_abs`: *"What is the name of my hamster?"* — never stated.
Engram holds 149 current facts about the user (including the cat, *Luna*), finds
no fact about a hamster, and abstains instead of guessing:

```
A: [ABSTAINED — not supported by memory]
gold: "You did not mention this... you mentioned your cat Luna but not a hamster."  ✓
```

This is the beat full-context prompting fails: it hallucinates a name; Engram
returns an empty evidence set and declines.

## Honest limitations

- **Extraction consistency depends on the model.** Strong models extract the
  same real-world attribute under one predicate across sessions, so supersession
  links cleanly (example 1 above). Small free models (e.g. `gpt-oss-20b/120b`)
  *drift* — the same fact becomes `personal_best_5k_time` in one session and
  `personal_best_time` in another — so the two values don't group and the update
  is missed. This is a model-quality gap, addressable with predicate
  canonicalization (planned) or a stronger extractor.
- **Multi-session aggregation** (counting across sessions) and **temporal
  date-arithmetic** are harder for the answer step than single-fact recall.

## Benchmark

Engram vs a vector-RAG baseline on LongMemEval-S, same model (gpt-4o-mini via
OpenRouter) for retrieval-answering on both, LLM-judged, small sample. Chart in
`results/engram_vs_baseline.png`, raw scores in `results/summary.csv`.

| category | Engram | Vector-RAG |
|---|---|---|
| knowledge-update | 5/7 (71%) | 4/6 (67%) |
| multi-session | 3/10 (30%) | 2/10 (20%) |
| abstention | 5/5 (100%) | 5/5 (100%) |
| temporal-reasoning | 1/5 (20%) | 3/5 (60%) |

**Read this honestly.** On a small sample the two systems are close overall.
Engram is nominally ahead on multi-session and knowledge-update, tied on
abstention, and clearly behind on temporal reasoning — date arithmetic over
events, where the raw chunks a vector retriever returns preserve exact dates
better than extracted facts do. A clean N=5-per-category slice was even kinder to
Engram on knowledge-update (5/5), but that was small-sample luck; the larger
sample above is the number to trust.

What the benchmark does **not** capture, and what actually distinguishes Engram,
are the two behaviours in the verified examples above: a **provenance receipt**
for every fact, and **evidence-backed abstention** — neither of which a vector
retriever provides. The accuracy is competitive; the auditability and the refusal
to guess are the point.

Reproduce / extend:

```bash
python -m bench.run_longmemeval --n 10 && python -m bench.plot
```
