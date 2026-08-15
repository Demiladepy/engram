"""Read path: question -> graph traversal -> temporal filter -> answer + receipt.

The graph does the work vectors can't: supersession has already collapsed each
(entity, predicate) history to a single `current` fact, so retrieval returns the
temporally-correct value, never a stale chunk. Every fact carries a `STATES`
edge back to the message that stated it — that edge is the receipt. When the
graph holds no supporting fact, we abstain instead of guessing.
"""

from __future__ import annotations

from typing import Any

from . import llm
from .graph import Hydra
from .ids import nid


def query_entities(question: str) -> list[str]:
    """Entities the question is about.

    v1 is user-centric — LongMemEval questions are overwhelmingly about the
    user, and 'user' is a canonical we always ingest. (TODO: NER for named
    entities, aligned to ingest's canonical forms.)
    """
    return ["user"]


def _temporal_filter(as_of: int | None) -> tuple[str, dict[str, Any]]:
    if as_of is None:
        return "f.status = 'current'", {}
    return "f.valid_from <= $asof AND f.valid_to > $asof", {"asof": as_of}


def retrieve(
    hydra: Hydra, db: str, entities: list[str], as_of: int | None = None
) -> list[dict[str, Any]]:
    """Evidence facts (temporally filtered) about the query entities, each with
    the source message that states it."""
    where, extra = _temporal_filter(as_of)
    evidence: list[dict[str, Any]] = []
    for canonical in entities:
        uid = nid("entity", canonical)
        rows = hydra.run(
            "MATCH (m:Message)-[:STATES]->(f:Fact)-[:ABOUT]->(e:Entity {id:$uid}) "
            f"WHERE {where} "
            "RETURN f.predicate AS predicate, f.object AS object, f.status AS status, "
            "f.valid_from AS valid_from, f.valid_to AS valid_to, "
            "m.sid AS source_session, m.text AS source_text ORDER BY predicate",
            database=db,
            uid=uid,
            **extra,
        )
        for r in rows:
            r["subject"] = canonical
            r["id"] = len(evidence) + 1
            evidence.append(r)
    return evidence


def predecessor(hydra: Hydra, db: str, subject: str, predicate: str) -> dict[str, Any] | None:
    """The value a current fact overrode — the SUPERSEDES step, for the receipt."""
    uid = nid("entity", subject)
    rows = hydra.run(
        "MATCH (new:Fact)-[:SUPERSEDES]->(old:Fact)-[:ABOUT]->(e:Entity {id:$uid}) "
        "WHERE new.predicate = $p AND new.status = 'current' "
        "RETURN old.object AS object, old.valid_from AS valid_from, old.valid_to AS valid_to",
        database=db,
        uid=uid,
        p=predicate,
    )
    return rows[0] if rows else None


def answer_question(
    hydra: Hydra, db: str, question: str, as_of: int | None = None
) -> dict[str, Any]:
    entities = query_entities(question)
    evidence = retrieve(hydra, db, entities, as_of)
    verdict = llm.answer(question, evidence)
    used = set(verdict.get("used_fact_ids", []))

    receipt = []
    for e in evidence:
        if e["id"] in used:
            receipt.append(
                {"fact": e, "superseded": predecessor(hydra, db, e["subject"], e["predicate"])}
            )

    return {
        "question": question,
        "abstained": bool(verdict.get("abstained", not evidence)),
        "answer": verdict.get("answer", ""),
        "entities": entities,
        "evidence_count": len(evidence),
        "receipt": receipt,
    }


def _print_result(res: dict[str, Any], gold: str | None = None) -> None:
    print("\nQ:", res["question"])
    if res["abstained"]:
        print("A: [ABSTAINED — not supported by memory]")
    else:
        print("A:", res["answer"])
    if gold is not None:
        print("gold:", gold)
    print(f"(traversed entities={res['entities']}, evidence facts={res['evidence_count']})")
    for item in res["receipt"]:
        f = item["fact"]
        print(f"  RECEIPT · {f['predicate']} = {f['object']}  [status={f['status']}]")
        print(f"      stated in session {f['source_session']}: {f['source_text'][:120]!r}")
        if item["superseded"]:
            s = item["superseded"]
            print(f"      superseded earlier value: {s['object']!r} (valid until {f['valid_from']})")


if __name__ == "__main__":
    import sys

    from dotenv import find_dotenv, load_dotenv

    from .ingest import ingest_instance, load_dataset
    from .ids import to_epoch

    load_dotenv(find_dotenv(usecwd=True))
    qtype = sys.argv[1] if len(sys.argv) > 1 else "knowledge-update"
    data = load_dataset()
    inst = next(d for d in data if d["question_type"] == qtype)

    with Hydra() as h:
        h.verify()
        info = ingest_instance(h, inst)  # cached extractions -> cheap re-run
        res = answer_question(h, info["database"], inst["question"])
        _print_result(res, gold=inst["answer"])
