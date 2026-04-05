"""OntologyGraph — thin public facade over a pluggable backend.

Delegates core CRUD/query/persist to the selected backend.
Convenience methods (context_for, prune, stats enrichment) live here,
not in the backend protocol.

No event firing in v1.0. No second lock layer — backends own their locks.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Callable, Literal

from ontology.backends import create_backend
from ontology.config import KernelConfig
from ontology.protocols import OntologyBackend
from ontology.schema import Entity, EntityRef, Predicate, QueryResult, Triple

logger = logging.getLogger(__name__)

HookCallback = Callable[[list[Triple]], None]


class OntologyGraph:
    """Public API for the ontology kernel.

    Wraps a backend and adds convenience methods that don't belong
    in the core storage protocol.

    Supports post-mutation hooks via :meth:`register_hook`.  Callbacks
    receive the list of triples that were added or removed.
    """

    HOOK_TRIPLES_ADDED = "triples_added"
    HOOK_TRIPLES_REMOVED = "triples_removed"
    _VALID_HOOKS = frozenset({HOOK_TRIPLES_ADDED, HOOK_TRIPLES_REMOVED})

    def __init__(self, config: KernelConfig | None = None) -> None:
        self._config = config or KernelConfig()
        self._backend: OntologyBackend = create_backend(self._config)
        self._hooks: dict[str, list[HookCallback]] = defaultdict(list)

    @property
    def backend(self) -> OntologyBackend:
        """Direct access to the underlying backend (for enrichers, tests)."""
        return self._backend

    @property
    def config(self) -> KernelConfig:
        return self._config

    # ── hooks ─────────────────────────────────────────────────────────────

    def register_hook(self, event: str, callback: HookCallback) -> None:
        """Register a callback for a mutation event.

        Supported events: ``"triples_added"``, ``"triples_removed"``.
        Callbacks receive the list of affected triples.
        """
        if event not in self._VALID_HOOKS:
            raise ValueError(
                f"Unknown hook event {event!r}; "
                f"valid: {sorted(self._VALID_HOOKS)}"
            )
        self._hooks[event].append(callback)

    def _fire(self, event: str, triples: list[Triple]) -> None:
        for cb in self._hooks.get(event, []):
            try:
                cb(triples)
            except Exception:
                logger.warning("Hook %r callback failed", event, exc_info=True)

    # ── delegated core ops ───────────────────────────────────────────────

    def add_triple(self, triple: Triple) -> None:
        self._backend.add_triple(triple)
        self._fire(self.HOOK_TRIPLES_ADDED, [triple])

    def add_triples(self, triples: list[Triple]) -> None:
        self._backend.add_triples(triples)
        if triples:
            self._fire(self.HOOK_TRIPLES_ADDED, triples)

    def remove_triple(
        self, subject: EntityRef, predicate: Predicate, obj: EntityRef
    ) -> bool:
        existing = self._backend.query_triples(subject, predicate, obj)
        removed = self._backend.remove_triple(subject, predicate, obj)
        if removed and existing:
            self._fire(self.HOOK_TRIPLES_REMOVED, existing)
        return removed

    def remove_entity(self, ref: EntityRef) -> int:
        neighbors = self._backend.neighbors(ref, direction="both")
        count = self._backend.remove_entity(ref)
        if count > 0 and neighbors:
            self._fire(self.HOOK_TRIPLES_REMOVED, neighbors)
        return count

    def get_entity(self, ref: EntityRef) -> Entity | None:
        return self._backend.get_entity(ref)

    def query_triples(
        self,
        subject: EntityRef | None = None,
        predicate: Predicate | None = None,
        obj: EntityRef | None = None,
    ) -> list[Triple]:
        return self._backend.query_triples(subject, predicate, obj)

    def neighbors(
        self,
        ref: EntityRef,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[Triple]:
        return self._backend.neighbors(ref, direction)

    def persist(self) -> None:
        self._backend.persist()

    def load(self) -> None:
        self._backend.load()

    # ── convenience methods (facade-only, not in backend protocol) ───────

    def context_for(
        self,
        query: str,
        top_n: int = 15,
        *,
        max_hops: int = 1,
        recency_half_life: float = 0.0,
    ) -> str:
        """Return a formatted string of facts most relevant to *query*.

        Parameters
        ----------
        query : str
            Free-text query.  Tokens <= 3 chars are ignored.
        top_n : int
            Maximum facts returned.
        max_hops : int
            How many hops to walk from each seed entity (1–3).
        recency_half_life : float
            If > 0, score triples by ``decayed_confidence(half_life_hours=…)``
            instead of raw confidence.  0 (default) disables decay.
        """
        result = self.context_for_query(
            query,
            top_n=top_n,
            max_hops=max_hops,
            recency_half_life=recency_half_life,
        )
        lines: list[str] = []
        for t in result.triples:
            s = t.subject.qualified
            o = t.obj.qualified
            lines.append(f"{s} {t.predicate.value} {o}  [conf={t.confidence:.2f}]")
        return "\n".join(lines)

    def context_for_query(
        self,
        query: str,
        top_n: int = 15,
        *,
        max_hops: int = 1,
        recency_half_life: float = 0.0,
    ) -> QueryResult:
        """Structured retrieval — returns a :class:`QueryResult`."""
        tokens = {t.lower() for t in query.split() if len(t) > 3}
        if not tokens:
            return QueryResult()

        all_triples = self._backend.query_triples()
        entity_keys: set[str] = set()
        for t in all_triples:
            entity_keys.add(t.subject.qualified)
            entity_keys.add(t.obj.qualified)

        seeds = [
            k for k in entity_keys if any(tok in k.lower() for tok in tokens)
        ]
        if not seeds:
            return QueryResult()

        now = time.time()
        max_hops = max(1, min(max_hops, 3))

        collected: dict[tuple[str, str, str], Triple] = {}

        for seed_key in seeds[:8]:
            frontier = {seed_key}
            visited: set[str] = set()
            for _hop in range(max_hops):
                next_frontier: set[str] = set()
                for node_key in frontier:
                    if node_key in visited:
                        continue
                    visited.add(node_key)
                    ref = EntityRef.parse(node_key)
                    for t in self._backend.neighbors(ref, direction="both"):
                        triple_key = (
                            t.subject.qualified,
                            t.predicate.value,
                            t.obj.qualified,
                        )
                        if triple_key not in collected:
                            collected[triple_key] = t
                        other = (
                            t.obj.qualified
                            if t.subject.qualified == node_key
                            else t.subject.qualified
                        )
                        next_frontier.add(other)
                frontier = next_frontier - visited

        def _score(t: Triple) -> float:
            if recency_half_life > 0:
                return t.decayed_confidence(
                    half_life_hours=recency_half_life, as_of=now
                )
            return t.confidence

        ranked = sorted(collected.values(), key=_score, reverse=True)[:top_n]
        return QueryResult(triples=ranked)

    def prune(self, min_confidence: float = 0.3) -> int:
        """Remove low-confidence edges and orphan nodes. Returns edges removed."""
        all_triples = self._backend.query_triples()
        removed = 0
        for t in all_triples:
            if (
                t.confidence < min_confidence
                and self._backend.remove_triple(t.subject, t.predicate, t.obj)
            ):
                removed += 1
        return removed

    def stats(self) -> dict[str, Any]:
        """Graph statistics enriched with top entities by degree."""
        base = self._backend.stats()
        all_triples = self._backend.query_triples()
        degree: dict[str, int] = {}
        for t in all_triples:
            s = t.subject.qualified
            o = t.obj.qualified
            degree[s] = degree.get(s, 0) + 1
            degree[o] = degree.get(o, 0) + 1
        top = sorted(degree.items(), key=lambda x: -x[1])[:10]
        base["top_entities"] = top
        return base
