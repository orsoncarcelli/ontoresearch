"""Tests for ontology.graph — facade convenience methods."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ontology.config import KernelConfig
from ontology.graph import OntologyGraph
from ontology.schema import EntityRef, Predicate, QueryResult, Triple


@pytest.fixture()
def graph(tmp_path: Path) -> OntologyGraph:
    cfg = KernelConfig(
        backend="networkx",
        persist_path=tmp_path / "test.json",
        default_namespace="test",
    )
    return OntologyGraph(config=cfg)


def _ref(name: str, ns: str = "test") -> EntityRef:
    return EntityRef(namespace=ns, name=name)


def _triple(
    subj: str = "a",
    pred: Predicate = Predicate.RELATED_TO,
    obj: str = "b",
    confidence: float = 0.7,
) -> Triple:
    return Triple(
        subject=_ref(subj),
        predicate=pred,
        obj=_ref(obj),
        confidence=confidence,
        source="test",
    )


class TestFacadeDelegation:
    def test_add_and_query(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple())
        results = graph.query_triples()
        assert len(results) == 1

    def test_add_triples(self, graph: OntologyGraph) -> None:
        graph.add_triples([_triple("a", obj="b"), _triple("c", obj="d")])
        assert len(graph.query_triples()) == 2

    def test_remove_triple(self, graph: OntologyGraph) -> None:
        t = _triple()
        graph.add_triple(t)
        assert graph.remove_triple(t.subject, t.predicate, t.obj) is True
        assert len(graph.query_triples()) == 0

    def test_remove_entity(self, graph: OntologyGraph) -> None:
        graph.add_triples([_triple("hub", obj="a"), _triple("hub", obj="b")])
        removed = graph.remove_entity(_ref("hub"))
        assert removed == 2

    def test_get_entity(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple())
        e = graph.get_entity(_ref("a"))
        assert e is not None
        assert e.ref.name == "a"

    def test_neighbors(self, graph: OntologyGraph) -> None:
        graph.add_triples([_triple("hub", obj="x"), _triple("y", obj="hub")])
        both = graph.neighbors(_ref("hub"), direction="both")
        assert len(both) == 2

    def test_persist_and_load(self, graph: OntologyGraph, tmp_path: Path) -> None:
        graph.add_triple(_triple())
        graph.persist()

        graph2 = OntologyGraph(
            config=KernelConfig(
                backend="networkx",
                persist_path=tmp_path / "test.json",
            )
        )
        assert len(graph2.query_triples()) == 1


class TestContextFor:
    def test_basic_retrieval(self, graph: OntologyGraph) -> None:
        graph.add_triples([
            _triple("bitcoin_price", Predicate.INFLUENCES, "market_sentiment"),
            _triple("fed_rate", Predicate.PREDICTS, "inflation"),
        ])
        ctx = graph.context_for("bitcoin market")
        assert "bitcoin" in ctx.lower()
        assert "market" in ctx.lower()

    def test_empty_query(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple())
        assert graph.context_for("") == ""

    def test_short_tokens_ignored(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple())
        assert graph.context_for("a b c") == ""

    def test_no_match(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple("alpha", obj="beta"))
        assert graph.context_for("completely unrelated query") == ""

    def test_top_n_limit(self, graph: OntologyGraph) -> None:
        for i in range(20):
            graph.add_triple(
                _triple(f"entity_{i}", Predicate.INFLUENCES, "target_entity")
            )
        ctx = graph.context_for("target_entity", top_n=5)
        lines = [line for line in ctx.strip().split("\n") if line.strip()]
        assert len(lines) <= 5

    def test_multi_hop_reaches_distant_nodes(self, graph: OntologyGraph) -> None:
        graph.add_triples([
            _triple("bitcoin_price", Predicate.INFLUENCES, "market_sentiment"),
            _triple("market_sentiment", Predicate.PREDICTS, "trading_volume"),
        ])
        ctx_1hop = graph.context_for("bitcoin", max_hops=1)
        ctx_2hop = graph.context_for("bitcoin", max_hops=2)
        assert "trading_volume" not in ctx_1hop
        assert "trading_volume" in ctx_2hop

    def test_recency_half_life_favors_recent(self, graph: OntologyGraph) -> None:
        now = time.time()
        old_triple = Triple(
            subject=_ref("bitcoin_price"), predicate=Predicate.INFLUENCES,
            obj=_ref("market"), confidence=0.9, source="test",
            timestamp=now - 30 * 24 * 3600,
        )
        new_triple = Triple(
            subject=_ref("bitcoin_price"), predicate=Predicate.PREDICTS,
            obj=_ref("sentiment"), confidence=0.5, source="test",
            timestamp=now,
        )
        graph.add_triples([old_triple, new_triple])
        ctx = graph.context_for("bitcoin_price", top_n=1, recency_half_life=24.0)
        assert "sentiment" in ctx

    def test_context_for_query_returns_query_result(self, graph: OntologyGraph) -> None:
        graph.add_triple(_triple("bitcoin_price", Predicate.INFLUENCES, "market_sentiment"))
        result = graph.context_for_query("bitcoin market")
        assert isinstance(result, QueryResult)
        assert len(result.triples) >= 1

    def test_context_for_query_empty(self, graph: OntologyGraph) -> None:
        result = graph.context_for_query("")
        assert isinstance(result, QueryResult)
        assert result.triples == []


class TestPrune:
    def test_removes_low_confidence(self, graph: OntologyGraph) -> None:
        graph.add_triples([
            _triple("a", confidence=0.1, obj="b"),
            _triple("c", confidence=0.9, obj="d"),
        ])
        removed = graph.prune(min_confidence=0.5)
        assert removed == 1
        remaining = graph.query_triples()
        assert len(remaining) == 1
        assert remaining[0].confidence == 0.9

    def test_prune_empty_graph(self, graph: OntologyGraph) -> None:
        assert graph.prune() == 0


class TestStats:
    def test_basic_stats(self, graph: OntologyGraph) -> None:
        graph.add_triples([_triple("a", obj="b"), _triple("a", obj="c")])
        s = graph.stats()
        assert s["nodes"] == 3
        assert s["edges"] == 2
        assert "top_entities" in s
        assert s["top_entities"][0][0] == "test:a"

    def test_empty_stats(self, graph: OntologyGraph) -> None:
        s = graph.stats()
        assert s["nodes"] == 0
        assert s["edges"] == 0
        assert s["top_entities"] == []
