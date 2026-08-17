"""HydraDB client.

Thin wrapper over the official ``neo4j`` Bolt driver. HydraDB speaks the Bolt
protocol on ``127.0.0.1:7687`` and OpenCypher, so the Neo4j driver is the
supported client (its own smoke scripts use it). All Engram graph I/O goes
through here.

Connection settings come from the environment so the same code works against a
local plaintext node and a TLS one:

    HYDRA_BOLT_URI   default bolt://127.0.0.1:7687   (direct, single node)
    HYDRA_USER       default neo4j
    HYDRA_PASSWORD   the node's auth token (required even in plaintext mode)
    HYDRA_DATABASE   default "default"
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, SessionExpired


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Hydra:
    """Owns a Bolt driver and hands out sessions/queries."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.uri = uri or _env("HYDRA_BOLT_URI", "bolt://127.0.0.1:7687")
        self.user = user or _env("HYDRA_USER", "neo4j")
        self.password = password if password is not None else _env("HYDRA_PASSWORD", "")
        self.database = database or _env("HYDRA_DATABASE", "default")
        self._driver: Driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            keep_alive=True,
            # Ping any connection idle longer than this before reuse, so a
            # connection the node dropped during a long gap (e.g. while the
            # vector baseline embeds) is replaced instead of read as defunct.
            liveness_check_timeout=10,
            max_connection_lifetime=300,
        )

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "Hydra":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def verify(self) -> None:
        """Raise if the server is unreachable."""
        self._driver.verify_connectivity()

    def run(
        self, cypher: str, database: str | None = None, **params: Any
    ) -> list[dict[str, Any]]:
        """Execute one Cypher statement, return rows as dicts.

        ``database`` overrides the default (used for per-question scoped DBs).
        Retries once on a dropped connection: autocommit queries don't get the
        managed-transaction retry, so we discard a defunct pooled connection and
        try again on a fresh one.
        """
        db = database or self.database
        last: Exception | None = None
        for _ in range(3):
            try:
                with self._driver.session(database=db) as session:
                    result = session.run(cypher, **params)
                    return [record.data() for record in result]
            except (ServiceUnavailable, SessionExpired) as exc:
                last = exc
        raise last  # type: ignore[misc]

    @contextmanager
    def session(self, database: str | None = None) -> Iterator[Any]:
        with self._driver.session(database=database or self.database) as session:
            yield session

    # --- batched writes (HydraDB UNWIND forms; see cypher-compat.md) ---

    # Rows per UNWIND query. Each edge row does two MATCHes + a MERGE, so a big
    # instance's STATES batch can blow HydraDB's ~30s query timeout in one go —
    # chunk it so every query stays well under the limit.
    _CHUNK = 120

    def _run_chunked(self, cypher: str, rows: list[dict[str, Any]], database: str | None) -> None:
        for i in range(0, len(rows), self._CHUNK):
            self.run(cypher, database=database, rows=rows[i : i + self._CHUNK])

    def merge_nodes(
        self,
        label: str,
        rows: list[dict[str, Any]],
        props: list[str],
        database: str | None = None,
    ) -> None:
        """Upsert nodes: MERGE by integer id, then SET label + properties.

        Each row is a map carrying ``id`` plus every name in ``props``. Property
        values must be int/float/bool/string — never None.
        """
        if not rows:
            return
        sets = ", ".join(f"n.{p} = row.{p}" for p in props)
        cypher = f"UNWIND $rows AS row MERGE (n {{id: row.id}}) SET n:{label}"
        if sets:
            cypher += f", {sets}"
        self._run_chunked(cypher, rows, database)

    def merge_edges(
        self,
        rel: str,
        rows: list[dict[str, Any]],
        src_label: str,
        dst_label: str,
        props: list[str] | None = None,
        database: str | None = None,
    ) -> None:
        """Upsert relationships: MATCH labelled endpoints by id, MERGE the edge.

        Each row carries ``eid`` (edge id), ``src``, ``dst`` plus any ``props``.
        HydraDB requires exactly one label on each matched endpoint.
        """
        if not rows:
            return
        props = props or []
        sets = ", ".join(f"r.{p} = row.{p}" for p in props)
        cypher = (
            "UNWIND $rows AS row "
            f"MATCH (s:{src_label} {{id: row.src}}), (d:{dst_label} {{id: row.dst}}) "
            f"MERGE (s)-[r:{rel} {{id: row.eid}}]->(d)"
        )
        if sets:
            cypher += f" SET {sets}"
        self._run_chunked(cypher, rows, database)


if __name__ == "__main__":
    # Phase-1 smoke: CREATE then MATCH a trivial graph and print it back.
    #
    # HydraDB rules exercised here (see cypher-compat.md): node ids are
    # non-negative integers, CREATE only builds relationship paths, and each
    # request carries exactly one statement — so cleanup is two MATCH ... DELETE
    # calls, not a chained multi-statement.
    A, B = 90001, 90002
    with Hydra() as h:
        h.verify()
        h.run("MATCH (a {id:$id}) DETACH DELETE a", id=A)
        h.run("MATCH (b {id:$id}) DETACH DELETE b", id=B)
        h.run(
            "CREATE (a:EngramSmoke {id:$a, name:$an})"
            "-[:LINKS]->(b:EngramSmoke {id:$b, name:$bn})",
            a=A, an="hello", b=B, bn="hydradb",
        )
        rows = h.run(
            "MATCH (a:EngramSmoke {id:$a})-[:LINKS]->(b:EngramSmoke {id:$b}) "
            "RETURN a.name AS src, b.name AS dst",
            a=A, b=B,
        )
        print("round-trip rows:", rows)
        h.run("MATCH (a {id:$id}) DETACH DELETE a", id=A)
        h.run("MATCH (b {id:$id}) DETACH DELETE b", id=B)
        print("OK")
