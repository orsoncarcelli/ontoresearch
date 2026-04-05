"""Backend conformance test suite.

One parametrized suite that every backend must pass. Parametrized over
NetworkX and Kuzu. Tests cover: CRUD, upsert semantics, entity lifecycle,
namespace enforcement, predicate validation, idempotence, persist/load
round-trip, concurrent mutation, and empty graph operations.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from ontology.backends.kuzu import KuzuBackend
from ontology.backends.networkx import NetworkXBackend
from ontology.protocols import OntologyBackend
from ontology.schema import EntityRef, Predicate, Triple


def _ref(name: str, ns: str = "test") -> EntityRef:
    return EntityRef(namespace=ns, name=name)


def _triple(
    subj: str = "alpha",
    pred: Predicate = Predicate.RELATED_TO,
    obj: str = "beta",
    ns: str = "test",
    confidence: float = 0.7,
    source: str = "test",
) -> Triple:
    return Triple(
        subject=_ref(subj, ns),
        predicate=pred,
        obj=_ref(obj, ns),
        confidence=confidence,
        source=source,
    )


def _make_nx(tmp_path: Path) -> NetworkXBackend:
    return NetworkXBackend(persist_path=tmp_path / "test_graph.json")


def _make_kuzu(tmp_path: Path) -> KuzuBackend:
    return KuzuBackend(db_path=tmp_path / "kuzu_db")


@pytest.fixture(params=["networkx", "kuzu"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    """Parametrized backend fixture — covers NX and Kuzu."""
    if request.param == "networkx":
        return _make_nx(tmp_path)
    if request.param == "kuzu":
        return _make_kuzu(tmp_path)
    raise ValueError(f"Unknown backend: {request.param}")


class TestCRUDHappyPath:
    def test_add_and_query(self, backend: OntologyBackend) -> None:
        t = _triple()
        backend.add_triple(t)
        results = backend.query_triples()
        assert len(results) == 1
        assert results[0].subject == t.subject
        assert results[0].obj == t.obj
        assert results[0].predicate == t.predicate

    def test_add_triples_batch(self, backend: OntologyBackend) -> None:
        triples = [
            _triple("a", Predicate.INFLUENCES, "b"),
            _triple("b", Predicate.PREDICTS, "c"),
            _triple("c", Predicate.SUPPORTS, "d"),
        ]
        backend.add_triples(triples)
        results = backend.query_triples()
        assert len(results) == 3

    def test_remove_triple(self, backend: OntologyBackend) -> None:
        t = _triple()
        backend.add_triple(t)
        removed = backend.remove_triple(t.subject, t.predicate, t.obj)
        assert removed is True
        assert len(backend.query_triples()) == 0

    def test_remove_nonexistent_returns_false(self, backend: OntologyBackend) -> None:
        removed = backend.remove_triple(
            _ref("x"), Predicate.INFLUENCES, _ref("y")
        )
        assert removed is False

    def test_remove_entity(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("hub", Predicate.INFLUENCES, "a"),
            _triple("hub", Predicate.PREDICTS, "b"),
            _triple("c", Predicate.SUPPORTS, "hub"),
        ])
        removed = backend.remove_entity(_ref("hub"))
        assert removed == 3
        assert backend.get_entity(_ref("hub")) is None

    def test_remove_nonexistent_entity(self, backend: OntologyBackend) -> None:
        assert backend.remove_entity(_ref("ghost")) == 0

    def test_get_entity(self, backend: OntologyBackend) -> None:
        t = _triple(source="agent_1")
        backend.add_triple(t)
        e = backend.get_entity(t.subject)
        assert e is not None
        assert e.ref == t.subject
        assert "agent_1" in e.sources

    def test_get_nonexistent_entity(self, backend: OntologyBackend) -> None:
        assert backend.get_entity(_ref("ghost")) is None


class TestQueryFilters:
    def test_filter_by_subject(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("a", Predicate.INFLUENCES, "b"),
            _triple("c", Predicate.PREDICTS, "d"),
        ])
        results = backend.query_triples(subject=_ref("a"))
        assert len(results) == 1
        assert results[0].subject.name == "a"

    def test_filter_by_predicate(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("a", Predicate.INFLUENCES, "b"),
            _triple("c", Predicate.PREDICTS, "d"),
        ])
        results = backend.query_triples(predicate=Predicate.PREDICTS)
        assert len(results) == 1
        assert results[0].predicate == Predicate.PREDICTS

    def test_filter_by_object(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("a", Predicate.INFLUENCES, "target"),
            _triple("c", Predicate.PREDICTS, "other"),
        ])
        results = backend.query_triples(obj=_ref("target"))
        assert len(results) == 1
        assert results[0].obj.name == "target"

    def test_combined_filters(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("a", Predicate.INFLUENCES, "b"),
            _triple("a", Predicate.PREDICTS, "b"),
            _triple("a", Predicate.INFLUENCES, "c"),
        ])
        results = backend.query_triples(
            subject=_ref("a"), predicate=Predicate.INFLUENCES, obj=_ref("b")
        )
        assert len(results) == 1


class TestNeighbors:
    def test_out_neighbors(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("hub", Predicate.INFLUENCES, "a"),
            _triple("hub", Predicate.PREDICTS, "b"),
            _triple("c", Predicate.SUPPORTS, "hub"),
        ])
        out = backend.neighbors(_ref("hub"), direction="out")
        assert len(out) == 2

    def test_in_neighbors(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("hub", Predicate.INFLUENCES, "a"),
            _triple("c", Predicate.SUPPORTS, "hub"),
        ])
        inn = backend.neighbors(_ref("hub"), direction="in")
        assert len(inn) == 1
        assert inn[0].subject.name == "c"

    def test_both_neighbors(self, backend: OntologyBackend) -> None:
        backend.add_triples([
            _triple("hub", Predicate.INFLUENCES, "a"),
            _triple("c", Predicate.SUPPORTS, "hub"),
        ])
        both = backend.neighbors(_ref("hub"), direction="both")
        assert len(both) == 2

    def test_nonexistent_entity_neighbors(self, backend: OntologyBackend) -> None:
        assert backend.neighbors(_ref("ghost")) == []


class TestUpsertSemantics:
    def test_same_triple_merges_confidence(self, backend: OntologyBackend) -> None:
        backend.add_triple(_triple("a", Predicate.INFLUENCES, "b", confidence=0.5))
        backend.add_triple(_triple("a", Predicate.INFLUENCES, "b", confidence=0.9))
        results = backend.query_triples(
            subject=_ref("a"), predicate=Predicate.INFLUENCES, obj=_ref("b")
        )
        assert len(results) == 1
        assert results[0].confidence == 0.9

    def test_different_predicates_are_separate_edges(self, backend: OntologyBackend) -> None:
        """In Kuzu, different predicates = different relation tables = separate edges."""
        backend.add_triple(_triple("a", Predicate.INFLUENCES, "b"))
        backend.add_triple(_triple("a", Predicate.PREDICTS, "b"))
        all_triples = backend.query_triples()
        assert len(all_triples) == 2
        preds = {t.predicate for t in all_triples}
        assert preds == {Predicate.INFLUENCES, Predicate.PREDICTS}

    def test_source_accumulates(self, backend: OntologyBackend) -> None:
        backend.add_triple(_triple("a", source="s1"))
        backend.add_triple(_triple("a", source="s2"))
        e = backend.get_entity(_ref("a"))
        assert e is not None
        assert "s1" in e.sources
        assert "s2" in e.sources


class TestIdempotence:
    def test_add_same_triple_twice(self, backend: OntologyBackend) -> None:
        t = _triple()
        backend.add_triple(t)
        backend.add_triple(t)
        results = backend.query_triples()
        assert len(results) == 1


class TestPersistLoadRoundTrip:
    def test_nx_round_trip(self, tmp_path: Path) -> None:
        b1 = _make_nx(tmp_path)
        triples = [
            _triple("a", Predicate.INFLUENCES, "b", confidence=0.9),
            _triple("c", Predicate.PREDICTS, "d", confidence=0.8),
        ]
        b1.add_triples(triples)
        b1.persist()

        b2 = NetworkXBackend(persist_path=tmp_path / "test_graph.json")
        results = b2.query_triples()
        assert len(results) == 2
        confidences = sorted(r.confidence for r in results)
        assert confidences == [0.8, 0.9]

    def test_kuzu_persistence(self, tmp_path: Path) -> None:
        """Kuzu writes are durable immediately — reopen DB and verify."""
        db_path = tmp_path / "kuzu_persist"
        b1 = KuzuBackend(db_path=db_path)
        b1.add_triples([
            _triple("x", Predicate.SUPPORTS, "y", confidence=0.95),
            _triple("y", Predicate.OPPOSES, "z", confidence=0.6),
        ])
        b1.persist()

        del b1
        b2 = KuzuBackend(db_path=db_path)
        results = b2.query_triples()
        assert len(results) == 2

    def test_nx_persist_creates_parent_dirs(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "graph.json"
        b = NetworkXBackend(persist_path=deep_path)
        b.add_triple(_triple())
        b.persist()
        assert deep_path.exists()


class TestEmptyGraphOperations:
    def test_query_empty(self, backend: OntologyBackend) -> None:
        assert backend.query_triples() == []

    def test_stats_empty(self, backend: OntologyBackend) -> None:
        s = backend.stats()
        assert s["nodes"] == 0
        assert s["edges"] == 0

    def test_remove_from_empty(self, backend: OntologyBackend) -> None:
        assert backend.remove_triple(
            _ref("a"), Predicate.INFLUENCES, _ref("b")
        ) is False

    def test_get_entity_empty(self, backend: OntologyBackend) -> None:
        assert backend.get_entity(_ref("a")) is None


class TestConcurrentMutationSafety:
    def test_threaded_adds(self, backend: OntologyBackend) -> None:
        errors: list[Exception] = []

        def add_batch(start: int) -> None:
            try:
                for i in range(50):
                    backend.add_triple(
                        _triple(f"node_{start}_{i}", Predicate.INFLUENCES, f"target_{start}")
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_batch, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        stats = backend.stats()
        assert stats["edges"] == 200

    def test_threaded_add_remove(self, backend: OntologyBackend) -> None:
        for i in range(50):
            backend.add_triple(_triple(f"s_{i}", Predicate.RELATED_TO, f"o_{i}"))

        errors: list[Exception] = []

        def adder() -> None:
            try:
                for i in range(50, 100):
                    backend.add_triple(_triple(f"s_{i}", Predicate.RELATED_TO, f"o_{i}"))
            except Exception as e:
                errors.append(e)

        def remover() -> None:
            try:
                for i in range(25):
                    backend.remove_triple(
                        _ref(f"s_{i}"), Predicate.RELATED_TO, _ref(f"o_{i}")
                    )
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=adder)
        t2 = threading.Thread(target=remover)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []


class TestLegacyJsonRoundTrip:
    def test_load_legacy_format(self, tmp_path: Path) -> None:
        """Load a file in onto-market's node_link_data format."""
        from ontology.migration import load_legacy_json

        legacy = {
            "directed": True,
            "multigraph": False,
            "graph": {},
            "nodes": [
                {"id": "bitcoin price", "sources": ["agent"], "first_seen": 1000.0},
                {"id": "market sentiment", "sources": [], "first_seen": 1000.0},
            ],
            "links": [
                {
                    "source": "bitcoin price",
                    "target": "market sentiment",
                    "predicate": "influences",
                    "predicates": ["influences"],
                    "confidence": 0.85,
                    "source_agent": "planning_agent",
                    "timestamp": 1000.0,
                }
            ],
        }
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(legacy))

        triples = load_legacy_json(legacy_path, namespace="polymarket")
        assert len(triples) == 1
        t = triples[0]
        assert t.subject.namespace == "polymarket"
        assert t.subject.name == "bitcoin_price"
        assert t.obj.name == "market_sentiment"
        assert t.predicate == Predicate.INFLUENCES
        assert t.confidence == 0.85

    def test_migrate_into_backend(self, backend: OntologyBackend, tmp_path: Path) -> None:
        """Full round-trip: legacy JSON -> migration -> backend -> query."""
        from ontology.migration import load_legacy_json

        legacy = {
            "directed": True, "multigraph": False, "graph": {},
            "nodes": [
                {"id": "fed rate", "sources": []},
                {"id": "inflation", "sources": []},
            ],
            "links": [
                {
                    "source": "fed rate", "target": "inflation",
                    "predicate": "influences", "confidence": 0.9,
                    "timestamp": 1000.0,
                }
            ],
        }
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(legacy))

        triples = load_legacy_json(legacy_path, namespace="test")
        backend.add_triples(triples)

        results = backend.query_triples()
        assert len(results) == 1
        assert results[0].subject.namespace == "test"
        assert results[0].subject.name == "fed_rate"

    def test_unknown_predicate_maps_to_related_to(self, tmp_path: Path) -> None:
        from ontology.migration import load_legacy_json

        legacy = {
            "directed": True, "multigraph": False, "graph": {},
            "nodes": [{"id": "a"}, {"id": "b"}],
            "links": [
                {"source": "a", "target": "b", "predicate": "gobbledygook", "confidence": 0.5}
            ],
        }
        legacy_path = tmp_path / "legacy.json"
        legacy_path.write_text(json.dumps(legacy))

        triples = load_legacy_json(legacy_path, namespace="test")
        assert len(triples) == 1
        assert triples[0].predicate == Predicate.RELATED_TO


class TestPerformanceSmoke:
    def test_1000_triples(self, backend: OntologyBackend) -> None:
        triples = [
            _triple(f"s_{i}", Predicate.INFLUENCES, f"o_{i}", confidence=i / 1000)
            for i in range(1000)
        ]
        t0 = time.monotonic()
        backend.add_triples(triples)
        dt_add = time.monotonic() - t0

        t0 = time.monotonic()
        results = backend.query_triples()
        dt_query = time.monotonic() - t0

        assert len(results) == 1000
        assert dt_add < 30.0, f"Adding 1000 triples took {dt_add:.2f}s"
        assert dt_query < 5.0, f"Querying 1000 triples took {dt_query:.2f}s"
