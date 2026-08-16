"""Baselines answered in the SAME harness as Engram, with the SAME model.

Full-context is the strongest vector-free contender: the entire history is put
in front of the model, so nothing retrieval could surface is missing. The only
difference from Engram is *what memory feeds the model* — raw transcript here,
graph-resolved current facts there. That is the comparison the thesis rests on.
"""

from __future__ import annotations

from typing import Any

from engram import llm

# Keep the transcript within a generous window; -S haystacks almost all fit.
# If one exceeds it, we keep the most recent text (a realistic memory window),
# which is exactly where a full-context approach legitimately starts to lose.
_MAX_CHARS = 700_000


def history_text(instance: dict[str, Any], max_chars: int = _MAX_CHARS) -> str:
    parts: list[str] = []
    for sid, date, sess in zip(
        instance["haystack_session_ids"],
        instance["haystack_dates"],
        instance["haystack_sessions"],
    ):
        parts.append(f"### Session {sid} — {date}")
        for t in sess:
            parts.append(f"{t['role']}: {t['content']}")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def full_context(instance: dict[str, Any]) -> dict[str, Any]:
    """Answer straight from the full transcript. Returns {answer, abstained}."""
    ans = llm.answer_full_context(instance["question"], history_text(instance))
    low = ans.lower()
    abstained = any(
        p in low
        for p in ("don't have", "do not have", "not have that information", "no information", "didn't mention", "did not mention", "not mentioned")
    )
    return {"answer": ans, "abstained": abstained}
