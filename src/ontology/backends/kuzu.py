"""Kuzu embedded graph database backend.

Physical model: one relation type per core predicate.
Each Predicate enum member maps to its own Kuzu relationship table
(INFLUENCES, PREDICTS, CORRELATES_WITH, etc.) for optimal query performance.

Node table: Entity with qname as primary key.
Relation tables: one per predicate, all sharing the same column schema.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Literal

import kuzu

from ontology.schema import Entity, EntityRef, Predicate, Triple

logger = logging.getLogger(__name__)

_REL_TABLE_NAMES: dict[Predicate, str] = {
    Predicate.INFLUENCES: "INFLUENCES",
    Predicate.RELATED_TO: "RELATED_TO",
    Predicate.CONTRADICTS: "CONTRADICTS",
    Predicate.PREDICTS: "PREDICTS",
    Predicate.CAUSED_BY: "CAUSED_BY",
    Predicate.INVOLVES: "INVOLVES",
    Predicate.SUPPORTS: "SUPPORTS",
    Predicate.OPPOSES: "OPPOSES",
    Predicate.CORRELATES_WITH: "CORRELATES_WITH",
}

_REL_COLUMNS = "confidence DOUBLE, source STRING, ts DOUBLE, metadata STRING"


class KuzuBackend:
    """Kuzu-backed graph storage with discrete relation types."""

    def __init__(self, db_path: Path | str = "data/ontology_kuzu") -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None
        self._schema_ready = False
        self.load()

    def _ensure_db(self) -> kuzu.Connection:
        """Lazily initialize database and connection."""
        if self._conn is not None:
            return self._conn
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        if not self._schema_ready:
            self._create_schema()
        return self._conn

    @staticmethod
    def _exec(conn: kuzu.Connection, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a Cypher query and return the QueryResult.

        Wraps kuzu's execute() to narrow the union return type for mypy.
        """
        if params:
            return conn.execute(query, params)
        return conn.execute(query)

    def _create_schema(self) -> None:
        """Create node and relation tables if they don't exist."""
        conn = self._conn
        assert conn is not None

        with contextlib.suppress(RuntimeError):
            self._exec(
                conn,
                "CREATE NODE TABLE IF NOT EXISTS Entity("
                "qname STRING, namespace STRING, name STRING, "
                "sources STRING, first_seen DOUBLE, last_seen DOUBLE, "
                "properties STRING, PRIMARY KEY(qname))",
            )

        for rel_name in _REL_TABLE_NAMES.values():
            with contextlib.suppress(RuntimeError):
                self._exec(
                    conn,
                    f"CREATE REL TABLE IF NOT EXISTS {rel_name}("
                    f"FROM Entity TO Entity, {_REL_COLUMNS})",
                )

        self._schema_ready = True

    def add_triple(self, triple: Triple) -> None:
        with self._lock:
            self._upsert_triple(triple)

    def add_triples(self, triples: list[Triple]) -> None:
        with self._lock:
            for t in triples:
                self._upsert_triple(t)

    def remove_triple(
        self, subject: EntityRef, predicate: Predicate, obj: EntityRef
    ) -> bool:
        s_key = subject.qualified
        o_key = obj.qualified
        rel = _REL_TABLE_NAMES[predicate]
        with self._lock:
            conn = self._ensure_db()
            result = self._exec(
                conn,
                f"MATCH (a:Entity {{qname: $s}})-[r:{rel}]->(b:Entity {{qname: $o}}) "
                f"RETURN count(r)",
                {"s": s_key, "o": o_key},
            )
            count = 0
            if result.has_next():
                count = result.get_next()[0]
            if count == 0:
                return False
            self._exec(
                conn,
                f"MATCH (a:Entity {{qname: $s}})-[r:{rel}]->(b:Entity {{qname: $o}}) DELETE r",
                {"s": s_key, "o": o_key},
            )
            self._cleanup_orphans([s_key, o_key])
            return True

    def remove_entity(self, ref: EntityRef) -> int:
        key = ref.qualified
        with self._lock:
            conn = self._ensure_db()
            result = self._exec(
                conn,
                "MATCH (a:Entity {qname: $q}) RETURN count(a)",
                {"q": key},
            )
            if not result.has_next() or result.get_next()[0] == 0:
                return 0

            total_edges = 0
            for rel in _REL_TABLE_NAMES.values():
                for direction_query in [
                    f"MATCH (a:Entity {{qname: $q}})-[r:{rel}]->() DELETE r",
                    f"MATCH ()-[r:{rel}]->(a:Entity {{qname: $q}}) DELETE r",
                ]:
                    count_q = self._exec(
                        conn,
                        direction_query.replace("DELETE r", "RETURN count(r)"),
                        {"q": key},
                    )
                    if count_q.has_next():
                        total_edges += count_q.get_next()[0]
                    self._exec(conn, direction_query, {"q": key})

            self._exec(
                conn,
                "MATCH (a:Entity {qname: $q}) DELETE a",
                {"q": key},
            )
            return total_edges

    def get_entity(self, ref: EntityRef) -> Entity | None:
        key = ref.qualified
        conn = self._ensure_db()
        result = self._exec(
            conn,
            "MATCH (a:Entity {qname: $q}) "
            "RETURN a.namespace, a.name, a.sources, a.first_seen, a.last_seen, a.properties",
            {"q": key},
        )
        if not result.has_next():
            return None
        row = result.get_next()
        return Entity(
            ref=ref,
            sources=json.loads(row[2]) if row[2] else [],
            first_seen=float(row[3]) if row[3] else 0.0,
            last_seen=float(row[4]) if row[4] else 0.0,
            properties=json.loads(row[5]) if row[5] else {},
        )

    def query_triples(
        self,
        subject: EntityRef | None = None,
        predicate: Predicate | None = None,
        obj: EntityRef | None = None,
    ) -> list[Triple]:
        conn = self._ensure_db()
        results: list[Triple] = []

        preds_to_scan = [predicate] if predicate else list(Predicate)
        for pred in preds_to_scan:
            rel = _REL_TABLE_NAMES[pred]
            where_clauses: list[str] = []
            params: dict[str, Any] = {}

            if subject:
                where_clauses.append("a.qname = $s")
                params["s"] = subject.qualified
            if obj:
                where_clauses.append("b.qname = $o")
                params["o"] = obj.qualified

            where = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
            query = (
                f"MATCH (a:Entity)-[r:{rel}]->(b:Entity){where} "
                f"RETURN a.qname, b.qname, r.confidence, r.source, r.ts, r.metadata"
            )

            try:
                result = self._exec(conn, query, params)
            except RuntimeError:
                continue

            while result.has_next():
                row = result.get_next()
                results.append(self._row_to_triple(row, pred))

        return results

    def neighbors(
        self,
        ref: EntityRef,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[Triple]:
        key = ref.qualified
        conn = self._ensure_db()

        result_check = self._exec(
            conn, "MATCH (a:Entity {qname: $q}) RETURN count(a)", {"q": key}
        )
        if not result_check.has_next() or result_check.get_next()[0] == 0:
            return []

        results: list[Triple] = []
        for pred, rel in _REL_TABLE_NAMES.items():
            if direction in ("out", "both"):
                with contextlib.suppress(RuntimeError):
                    out = self._exec(
                        conn,
                        f"MATCH (a:Entity {{qname: $q}})-[r:{rel}]->(b:Entity) "
                        f"RETURN a.qname, b.qname, r.confidence, r.source, r.ts, r.metadata",
                        {"q": key},
                    )
                    while out.has_next():
                        results.append(self._row_to_triple(out.get_next(), pred))
            if direction in ("in", "both"):
                with contextlib.suppress(RuntimeError):
                    inp = self._exec(
                        conn,
                        f"MATCH (a:Entity)-[r:{rel}]->(b:Entity {{qname: $q}}) "
                        f"RETURN a.qname, b.qname, r.confidence, r.source, r.ts, r.metadata",
                        {"q": key},
                    )
                    while inp.has_next():
                        results.append(self._row_to_triple(inp.get_next(), pred))

        return results

    def stats(self) -> dict[str, Any]:
        conn = self._ensure_db()
        node_result = self._exec(conn, "MATCH (a:Entity) RETURN count(a)")
        nodes = node_result.get_next()[0] if node_result.has_next() else 0

        edges = 0
        for rel in _REL_TABLE_NAMES.values():
            with contextlib.suppress(RuntimeError):
                edge_result = self._exec(conn, f"MATCH ()-[r:{rel}]->() RETURN count(r)")
                if edge_result.has_next():
                    edges += edge_result.get_next()[0]

        return {"nodes": nodes, "edges": edges}

    def persist(self) -> None:
        """Kuzu writes are immediately durable — no-op."""

    def load(self) -> None:
        """Initialize the database connection and schema."""
        self._ensure_db()

    # ── internal helpers ─────────────────────────────────────────────────

    def _upsert_triple(self, triple: Triple) -> None:
        """Upsert entity nodes and relation edge — must be called under _lock."""
        conn = self._ensure_db()
        s_key = triple.subject.qualified
        o_key = triple.obj.qualified

        for key, ref in ((s_key, triple.subject), (o_key, triple.obj)):
            existing = self._exec(
                conn,
                "MATCH (a:Entity {qname: $q}) RETURN a.sources, a.last_seen",
                {"q": key},
            )
            if existing.has_next():
                row = existing.get_next()
                sources: list[str] = json.loads(row[0]) if row[0] else []
                if triple.source and triple.source not in sources:
                    sources.append(triple.source)
                self._exec(
                    conn,
                    "MATCH (a:Entity {qname: $q}) "
                    "SET a.sources = $src, a.last_seen = $ls",
                    {"q": key, "src": json.dumps(sources), "ls": triple.timestamp},
                )
            else:
                init_sources = [triple.source] if triple.source else []
                self._exec(
                    conn,
                    "CREATE (a:Entity {"
                    "qname: $q, namespace: $ns, name: $n, "
                    "sources: $src, first_seen: $fs, last_seen: $ls, "
                    "properties: $props})",
                    {
                        "q": key,
                        "ns": ref.namespace,
                        "n": ref.name,
                        "src": json.dumps(init_sources),
                        "fs": triple.timestamp,
                        "ls": triple.timestamp,
                        "props": "{}",
                    },
                )

        rel = _REL_TABLE_NAMES[triple.predicate]
        existing_rel = self._exec(
            conn,
            f"MATCH (a:Entity {{qname: $s}})-[r:{rel}]->(b:Entity {{qname: $o}}) "
            f"RETURN r.confidence",
            {"s": s_key, "o": o_key},
        )
        if existing_rel.has_next():
            old_conf = existing_rel.get_next()[0]
            new_conf = max(old_conf, triple.confidence)
            self._exec(
                conn,
                f"MATCH (a:Entity {{qname: $s}})-[r:{rel}]->(b:Entity {{qname: $o}}) "
                f"SET r.confidence = $c, r.metadata = $m",
                {
                    "s": s_key,
                    "o": o_key,
                    "c": new_conf,
                    "m": json.dumps(triple.metadata),
                },
            )
        else:
            self._exec(
                conn,
                f"MATCH (a:Entity {{qname: $s}}), (b:Entity {{qname: $o}}) "
                f"CREATE (a)-[:{rel} {{confidence: $c, source: $src, ts: $t, metadata: $m}}]->(b)",
                {
                    "s": s_key,
                    "o": o_key,
                    "c": triple.confidence,
                    "src": triple.source,
                    "t": triple.timestamp,
                    "m": json.dumps(triple.metadata),
                },
            )

    def _cleanup_orphans(self, candidates: list[str]) -> None:
        """Remove entity nodes with no edges remaining."""
        conn = self._ensure_db()
        for key in candidates:
            total = 0
            for rel in _REL_TABLE_NAMES.values():
                for q in [
                    f"MATCH (a:Entity {{qname: $q}})-[r:{rel}]->() RETURN count(r)",
                    f"MATCH ()-[r:{rel}]->(a:Entity {{qname: $q}}) RETURN count(r)",
                ]:
                    result = self._exec(conn, q, {"q": key})
                    if result.has_next():
                        total += result.get_next()[0]
            if total == 0:
                self._exec(conn, "MATCH (a:Entity {qname: $q}) DELETE a", {"q": key})

    @staticmethod
    def _row_to_triple(row: Any, pred: Predicate) -> Triple:
        """Convert a Kuzu result row to a schema Triple."""
        return Triple(
            subject=EntityRef.parse(row[0]),
            predicate=pred,
            obj=EntityRef.parse(row[1]),
            confidence=float(row[2]) if row[2] is not None else 0.7,
            source=str(row[3]) if row[3] else "",
            timestamp=float(row[4]) if row[4] is not None else 0.0,
            metadata=json.loads(row[5]) if row[5] else {},
        )
