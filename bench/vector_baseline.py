"""Vector-RAG baseline: embed history chunks, retrieve top-k, answer.

This is the comparison the thesis targets. Retrieval by similarity is blind to
supersession and recency: for a knowledge-update question it may surface the old
value, the new one, or both — with no way to tell which is current. That is the
exact failure the graph is built to avoid. Embeddings run locally (fastembed /
ONNX, no API); only the final answer uses the same Claude model as every other
system, so the comparison stays apples-to-apples.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from engram import llm

_EMBED = None
_ABSTAIN_HINTS = (
    "don't have", "do not have", "not have that information", "no information",
    "didn't mention", "did not mention", "not mentioned", "isn't in", "not in the",
)


def _embedder():
    global _EMBED
    if _EMBED is None:
        from fastembed import TextEmbedding

        _EMBED = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _EMBED


_MAX_CHUNKS = 600


def _chunks(instance: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for date, sess in zip(instance["haystack_dates"], instance["haystack_sessions"]):
        for t in sess:
            # User turns carry the facts; skipping assistant turns roughly halves
            # the CPU embedding cost per instance without losing answer content.
            if t["role"] == "user":
                out.append(f"[{date}] {t['content']}")
    # Cap the corpus so a very large haystack can't make embedding take minutes;
    # keep the most recent, which is where current facts live.
    return out[-_MAX_CHUNKS:]


def vector_rag(instance: dict[str, Any], k: int = 12) -> dict[str, Any]:
    chunks = _chunks(instance)
    vecs = np.asarray(list(_embedder().embed(chunks + [instance["question"]])), dtype=float)
    corpus, query = vecs[:-1], vecs[-1]
    sims = corpus @ query / (np.linalg.norm(corpus, axis=1) * np.linalg.norm(query) + 1e-9)
    top = sorted(sims.argsort()[::-1][:k])
    context = "\n".join(chunks[i] for i in top)
    ans = llm.answer_full_context(instance["question"], context)
    low = ans.lower()
    abstained = any(p in low for p in _ABSTAIN_HINTS)
    return {"answer": "" if abstained else ans, "abstained": abstained}
