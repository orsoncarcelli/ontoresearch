"""OntologyGraph — thin public facade over a pluggable backend.

Delegates core CRUD/query/persist to the selected backend.
Convenience methods (context_for, prune, stats enrichment) live here,
not in the backend protocol.

No event firing in v1.0. No second lock layer — backends own their locks.
"""

from __future__ import annotations

from typing import Any, Literal

from ontology.backends import create_backend
from ontology.config import KernelConfig
from ontology.protocols import OntologyBackend
from ontology.schema import Entity, EntityRef, Predicate, Triple


class OntologyGraph:
    """Public API for the ontology kernel.

    Wraps a backend and adds convenience methods that don't belong
    in the core storage protocol.
    """

    def __init__(self, config: KernelConfig | None = None) -> None:
        self._config = config or KernelConfig()
        self._backend: OntologyBackend = create_backend(self._config)

    @property
    def backend(self) -> OntologyBackend:
        """Direct access to the underlying backend (for enrichers, tests)."""
        return self._backend

    @property
    def config(self) -> KernelConfig:
        return self._config

    # ── delegated core ops ───────────────────────────────────────────────

    def add_triple(self, triple: Triple) -> None:
        self._backend.add_triple(triple)

    def add_triples(self, triples: list[Triple]) -> None:
        self._backend.add_triples(triples)

    def remove_triple(
        self, subject: EntityRef, predicate: Predicate, obj: EntityRef
    ) -> bool:
        return self._backend.remove_triple(subject, predicate, obj)

    def remove_entity(self, ref: EntityRef) -> int:
        return self._backend.remove_entity(ref)

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

    def context_for(self, query: str, top_n: int = 15) -> str:
        """Return a formatted string of facts most relevant to query.

        Token-overlap retrieval — matches query words against entity names.
        Ported from onto-market's OntologyGraph.context_for().
        """
        tokens = {t.lower() for t in query.split() if len(t) > 3}
        if not tokens:
            return ""

        all_triples = self._backend.query_triples()
        entity_keys: set[str] = set()
        for t in all_triples:
            entity_keys.add(t.subject.qualified)
            entity_keys.add(t.obj.qualified)

        seeds = [
            k for k in entity_keys if any(tok in k.lower() for tok in tokens)
        ]
        if not seeds:
            return ""

        facts: list[tuple[float, str]] = []
        for seed in seeds[:6]:
            seed_ref = EntityRef.parse(seed)
            for t in self._backend.neighbors(seed_ref, direction="both"):
                s = t.subject.qualified
                o = t.obj.qualified
                line = f"{s} {t.predicate.value} {o}  [conf={t.confidence:.2f}]"
                facts.append((t.confidence, line))

        seen: set[str] = set()
        lines: list[str] = []
        for _, fact in sorted(facts, key=lambda x: -x[0]):
            if fact not in seen:
                seen.add(fact)
                lines.append(fact)
            if len(lines) >= top_n:
                break
        return "\n".join(lines)

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
