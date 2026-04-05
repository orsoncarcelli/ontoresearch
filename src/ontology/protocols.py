"""Core protocol definitions — the kernel contract.

All interfaces use typing.Protocol — implementations satisfy them
structurally without importing base classes.

context_for, prune, and analytics are NOT in OntologyBackend.
They live in the facade (graph.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from ontology.schema import Entity, EntityRef, Predicate, Triple

if TYPE_CHECKING:
    from ontology.graph import OntologyGraph


@runtime_checkable
class OntologyBackend(Protocol):
    """Core graph storage operations: CRUD + query + persist.

    Every backend must implement this protocol. Backends own their
    own threading.RLock for mutation safety.
    """

    def add_triple(self, triple: Triple) -> None: ...

    def add_triples(self, triples: list[Triple]) -> None: ...

    def remove_triple(
        self, subject: EntityRef, predicate: Predicate, obj: EntityRef
    ) -> bool: ...

    def remove_entity(self, ref: EntityRef) -> int: ...

    def get_entity(self, ref: EntityRef) -> Entity | None: ...

    def query_triples(
        self,
        subject: EntityRef | None = None,
        predicate: Predicate | None = None,
        obj: EntityRef | None = None,
    ) -> list[Triple]: ...

    def neighbors(
        self,
        ref: EntityRef,
        direction: Literal["out", "in", "both"] = "both",
    ) -> list[Triple]: ...

    def stats(self) -> dict[str, Any]: ...

    def persist(self) -> None: ...

    def load(self) -> None: ...


@runtime_checkable
class EnricherProtocol(Protocol):
    """Triple enrichment interface.

    Enrichers receive a batch of triples and a backend reference,
    and return derived triples to be ingested.
    """

    @property
    def name(self) -> str: ...

    def enrich(
        self, triples: list[Triple], backend: OntologyBackend
    ) -> list[Triple]: ...


@runtime_checkable
class DomainPlugin(Protocol):
    """Domain plugin interface for automatic registration via entry points.

    Plugins provide a namespace, register themselves with the graph,
    and supply domain-specific enrichers.
    """

    @property
    def name(self) -> str: ...

    @property
    def namespace(self) -> str: ...

    def register(self, graph: OntologyGraph) -> None: ...

    def enrichers(self) -> list[EnricherProtocol]: ...
