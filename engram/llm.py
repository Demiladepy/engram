"""Claude calls: fact extraction (ingest) and evidence-bound answering.

Both use forced tool-use so the model returns structured data instead of prose
we'd have to parse. One provider, one place.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import anthropic

_CACHE = Path(os.environ.get("ENGRAM_CACHE", str(Path.home() / "hydra" / "engram-cache")))


def _cache_get(key: str) -> Any | None:
    fp = _CACHE / f"{key}.json"
    if fp.exists():
        return json.loads(fp.read_text())
    return None


def _cache_put(key: str, value: Any) -> None:
    _CACHE.mkdir(parents=True, exist_ok=True)
    (_CACHE / f"{key}.json").write_text(json.dumps(value))

_client: anthropic.Anthropic | None = None

_RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=0)  # we retry explicitly
    return _client


def _create(**kwargs: Any) -> Any:
    """messages.create with backoff — WSL/network blips must not kill a long run."""
    delay = 1.0
    for attempt in range(6):
        try:
            return client().messages.create(**kwargs)
        except _RETRYABLE as exc:
            if attempt == 5:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 20.0)
    raise RuntimeError("unreachable")


def _model() -> str:
    return os.environ.get("ENGRAM_LLM_MODEL", "claude-sonnet-5")


def _tool_result(resp: Any, tool_name: str) -> dict[str, Any]:
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise ValueError(f"model did not call {tool_name}: {resp.stop_reason}")


# --- extraction -----------------------------------------------------------

_EXTRACT_TOOL = {
    "name": "record_facts",
    "description": "Record durable facts stated by the user in this session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "Canonical lowercase subject. Use 'user' for the human.",
                        },
                        "predicate": {
                            "type": "string",
                            "description": "Normalized snake_case relation, e.g. personal_best_5k_time, lives_in, job_title. Reuse the SAME predicate string for the same kind of fact across sessions.",
                        },
                        "object": {
                            "type": "string",
                            "description": "The value, as a short string.",
                        },
                        "source_turn": {
                            "type": "integer",
                            "description": "Index of the turn that states this fact.",
                        },
                    },
                    "required": ["entity", "predicate", "object", "source_turn"],
                },
            }
        },
        "required": ["facts"],
    },
}

_EXTRACT_SYS = (
    "You extract durable, factual statements the user makes about themselves or "
    "their world (preferences, attributes, possessions, relationships, dated "
    "events with concrete values). Ignore small talk, questions, hypotheticals, "
    "and the assistant's own text. Prefer specific values. Use canonical "
    "snake_case predicates and reuse them for the same kind of fact so later "
    "updates line up. Only record what is actually stated."
)


def extract_facts(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return facts stated in one session's turns.

    ``turns`` is ``[{'index': i, 'role': r, 'content': c}, ...]``.
    """
    lines = [f"[{t['index']}] {t['role']}: {t['content']}" for t in turns]
    payload = "\n".join(lines)
    key = hashlib.blake2b(
        f"extract\x00{_model()}\x00{_EXTRACT_SYS}\x00{payload}".encode(), digest_size=16
    ).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached
    resp = _create(
        model=_model(),
        max_tokens=2048,
        system=_EXTRACT_SYS,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "record_facts"},
        messages=[{"role": "user", "content": payload}],
    )
    facts = _tool_result(resp, "record_facts").get("facts", [])
    _cache_put(key, facts)
    return facts


# --- answering ------------------------------------------------------------

_ANSWER_TOOL = {
    "name": "answer",
    "description": "Answer the question using ONLY the provided evidence facts.",
    "input_schema": {
        "type": "object",
        "properties": {
            "abstained": {
                "type": "boolean",
                "description": "True if the evidence does not support any answer.",
            },
            "answer": {
                "type": "string",
                "description": "The answer, or empty string if abstaining.",
            },
            "used_fact_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Ids of the evidence facts the answer relied on.",
            },
        },
        "required": ["abstained", "answer", "used_fact_ids"],
    },
}

_ANSWER_SYS = (
    "You answer strictly from the supplied evidence facts and nothing else. "
    "Each fact has an id, a subject, a relation, a value, and when it was true. "
    "If the evidence does not contain the answer, you MUST abstain — set "
    "abstained=true and answer=''. Never guess or use outside knowledge. When "
    "facts conflict over time, prefer the one marked current."
)


def answer(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Answer ``question`` from ``evidence`` facts, or abstain.

    Each evidence item: ``{id, subject, predicate, object, status, valid_from,
    source}``.
    """
    if not evidence:
        return {"abstained": True, "answer": "", "used_fact_ids": []}
    facts_text = "\n".join(
        f"id={f['id']} | {f['subject']} {f['predicate']} = {f['object']} "
        f"| status={f['status']} | when={f['valid_from']} | source={f.get('source', '')!r}"
        for f in evidence
    )
    resp = _create(
        model=_model(),
        max_tokens=1024,
        system=_ANSWER_SYS,
        tools=[_ANSWER_TOOL],
        tool_choice={"type": "tool", "name": "answer"},
        messages=[
            {
                "role": "user",
                "content": f"Question: {question}\n\nEvidence facts:\n{facts_text}",
            }
        ],
    )
    return _tool_result(resp, "answer")
