"""Pydantic v2 models for the ontology kernel.

Canonical types: EntityRef, Triple, Entity, Predicate, QueryResult.

EntityRef is the structured internal form — (namespace, name) pair.
The string form "ns:name" only appears at IO boundaries.
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class Predicate(StrEnum):
    """Closed predicate vocabulary.

    Unknown values raise ValidationError — no silent coercion.
    """

    INFLUENCES = "influences"
    RELATED_TO = "related_to"
    CONTRADICTS = "contradicts"
    PREDICTS = "predicts"
    CAUSED_BY = "caused_by"
    INVOLVES = "involves"
    SUPPORTS = "supports"
    OPPOSES = "opposes"
    CORRELATES_WITH = "correlates_with"


class EntityRef(BaseModel, frozen=True):
    """Namespaced entity reference — the canonical internal form.

    Use EntityRef.parse() at IO boundaries to convert "ns:name" strings.
    Use .qualified property to serialize back to "ns:name".
    """

    namespace: str = Field(min_length=1)
    name: str = Field(min_length=1)

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        object.__setattr__(self, "namespace", self.namespace.lower().strip())
        object.__setattr__(self, "name", self.name.lower().strip())
        return self

    @property
    def qualified(self) -> str:
        """Serialize to 'namespace:name' string form."""
        return f"{self.namespace}:{self.name}"

    @classmethod
    def parse(cls, s: str, default_ns: str | None = None) -> EntityRef:
        """Parse 'ns:name' string or apply default namespace.

        If the string contains ':', split on the first ':'.
        If no ':', requires default_ns or raises ValueError.
        """
        s = s.strip()
        if ":" in s:
            ns, _, name = s.partition(":")
            ns = ns.strip()
            name = name.strip()
            if not ns or not name:
                raise ValueError(f"Invalid entity ref: {s!r}")
            return cls(namespace=ns, name=name)
        if default_ns:
            return cls(namespace=default_ns, name=s)
        raise ValueError(
            f"Entity ref {s!r} has no namespace and no default_ns provided"
        )

    def __str__(self) -> str:
        return self.qualified

    def __repr__(self) -> str:
        return f"EntityRef({self.qualified!r})"


class Triple(BaseModel, frozen=True):
    """A typed, validated triple — the fundamental unit of the knowledge graph."""

    subject: EntityRef
    predicate: Predicate
    obj: EntityRef
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    source: str = ""
    timestamp: float = Field(default_factory=time.time)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Entity(BaseModel):
    """Node data model — accumulated metadata for an entity in the graph."""

    ref: EntityRef
    sources: list[str] = Field(default_factory=list)
    first_seen: float = Field(default_factory=time.time)
    last_seen: float = Field(default_factory=time.time)
    properties: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    """Standardized result container for graph queries."""

    triples: list[Triple] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
