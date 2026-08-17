"""LLM calls behind one provider-agnostic layer (OpenAI-compatible).

Points at Groq by default (free tier, fast). Any OpenAI-compatible endpoint —
Ollama at localhost:11434/v1, Together, OpenAI itself — works by setting
ENGRAM_LLM_BASE_URL and ENGRAM_LLM_KEY_ENV. Models are chosen per role so the
cheap/fast model does the high-volume work and a stronger one answers:

    ENGRAM_EXTRACT_MODEL  default llama-3.1-8b-instant   (high volume, cached)
    ENGRAM_ANSWER_MODEL   default llama-3.3-70b-versatile
    ENGRAM_JUDGE_MODEL    default llama-3.1-8b-instant

Structured outputs use function-calling; results are cached on disk keyed by
model+prompt, so re-runs and iteration cost nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

_CACHE = Path(os.environ.get("ENGRAM_CACHE", str(Path.home() / "hydra" / "engram-cache")))
_RETRYABLE = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


def _cache_get(key: str) -> Any | None:
    fp = _CACHE / f"{key}.json"
    return json.loads(fp.read_text()) if fp.exists() else None


def _cache_put(key: str, value: Any) -> None:
    _CACHE.mkdir(parents=True, exist_ok=True)
    (_CACHE / f"{key}.json").write_text(json.dumps(value))


_clients: dict[tuple[str, str], OpenAI] = {}


def _client_for(role: str) -> OpenAI:
    """OpenAI-compatible client for a role, with per-role endpoint override.

    Each role (extract/answer/judge) can point at a different provider via
    ENGRAM_<ROLE>_BASE_URL / ENGRAM_<ROLE>_KEY_ENV, else the global
    ENGRAM_LLM_* is used. This is what lets high-volume extraction run on a
    local Ollama node while answering/judging stay on a hosted model.
    """
    r = role.upper()
    base = os.environ.get(f"ENGRAM_{r}_BASE_URL") or os.environ.get(
        "ENGRAM_LLM_BASE_URL", "https://api.groq.com/openai/v1"
    )
    key_env = os.environ.get(f"ENGRAM_{r}_KEY_ENV") or os.environ.get(
        "ENGRAM_LLM_KEY_ENV", "GROQ_API_KEY"
    )
    key = os.environ.get(key_env) or os.environ.get("OPENAI_API_KEY") or "ollama"
    ck = (base, key)
    if ck not in _clients:
        _clients[ck] = OpenAI(base_url=base, api_key=key, max_retries=0)
    return _clients[ck]


def _extract_model() -> str:
    # gpt-oss respects tool schemas (integer types); the llama tool models on
    # Groq either mangle predicates (8b) or emit wrong types (70b). 120b has
    # noticeably higher free-tier throughput than 20b, which matters for the
    # high-volume extraction step even after batching.
    return os.environ.get("ENGRAM_EXTRACT_MODEL", "openai/gpt-oss-120b")


def _answer_model() -> str:
    return os.environ.get("ENGRAM_ANSWER_MODEL", "openai/gpt-oss-120b")


def _judge_model() -> str:
    return os.environ.get("ENGRAM_JUDGE_MODEL", "openai/gpt-oss-20b")


def _create(role: str, **kwargs: Any) -> Any:
    """chat.completions.create with backoff — transient blips must not kill a
    long run, but a per-DAY token cap will not reset for hours, so fail fast on
    it instead of burning 30s×8 retries per call."""
    delay = 2.0
    for attempt in range(8):
        try:
            return _client_for(role).chat.completions.create(**kwargs)
        except RateLimitError as exc:
            msg = str(exc).lower()
            if "per day" in msg or "tpd" in msg:
                raise  # daily cap — retrying is pointless
            if attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 1.8, 30.0)
        except (APIConnectionError, APITimeoutError, InternalServerError):
            if attempt == 7:
                raise
            time.sleep(delay)
            delay = min(delay * 1.8, 30.0)
    raise RuntimeError("unreachable")


def _call_tool(
    role: str,
    model: str,
    system: str,
    user: str,
    fn_name: str,
    parameters: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """Force a single function call and return its parsed arguments.

    Falls back to parsing JSON from message content for models/endpoints that
    don't honour forced tool_choice (e.g. some local models).
    """
    resp = _create(
        role,
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        tools=[{"type": "function", "function": {"name": fn_name, "parameters": parameters}}],
        tool_choice={"type": "function", "function": {"name": fn_name}},
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.loads(msg.tool_calls[0].function.arguments)
    return json.loads(_first_json_object(msg.content or ""))


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return "{}"
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return "{}"


# --- extraction -----------------------------------------------------------

_EXTRACT_PARAMS = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Canonical lowercase subject. Use 'user' for the human."},
                    "predicate": {"type": "string", "description": "Normalized snake_case relation, e.g. personal_best_5k_time, lives_in, job_title. Reuse the SAME predicate string for the same kind of fact across sessions."},
                    "object": {"type": "string", "description": "The value, as a short string."},
                    "source_turn": {"type": "integer", "description": "Index of the turn that states this fact."},
                },
                "required": ["entity", "predicate", "object", "source_turn"],
            },
        }
    },
    "required": ["facts"],
}

_EXTRACT_SYS = (
    "You extract durable, factual statements the user makes about themselves or "
    "their world (preferences, attributes, possessions, relationships, dated "
    "events with concrete values). Ignore small talk, questions, hypotheticals, "
    "and the assistant's own text. Prefer specific values. Use canonical "
    "snake_case predicates and reuse them for the same kind of fact so later "
    "updates line up. Only record what is actually stated. Call record_facts."
)


def extract_facts(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = "\n".join(f"[{t['index']}] {t['role']}: {t['content']}" for t in turns)
    model = _extract_model()
    key = hashlib.blake2b(f"extract\x00{model}\x00{payload}".encode(), digest_size=16).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        out = _call_tool("extract", model, _EXTRACT_SYS, payload, "record_facts", _EXTRACT_PARAMS, 2048)
        facts = out.get("facts", []) if isinstance(out, dict) else []
    except Exception:
        return []  # flaky call: don't cache, so it retries next run
    _cache_put(key, facts)  # cache only real results
    return facts


_EXTRACT_BATCH_PARAMS = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Canonical lowercase subject. Use 'user' for the human."},
                    "predicate": {"type": "string", "description": "Normalized snake_case relation; reuse the SAME predicate for the same kind of fact across sessions."},
                    "object": {"type": "string", "description": "The value, as a short string."},
                    "source": {"type": "string", "description": "Tag of the turn that states this fact, e.g. s3t12."},
                },
                "required": ["entity", "predicate", "object", "source"],
            },
        }
    },
    "required": ["facts"],
}

_EXTRACT_BATCH_SYS = _EXTRACT_SYS + (
    " Turns are tagged like [s3t12] meaning session 3, turn 12. For every fact, "
    "set source to the exact tag of the turn that states it. The input may hold "
    "several sessions — read EVERY session and turn and extract facts from all of "
    "them; do not skip any. Be thorough: capture specific values (times, dates, "
    "names, numbers, places) the user states."
)


def extract_facts_batch(payload: str) -> list[dict[str, Any]]:
    """Extract facts from several tagged sessions in one call — far fewer calls
    than one-per-session, which is what keeps us under free-tier rate limits."""
    model = _extract_model()
    key = hashlib.blake2b(f"extractbatch\x00{model}\x00{payload}".encode(), digest_size=16).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        out = _call_tool("extract", model, _EXTRACT_BATCH_SYS, payload, "record_facts", _EXTRACT_BATCH_PARAMS, 4096)
        facts = out.get("facts", []) if isinstance(out, dict) else []
    except Exception:
        return []  # flaky call: don't cache, retry next run
    _cache_put(key, facts)
    return facts


# --- answering ------------------------------------------------------------

_ANSWER_PARAMS = {
    "type": "object",
    "properties": {
        "abstained": {"type": "boolean", "description": "True if the evidence does not support any answer."},
        "answer": {"type": "string", "description": "The answer, or empty string if abstaining."},
        "used_fact_ids": {"type": "array", "items": {"type": "integer"}, "description": "Ids of the evidence facts the answer relied on."},
    },
    "required": ["abstained", "answer", "used_fact_ids"],
}

_ANSWER_SYS = (
    "You answer a question about a user using ONLY the supplied evidence facts. "
    "Each fact has an id, a subject, a relation, a value, and 'when' (a timestamp "
    "it became true). Rules:\n"
    "- Match facts to the question by MEANING, not exact wording (e.g. "
    "'personal_best_time' answers a question about a personal best time in a run).\n"
    "- If several facts could answer — typically an older and a newer value of the "
    "same thing — choose the one with the LATEST 'when'; that is the current value. "
    "A fact marked status=current also wins over status=superseded.\n"
    "- Only abstain (abstained=true, answer='') when NO fact is relevant to the "
    "question. Do not abstain merely because wording differs or values conflict.\n"
    "- Never use outside knowledge. List the fact ids you relied on in "
    "used_fact_ids. Call answer."
)


def answer(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not evidence:
        return {"abstained": True, "answer": "", "used_fact_ids": []}
    facts_text = "\n".join(
        f"id={f['id']} | {f['subject']} {f['predicate']} = {f['object']} "
        f"| status={f['status']} | when={f['valid_from']} | source={f.get('source_text', '')!r}"
        for f in evidence
    )
    user = f"Question: {question}\n\nEvidence facts:\n{facts_text}"
    try:
        out = _call_tool("answer", _answer_model(), _ANSWER_SYS, user, "answer", _ANSWER_PARAMS, 1024)
    except Exception:
        return {"abstained": True, "answer": "", "used_fact_ids": []}
    out.setdefault("abstained", False)
    out.setdefault("answer", "")
    out.setdefault("used_fact_ids", [])
    return out


# --- baseline: full-context ----------------------------------------------

_FULLCTX_SYS = (
    "You are a long-term memory assistant. Answer the user's question using only "
    "the conversation history provided. If the history does not contain the "
    "answer, reply that you don't have that information — do not guess. Keep the "
    "answer to one short sentence."
)


def answer_full_context(question: str, history_text: str) -> str:
    """Baseline answerer over raw context (used by full-context and vector-RAG)."""
    model = _answer_model()
    key = hashlib.blake2b(
        f"fullctx\x00{model}\x00{question}\x00{history_text}".encode(), digest_size=16
    ).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached
    resp = _create(
        "answer",
        model=model,
        max_tokens=256,
        temperature=0,
        messages=[
            {"role": "system", "content": _FULLCTX_SYS},
            {"role": "user", "content": f"{history_text}\n\nQuestion: {question}"},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    _cache_put(key, text)
    return text


# --- grading --------------------------------------------------------------

_JUDGE_PARAMS = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "reason": {"type": "string", "description": "Brief justification."},
    },
    "required": ["correct", "reason"],
}

_JUDGE_SYS = (
    "You grade a candidate answer against a gold answer for a question about a "
    "user's own chat history. Mark correct=true if the candidate conveys the same "
    "essential fact as the gold answer (paraphrase and extra harmless detail are "
    "fine). IMPORTANT: when the gold answer indicates the information was never "
    "stated / is not available, correct=true ONLY if the candidate also declines "
    "or says it doesn't have that information; a candidate that states a concrete "
    "answer in that case is incorrect. Call grade."
)


def judge(question: str, gold: str, candidate: str) -> dict[str, Any]:
    model = _judge_model()
    key = hashlib.blake2b(
        f"judge\x00{model}\x00{question}\x00{gold}\x00{candidate}".encode(), digest_size=16
    ).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        return cached
    user = (
        f"Question: {question}\nGold answer: {gold}\n"
        f"Candidate answer: {candidate or '(no answer / abstained)'}"
    )
    try:
        out = _call_tool("judge", model, _JUDGE_SYS, user, "grade", _JUDGE_PARAMS, 256)
        result = {"correct": bool(out.get("correct", False)), "reason": str(out.get("reason", ""))}
    except Exception as exc:
        return {"correct": False, "reason": f"judge error: {exc}"}  # don't cache errors
    _cache_put(key, result)
    return result
