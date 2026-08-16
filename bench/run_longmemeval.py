"""LongMemEval harness: Engram vs full-context, same model, same questions.

Runs the graph-favouring subsets, grades every answer with an LLM judge, and
writes a per-category CSV. Resumable: results are appended to a JSONL and
(question_id, system) pairs already present are skipped, so scaling N or adding
a system only does the new work. Extraction/answers/judgements are all cached,
so a re-run is cheap.

    python -m bench.run_longmemeval --n 5
    python -m bench.run_longmemeval --n 20 --categories multi-session,knowledge-update
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import time
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv

RESULTS = Path(__file__).resolve().parent.parent / "results"
RAW = RESULTS / "raw.jsonl"

# Graph-favouring subsets — where vectors are known to fail (build plan §6).
CATEGORIES = ["multi-session", "knowledge-update", "temporal-reasoning", "abstention"]


def select(data: list[dict], categories: list[str], n: int) -> list[tuple[str, dict]]:
    """Deterministically pick up to n instances per category. Abstention is the
    `_abs` questions; other categories exclude `_abs` so they stay pure."""
    picks: list[tuple[str, dict]] = []
    for cat in categories:
        count = 0
        for d in data:
            is_abs = str(d["question_id"]).endswith("_abs")
            if cat == "abstention":
                match = is_abs
            else:
                match = (d["question_type"] == cat) and not is_abs
            if match:
                picks.append((cat, d))
                count += 1
                if count >= n:
                    break
    return picks


def load_done() -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if RAW.exists():
        for line in RAW.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["question_id"], r["system"]))
    return done


def append(row: dict[str, Any]) -> None:
    RESULTS.mkdir(exist_ok=True)
    with RAW.open("a") as f:
        f.write(json.dumps(row) + "\n")


def run_engram(hydra, inst: dict) -> dict[str, Any]:
    from engram.answer import answer_question
    from engram.ingest import ingest_instance

    info = ingest_instance(hydra, inst)  # cached extractions
    res = answer_question(hydra, info["database"], inst["question"])
    candidate = "" if res["abstained"] else res["answer"]
    return {"answer": candidate, "abstained": res["abstained"], "extra": info["counts"]}


def run_full_context(inst: dict) -> dict[str, Any]:
    from bench import baselines

    out = baselines.full_context(inst)
    return {"answer": "" if out["abstained"] else out["answer"], "abstained": out["abstained"], "extra": {}}


def run_vector(inst: dict) -> dict[str, Any]:
    from bench import vector_baseline

    out = vector_baseline.vector_rag(inst)
    return {"answer": out["answer"], "abstained": out["abstained"], "extra": {}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5, help="instances per category")
    ap.add_argument("--categories", default=",".join(CATEGORIES))
    ap.add_argument("--systems", default="engram,vector")
    args = ap.parse_args()

    load_dotenv(find_dotenv(usecwd=True))
    from engram import llm
    from engram.graph import Hydra
    from engram.ingest import load_dataset

    cats = [c.strip() for c in args.categories.split(",") if c.strip()]
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    data = load_dataset()
    picks = select(data, cats, args.n)
    done = load_done()
    print(f"selected {len(picks)} instances across {cats}; systems={systems}")

    with Hydra() as hydra:
        hydra.verify()
        for i, (cat, inst) in enumerate(picks, 1):
            qid = inst["question_id"]
            for system in systems:
                if (qid, system) in done:
                    continue
                t0 = time.time()
                if system == "engram":
                    out = run_engram(hydra, inst)
                elif system == "vector":
                    out = run_vector(inst)
                else:
                    out = run_full_context(inst)
                grade = llm.judge(inst["question"], inst["answer"], out["answer"])
                row = {
                    "question_id": qid,
                    "category": cat,
                    "system": system,
                    "correct": bool(grade["correct"]),
                    "abstained": out["abstained"],
                    "candidate": out["answer"],
                    "gold": inst["answer"],
                    "reason": grade["reason"],
                    "seconds": round(time.time() - t0, 1),
                }
                append(row)
                mark = "OK " if row["correct"] else "XX "
                print(f"[{i}/{len(picks)}] {mark} {system:12s} {cat:18s} {qid}  ({row['seconds']}s)")

    summarize(cats, systems)


def summarize(cats: list[str], systems: list[str]) -> None:
    rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
    agg: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
    for r in rows:
        agg[(r["category"], r["system"])].append(1 if r["correct"] else 0)

    RESULTS.mkdir(exist_ok=True)
    csv_path = RESULTS / "summary.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "system", "n", "correct", "accuracy"])
        for cat in cats:
            for system in systems:
                v = agg.get((cat, system), [])
                if v:
                    w.writerow([cat, system, len(v), sum(v), round(sum(v) / len(v), 3)])

    print(f"\n=== accuracy (wrote {csv_path}) ===")
    header = "category".ljust(20) + "".join(s.ljust(16) for s in systems)
    print(header)
    for cat in cats:
        line = cat.ljust(20)
        for system in systems:
            v = agg.get((cat, system), [])
            line += (f"{sum(v)}/{len(v)} ({sum(v)/len(v):.0%})" if v else "-").ljust(16)
        print(line)


if __name__ == "__main__":
    main()
