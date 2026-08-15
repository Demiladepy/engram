"""Deterministic ids, time parsing, and scoped-database naming.

HydraDB requires node ids to be non-negative integers, and stores only
int/float/bool/string property values (no null, no lists). Everything here
exists to bridge LongMemEval's string keys and timestamps into that world.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import datetime, timezone

# "still true" sentinel for Fact.valid_to — properties can't be null, so an
# open interval is a far-future epoch instead. 2286-11-20.
VALID_TO_OPEN = 9_999_999_999


def nid(kind: str, key: str) -> int:
    """Stable 48-bit non-negative int id for a node of a given kind.

    48 bits keeps us comfortably under 2**53 (JSON/JS safe-int) while leaving a
    collision probability of ~1e-5 at 50k nodes — fine for a per-question graph.
    """
    h = hashlib.blake2b(f"{kind}\x00{key}".encode(), digest_size=6).digest()
    return int.from_bytes(h, "big")


_DAY = re.compile(r"\s*\([A-Za-z]{3}\)")


def to_epoch(stamp: str) -> int:
    """Parse LongMemEval's `2023/06/25 (Sun) 13:22` into UTC epoch seconds."""
    cleaned = _DAY.sub("", stamp).strip()
    dt = datetime.strptime(cleaned, "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def scope_db(collection: str, tenant: str = "engram", root: str = "default") -> str:
    """HydraDB scoped-database name isolating one collection's graph.

    Matches the `root.scope1.<b64(tenant)>.<b64(collection)>` form HydraDB's own
    runtime smoke uses. Each LongMemEval question gets its own scope, so their
    haystacks never contaminate each other and nothing needs clearing between.
    """
    return f"{root}.scope1.{_b64(tenant)}.{_b64(collection)}"
