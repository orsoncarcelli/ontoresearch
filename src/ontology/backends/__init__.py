"""Backend selection factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ontology.config import KernelConfig
    from ontology.protocols import OntologyBackend


def create_backend(config: KernelConfig) -> OntologyBackend:
    """Instantiate the backend specified by config."""
    if config.backend == "networkx":
        from ontology.backends.networkx import NetworkXBackend

        return NetworkXBackend(persist_path=config.persist_path)

    if config.backend == "kuzu":
        try:
            from ontology.backends.kuzu import KuzuBackend
        except ImportError as exc:
            raise ImportError(
                "Kuzu backend requires the 'kuzu' extra: pip install ontology[kuzu]"
            ) from exc
        return KuzuBackend(db_path=config.persist_path)

    if config.backend == "neo4j":
        from ontology.backends.neo4j import Neo4jBackend

        return Neo4jBackend()

    raise ValueError(f"Unknown backend: {config.backend!r}")
