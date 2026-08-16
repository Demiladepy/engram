"""Ingest one LongMemEval instance into a HydraDB provenance graph.

For each question we build an isolated scoped-database graph:

    (:Session)-[:CONTAINS]->(:Message)-[:STATES]->(:Fact)-[:ABOUT]->(:Entity)
    (:Fact)-[:SUPERSEDES]->(:Fact)     older <- newer, by valid_from

Facts about the same (entity, predicate) are ordered by time; each newer fact
supersedes the previous one and closes its validity interval. The latest stays
`current`; the rest become `superseded`. That chain is what answers
knowledge-update and temporal questions, and what the receipt renders.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
from typing import Any

from . import llm
from .graph import Hydra
from .ids import VALID_TO_OPEN, nid, scope_db, to_epoch

DATA_PATH = os.environ.get(
    "ENGRAM_DATA", "/home/user/hydra/longmemeval/data/longmemeval_s_cleaned.json"
)
_MAX_TEXT = 800


def load_dataset(path: str = DATA_PATH) -> list[dict[str, Any]]:
    with open(path) as fh:
        return json.load(fh)


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 1] + "…"


class _Batch:
    """Accumulates node/edge rows, flushes them as UNWIND writes."""

    def __init__(self) -> None:
        self.sessions: list[dict] = []
        self.messages: list[dict] = []
        self.entities: list[dict] = []
        self.facts: dict[int, dict] = {}  # id -> row (so supersession can revise)
        self.contains: list[dict] = []
        self.states: list[dict] = []
        self.about: list[dict] = []
        self.supersedes: list[dict] = []

    def edge(self, rel: str, src: int, dst: int, **props: Any) -> dict:
        return {"eid": nid("edge", f"{rel}:{src}:{dst}"), "src": src, "dst": dst, **props}


def ingest_instance(hydra: Hydra, inst: dict[str, Any]) -> dict[str, Any]:
    qid = inst["question_id"]
    db = scope_db(qid)
    b = _Batch()

    # Sessions ordered by their timestamp so idx reflects chronology.
    order = sorted(
        range(len(inst["haystack_sessions"])),
        key=lambda i: to_epoch(inst["haystack_dates"][i]),
    )

    # Fact extraction is the slow, independent-per-session step — run it
    # concurrently (cache hits return instantly; misses overlap their latency).
    indexed_by_i = {
        i: [
            {"index": j, "role": t["role"], "content": t["content"]}
            for j, t in enumerate(inst["haystack_sessions"][i])
        ]
        for i in order
    }
    workers = int(os.environ.get("ENGRAM_EXTRACT_WORKERS", "8"))
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        facts_by_i = dict(
            zip(order, ex.map(lambda i: llm.extract_facts(indexed_by_i[i]), order))
        )

    for idx, i in enumerate(order):
        sid = inst["haystack_session_ids"][i]
        turns = inst["haystack_sessions"][i]
        sts = to_epoch(inst["haystack_dates"][i])
        s_id = nid("session", sid)
        b.sessions.append({"id": s_id, "idx": idx, "ts": sts, "sid": sid})

        msg_ids: list[int] = []
        for j, t in enumerate(turns):
            m_id = nid("msg", f"{sid}:{j}")
            msg_ids.append(m_id)
            b.messages.append(
                {
                    "id": m_id,
                    "sid": sid,
                    "role": t["role"],
                    "ts": sts,
                    "turn": j,
                    "has_answer": bool(t.get("has_answer", False)),
                    "text": _clip(t["content"]),
                }
            )
            b.contains.append(b.edge("CONTAINS", s_id, m_id))

        # Attach the pre-extracted facts, with provenance to their source turns.
        for f in facts_by_i[i]:
            entity = str(f["entity"]).strip().lower()
            predicate = str(f["predicate"]).strip()
            obj = str(f["object"]).strip()
            src_turn = int(f.get("source_turn", 0))
            if not (entity and predicate and obj):
                continue
            e_id = nid("entity", entity)
            b.entities.append({"id": e_id, "canonical": entity})
            f_id = nid("fact", f"{sid}:{entity}:{predicate}:{obj}:{src_turn}")
            b.facts[f_id] = {
                "id": f_id,
                "predicate": predicate,
                "object": obj,
                "valid_from": sts,
                "valid_to": VALID_TO_OPEN,
                "status": "current",
                "confidence": 1.0,
                # carried for supersession, not written as node props:
                "_entity": entity,
            }
            b.about.append(b.edge("ABOUT", f_id, e_id))
            if 0 <= src_turn < len(msg_ids):
                b.states.append(b.edge("STATES", msg_ids[src_turn], f_id))

    _link_supersessions(b)
    _flush(hydra, db, b)

    return {
        "question_id": qid,
        "database": db,
        "counts": {
            "sessions": len(b.sessions),
            "messages": len(b.messages),
            "entities": len({e["id"] for e in b.entities}),
            "facts": len(b.facts),
            "supersedes": len(b.supersedes),
        },
    }


def _link_supersessions(b: _Batch) -> None:
    groups: dict[tuple[str, str], list[dict]] = {}
    for f in b.facts.values():
        groups.setdefault((f["_entity"], f["predicate"]), []).append(f)
    for chain in groups.values():
        chain.sort(key=lambda f: f["valid_from"])
        for older, newer in zip(chain, chain[1:]):
            older["status"] = "superseded"
            older["valid_to"] = newer["valid_from"]
            b.supersedes.append(b.edge("SUPERSEDES", newer["id"], older["id"]))


def _flush(hydra: Hydra, db: str, b: _Batch) -> None:
    hydra.merge_nodes("Session", b.sessions, ["idx", "ts", "sid"], database=db)
    hydra.merge_nodes(
        "Message", b.messages, ["sid", "role", "ts", "turn", "has_answer", "text"], database=db
    )
    # de-dup entity rows by id
    ents = list({e["id"]: e for e in b.entities}.values())
    hydra.merge_nodes("Entity", ents, ["canonical"], database=db)
    fact_rows = [
        {k: v for k, v in f.items() if not k.startswith("_")} for f in b.facts.values()
    ]
    hydra.merge_nodes(
        "Fact",
        fact_rows,
        ["predicate", "object", "valid_from", "valid_to", "status", "confidence"],
        database=db,
    )
    hydra.merge_edges("CONTAINS", b.contains, "Session", "Message", database=db)
    hydra.merge_edges("STATES", b.states, "Message", "Fact", database=db)
    hydra.merge_edges("ABOUT", b.about, "Fact", "Entity", database=db)
    hydra.merge_edges("SUPERSEDES", b.supersedes, "Fact", "Fact", database=db)


if __name__ == "__main__":
    import sys

    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    data = load_dataset()
    qtype = sys.argv[1] if len(sys.argv) > 1 else "knowledge-update"
    inst = next(d for d in data if d["question_type"] == qtype)
    print(f"ingesting {inst['question_id']} ({qtype}) — {len(inst['haystack_sessions'])} sessions")
    with Hydra() as h:
        h.verify()
        result = ingest_instance(h, inst)
    print(json.dumps(result, indent=2))
