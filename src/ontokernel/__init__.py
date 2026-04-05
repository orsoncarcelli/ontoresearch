"""Ontology kernel — domain-agnostic typed knowledge graph engine."""

from ontokernel.graph import HookCallback, OntologyGraph
from ontokernel.registry import PluginRegistry, discover_plugins
from ontokernel.schema import (
    Entity,
    EntityRef,
    GraphSnapshot,
    Predicate,
    QueryResult,
    Triple,
)

__all__ = [
    "Entity",
    "EntityRef",
    "GraphSnapshot",
    "HookCallback",
    "OntologyGraph",
    "PluginRegistry",
    "Predicate",
    "QueryResult",
    "Triple",
    "discover_plugins",
]
