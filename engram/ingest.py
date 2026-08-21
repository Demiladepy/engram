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


import re

_NONWORD = re.compile(r"[^a-z0-9]+")


def _norm_predicate(pred: str) -> str:
    """Snake-case a predicate so the same relation groups across sessions even
    when the model phrases it differently ('lives in' -> 'lives_in')."""
    return _NONWORD.sub("_", str(pred).strip().lower()).strip("_")


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

    # Build sessions + messages first, remembering each turn's global tag
    # (s{i}t{j}) -> message id and each session's timestamp, so batched
    # extraction can point a fact back to its exact source turn.
    msg_by_tag: dict[str, int] = {}
    ts_by_i: dict[int, int] = {}
    session_blocks: dict[int, str] = {}
    for idx, i in enumerate(order):
        sid = inst["haystack_session_ids"][i]
        turns = inst["haystack_sessions"][i]
        sts = to_epoch(inst["haystack_dates"][i])
        ts_by_i[i] = sts
        s_id = nid("session", sid)
        b.sessions.append({"id": s_id, "idx": idx, "ts": sts, "sid": sid})

        lines = [f"## session s{i}"]
        for j, t in enumerate(turns):
            tag = f"s{i}t{j}"
            m_id = nid("msg", f"{sid}:{j}")
            msg_by_tag[tag] = m_id
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
            # Only user turns feed extraction — the assistant's text states no
            # user facts, and dropping it ~halves the tokens the LLM must read.
            if t["role"] == "user":
                lines.append(f"[{tag}] {t['content']}")
        session_blocks[i] = "\n".join(lines)

    # Batch sessions into a few extraction calls (char budget) to stay under
    # free-tier rate limits, then extract batches concurrently.
    budget = int(os.environ.get("ENGRAM_EXTRACT_BATCH_CHARS", "3500"))
    batches: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for i in order:
        blk = session_blocks[i]
        if cur and cur_len + len(blk) > budget:
            batches.append("\n\n".join(cur))
            cur, cur_len = [], 0
        cur.append(blk)
        cur_len += len(blk)
    if cur:
        batches.append("\n\n".join(cur))

    workers = int(os.environ.get("ENGRAM_EXTRACT_WORKERS", "6"))
    with cf.ThreadPoolExecutor(max_workers=max(1, min(workers, len(batches)))) as ex:
        results = list(ex.map(llm.extract_facts_batch, batches))

    tag_re = re.compile(r"s(\d+)t(\d+)")
    for facts in results:
        for f in facts:
            entity = str(f.get("entity", "")).strip().lower()
            predicate = _norm_predicate(f.get("predicate", ""))
            obj = str(f.get("object", "")).strip()
            tag_m = tag_re.search(str(f.get("source", "")))
            if not (entity and predicate and obj and tag_m):
                continue
            i = int(tag_m.group(1))
            if i not in ts_by_i:  # hallucinated session index
                continue
            tag = f"s{tag_m.group(1)}t{tag_m.group(2)}"
            e_id = nid("entity", entity)
            b.entities.append({"id": e_id, "canonical": entity})
            f_id = nid("fact", f"{tag}:{entity}:{predicate}:{obj}")
            b.facts[f_id] = {
                "id": f_id,
                "predicate": predicate,
                "object": obj,
                "valid_from": ts_by_i[i],
                "valid_to": VALID_TO_OPEN,
                "status": "current",
                "confidence": 1.0,
                # carried for supersession, not written as node props:
                "_entity": entity,
            }
            b.about.append(b.edge("ABOUT", f_id, e_id))
            mid = msg_by_tag.get(tag)
            if mid is not None:
                b.states.append(b.edge("STATES", mid, f_id))

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


def _canon_predicates(preds: set[str]) -> dict[str, str]:
    """Map near-duplicate predicate names to one canonical form, so the same
    real-world attribute extracted under drifting names (e.g.
    'charity_5k_personal_best_time' and 'personal_best_5k_time') still groups for
    supersession. Token-set Jaccard >= 0.6; the shorter name is the canonical."""
    def toks(p: str) -> set[str]:
        return {t for t in p.split("_") if t}

    canon: dict[str, str] = {}
    reps: list[tuple[str, set[str]]] = []
    for p in sorted(preds, key=len):  # shorter names become representatives
        tp = toks(p)
        match = None
        for rep, tr in reps:
            union = len(tp | tr)
            if union and len(tp & tr) / union >= 0.6:
                match = rep
                break
        if match:
            canon[p] = match
        else:
            reps.append((p, tp))
            canon[p] = p
    return canon


def _link_supersessions(b: _Batch) -> None:
    import collections

    by_entity: dict[str, list[dict]] = collections.defaultdict(list)
    for f in b.facts.values():
        by_entity[f["_entity"]].append(f)

    for facts in by_entity.values():
        canon = _canon_predicates({f["predicate"] for f in facts})
        groups: dict[str, list[dict]] = collections.defaultdict(list)
        for f in facts:
            groups[canon[f["predicate"]]].append(f)
        for chain in groups.values():
            chain.sort(key=lambda f: f["valid_from"])
            for older, newer in zip(chain, chain[1:]):
                if older["object"] == newer["object"]:
                    continue  # same value restated, not an update
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
