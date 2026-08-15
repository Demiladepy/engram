"""HydraDB client.

Thin wrapper over the official ``neo4j`` Bolt driver. HydraDB speaks the Bolt
protocol on ``127.0.0.1:7687`` and OpenCypher, so the Neo4j driver is the
supported client (its own smoke scripts use it). All Engram graph I/O goes
through here.

Connection settings come from the environment so the same code works against a
local plaintext node and a TLS one:

    HYDRA_BOLT_URI   default neo4j://127.0.0.1:7687
    HYDRA_USER       default neo4j
    HYDRA_PASSWORD   default "" (plaintext local node)
    HYDRA_DATABASE   default neo4j
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import GraphDatabase, Driver


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
        self.uri = uri or _env("HYDRA_BOLT_URI", "neo4j://127.0.0.1:7687")
        self.user = user or _env("HYDRA_USER", "neo4j")
        self.password = password if password is not None else _env("HYDRA_PASSWORD", "")
        self.database = database or _env("HYDRA_DATABASE", "neo4j")
        self._driver: Driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password)
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

    def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        """Execute one Cypher statement, return rows as dicts."""
        with self._driver.session(database=self.database) as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    @contextmanager
    def session(self) -> Iterator[Any]:
        with self._driver.session(database=self.database) as session:
            yield session


if __name__ == "__main__":
    # Phase-1 smoke: CREATE then MATCH a trivial graph and print it back.
    with Hydra() as h:
        h.verify()
        h.run("MATCH (n:EngramSmoke) DETACH DELETE n")
        h.run(
            "CREATE (a:EngramSmoke {name:$a})-[:LINKS]->(b:EngramSmoke {name:$b})",
            a="hello",
            b="hydradb",
        )
        rows = h.run(
            "MATCH (a:EngramSmoke)-[:LINKS]->(b:EngramSmoke) "
            "RETURN a.name AS src, b.name AS dst"
        )
        print("round-trip rows:", rows)
        h.run("MATCH (n:EngramSmoke) DETACH DELETE n")
        print("OK")
