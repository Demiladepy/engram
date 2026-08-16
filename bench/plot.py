"""Grouped bar chart from results/summary.csv — the tweet, and slide 1.

    python -m bench.plot
"""

from __future__ import annotations

import csv
import collections
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parent.parent / "results"

_LABELS = {
    "engram": "Engram (graph)",
    "vector": "Vector-RAG",
    "full_context": "Full-context",
    "mem0": "mem0-OSS",
}
_COLORS = {
    "engram": "#2f7d4f",
    "vector": "#5a5a8a",
    "full_context": "#b0562f",
    "mem0": "#8a5a5a",
}


def main() -> None:
    rows = list(csv.DictReader((RESULTS / "summary.csv").open()))
    cats, systems = [], []
    acc: dict[tuple[str, str], float] = {}
    ns: dict[tuple[str, str], int] = {}
    for r in rows:
        if r["category"] not in cats:
            cats.append(r["category"])
        if r["system"] not in systems:
            systems.append(r["system"])
        acc[(r["category"], r["system"])] = float(r["accuracy"])
        ns[(r["category"], r["system"])] = int(r["n"])

    x = range(len(cats))
    width = 0.8 / max(len(systems), 1)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for j, system in enumerate(systems):
        vals = [acc.get((c, system), 0.0) for c in cats]
        offs = [i + j * width for i in x]
        bars = ax.bar(offs, vals, width, label=_LABELS.get(system, system),
                      color=_COLORS.get(system, None))
        for b, c in zip(bars, cats):
            n = ns.get((c, system), 0)
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01,
                    f"{b.get_height():.0%}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks([i + width * (len(systems) - 1) / 2 for i in x])
    ax.set_xticklabels([c.replace("-", "-\n") for c in cats])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Accuracy (LLM-judged)")
    ax.set_title("Engram vs full-context on LongMemEval-S — graph-favouring subsets")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = RESULTS / "engram_vs_baseline.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
