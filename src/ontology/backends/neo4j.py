"""Neo4j backend stub — wire when scaling to production clusters.

Implements the OntologyBackend protocol with NotImplementedError.
"""

from __future__ import annotations

from typing import Any, Literal

from ontology.schema import Entity, EntityRef, Predicate, Triple


class Neo4jBackend:
    """Placeholder for the Neo4j production backend."""

    def __init__(self, **kwargs: Any) -> None:
        raise NotImplementedError(
            "Neo4j backend is not yet implemented. "
            "Use 'networkx' or 'kuzu' backends for now."
        )

    def add_triple(self, triple: Triple) -> None:
        raise NotImplementedError

    def add_triples(self, triples: list[Triple]) -> None:
        raise NotImplementedError

    def remove_triple(
        self, subject: EntityRef, predicate: Predicate, obj: EntityRef
    ) -> bool:
        raise NotImplementedError

    def remove_entity(self, ref: EntityRef) -> int:
        raise NotImplementedError

    def get_entity(self, ref: EntityRef) -> Entity | None:
        raise NotImplementedError

    def query_triples(
        self,
        subject: EntityRef | None = None,
        predicate: Predicate | None = None,
        obj: EntityRef | None = None,
    ) -> list[Triple]:
        raise NotImplementedError

    def neighbors(
        self,
        ref: EntityRef,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[Triple]:
        raise NotImplementedError

    def stats(self) -> dict[str, Any]:
        raise NotImplementedError

    def persist(self) -> None:
        raise NotImplementedError

    def load(self) -> None:
        raise NotImplementedError
