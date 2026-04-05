"""Shared test fixtures for ontology kernel tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology.config import KernelConfig
from ontology.schema import EntityRef, Predicate, Triple


@pytest.fixture()
def tmp_path_factory_persist(tmp_path: Path) -> Path:
    """Return a temporary directory for backend persistence."""
    return tmp_path / "ontology_data"


@pytest.fixture()
def nx_config(tmp_path: Path) -> KernelConfig:
    """KernelConfig wired to a temporary NetworkX backend."""
    return KernelConfig(
        backend="networkx",
        persist_path=tmp_path / "ontology.json",
        default_namespace="test",
    )


def make_ref(name: str, ns: str = "test") -> EntityRef:
    """Shorthand for creating EntityRef in tests."""
    return EntityRef(namespace=ns, name=name)


def make_triple(
    subj: str = "alpha",
    pred: Predicate = Predicate.RELATED_TO,
    obj: str = "beta",
    ns: str = "test",
    confidence: float = 0.7,
    source: str = "test",
) -> Triple:
    """Shorthand for creating Triple in tests."""
    return Triple(
        subject=make_ref(subj, ns),
        predicate=pred,
        obj=make_ref(obj, ns),
        confidence=confidence,
        source=source,
    )
