"""NetworkX reference backend.

Uses MultiDiGraph to support multiple predicates per (subject, object) pair,
matching the Kuzu physical model where each Predicate is a discrete relation table.

Thread-safe via backend-owned RLock on all mutations.
Persistence via atomic JSON (temp file + rename).
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Literal

import networkx as nx

from ontokernel.schema import Entity, EntityRef, Predicate, Triple

logger = logging.getLogger(__name__)


class NetworkXBackend:
    """In-memory graph backed by NetworkX MultiDiGraph with JSON persistence."""

    def __init__(self, persist_path: Path | str = "data/ontology.json") -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._persist_path = Path(persist_path)
        self._lock = threading.RLock()
        self.load()

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
        edge_key = predicate.value
        with self._lock:
            if not self._g.has_edge(s_key, o_key, key=edge_key):
                return False
            self._g.remove_edge(s_key, o_key, key=edge_key)
            self._cleanup_orphans([s_key, o_key])
            return True

    def remove_entity(self, ref: EntityRef) -> int:
        key = ref.qualified
        with self._lock:
            if key not in self._g:
                return 0
            edge_count = self._g.degree(key)
            self._g.remove_node(key)
            return int(edge_count)

    def get_entity(self, ref: EntityRef) -> Entity | None:
        key = ref.qualified
        if key not in self._g:
            return None
        data = dict(self._g.nodes[key])
        return Entity(
            ref=ref,
            sources=data.get("sources", []),
            first_seen=data.get("first_seen", 0.0),
            last_seen=data.get("last_seen", 0.0),
            properties={
                k: v
                for k, v in data.items()
                if k not in ("sources", "first_seen", "last_seen", "namespace", "name")
            },
        )

    def query_triples(
        self,
        subject: EntityRef | None = None,
        predicate: Predicate | None = None,
        obj: EntityRef | None = None,
        *,
        before_timestamp: float | None = None,
        exclude_sources: frozenset[str] | None = None,
    ) -> list[Triple]:
        results: list[Triple] = []
        s_key = subject.qualified if subject else None
        o_key = obj.qualified if obj else None
        pred_val = predicate.value if predicate else None

        for u, v, key, data in self._g.edges(data=True, keys=True):
            if s_key and u != s_key:
                continue
            if o_key and v != o_key:
                continue
            if pred_val and key != pred_val:
                continue
            if before_timestamp is not None and float(data.get("timestamp", 0.0)) > before_timestamp:
                continue
            if exclude_sources is not None and str(data.get("source", "")) in exclude_sources:
                continue
            results.append(self._edge_to_triple(u, v, key, data))
        return results

    def neighbors(
        self,
        ref: EntityRef,
        direction: Literal["out", "in", "both"] = "both",
        *,
        before_timestamp: float | None = None,
        exclude_sources: frozenset[str] | None = None,
    ) -> list[Triple]:
        key = ref.qualified
        if key not in self._g:
            return []
        results: list[Triple] = []
        if direction in ("out", "both"):
            for _, tgt, ekey, data in self._g.out_edges(key, data=True, keys=True):
                if before_timestamp is not None and float(data.get("timestamp", 0.0)) > before_timestamp:
                    continue
                if exclude_sources is not None and str(data.get("source", "")) in exclude_sources:
                    continue
                results.append(self._edge_to_triple(key, tgt, ekey, data))
        if direction in ("in", "both"):
            for src, _, ekey, data in self._g.in_edges(key, data=True, keys=True):
                if before_timestamp is not None and float(data.get("timestamp", 0.0)) > before_timestamp:
                    continue
                if exclude_sources is not None and str(data.get("source", "")) in exclude_sources:
                    continue
                results.append(self._edge_to_triple(src, key, ekey, data))
        return results

    def stats(self) -> dict[str, Any]:
        return {
            "nodes": self._g.number_of_nodes(),
            "edges": self._g.number_of_edges(),
        }

    def persist(self) -> None:
        with self._lock:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = nx.node_link_data(self._g, edges="links")
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, default=str), encoding="utf-8")
            tmp.replace(self._persist_path)

    def load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._g = nx.node_link_graph(
                raw, directed=True, multigraph=True, edges="links"
            )
        except Exception:
            logger.warning(
                "Failed to load %s — starting with empty graph",
                self._persist_path,
                exc_info=True,
            )
            self._g = nx.MultiDiGraph()

    # ── internal helpers ─────────────────────────────────────────────────

    def _upsert_triple(self, triple: Triple) -> None:
        """Upsert nodes and edge. Edge key = predicate value."""
        s_key = triple.subject.qualified
        o_key = triple.obj.qualified
        edge_key = triple.predicate.value
        now = triple.timestamp

        for key, ref in ((s_key, triple.subject), (o_key, triple.obj)):
            if key not in self._g:
                self._g.add_node(
                    key,
                    namespace=ref.namespace,
                    name=ref.name,
                    sources=[],
                    first_seen=now,
                    last_seen=now,
                )
            node = self._g.nodes[key]
            sources: list[str] = node.get("sources", [])
            if triple.source and triple.source not in sources:
                sources.append(triple.source)
            node["sources"] = sources
            node["last_seen"] = now

        if self._g.has_edge(s_key, o_key, key=edge_key):
            edge = self._g[s_key][o_key][edge_key]
            edge["confidence"] = max(edge["confidence"], triple.confidence)
            edge["metadata"] = {
                **edge.get("metadata", {}),
                **triple.metadata,
            }
        else:
            self._g.add_edge(
                s_key,
                o_key,
                key=edge_key,
                confidence=triple.confidence,
                source=triple.source,
                timestamp=triple.timestamp,
                metadata=dict(triple.metadata),
            )

    def _cleanup_orphans(self, candidates: list[str]) -> None:
        for key in candidates:
            if key in self._g and self._g.degree(key) == 0:
                self._g.remove_node(key)

    def _edge_to_triple(
        self, s_key: str, o_key: str, edge_key: str, data: dict[str, Any]
    ) -> Triple:
        s_ref = EntityRef.parse(s_key)
        o_ref = EntityRef.parse(o_key)
        try:
            pred = Predicate(edge_key)
        except ValueError:
            pred = Predicate.RELATED_TO
        return Triple(
            subject=s_ref,
            predicate=pred,
            obj=o_ref,
            confidence=float(data.get("confidence", 0.7)),
            source=str(data.get("source", "")),
            timestamp=float(data.get("timestamp", 0.0)),
            metadata=data.get("metadata", {}),
        )
