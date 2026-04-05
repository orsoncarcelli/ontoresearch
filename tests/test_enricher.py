"""Tests for ontology.enricher — HubDecomposer + EnrichmentPipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology.backends.networkx import NetworkXBackend
from ontology.enricher import EnrichmentPipeline, HubDecomposer
from ontology.schema import EntityRef, Predicate, Triple


@pytest.fixture()
def backend(tmp_path: Path) -> NetworkXBackend:
    return NetworkXBackend(persist_path=tmp_path / "enricher_test.json")


def _ref(name: str, ns: str = "test") -> EntityRef:
    return EntityRef(namespace=ns, name=name)


def _triple(
    subj: str, pred: Predicate, obj: str, ns: str = "test"
) -> Triple:
    return Triple(
        subject=_ref(subj, ns),
        predicate=pred,
        obj=_ref(obj, ns),
        confidence=0.7,
        source="test",
    )


class TestHubDecomposer:
    def test_decomposes_hub(self, backend: NetworkXBackend) -> None:
        triples = [
            _triple("hub", Predicate.INFLUENCES, f"target_{i}")
            for i in range(6)
        ]
        backend.add_triples(triples)

        decomposer = HubDecomposer(min_degree=5)
        derived = decomposer.enrich([], backend)

        assert len(derived) > 0
        sub_entity_triples = [
            t for t in derived
            if t.subject.name == "hub" and t.predicate == Predicate.RELATED_TO
        ]
        assert len(sub_entity_triples) >= 1
        sub_name = sub_entity_triples[0].obj.name
        assert "drivers" in sub_name

    def test_ignores_low_degree(self, backend: NetworkXBackend) -> None:
        triples = [
            _triple("small", Predicate.INFLUENCES, f"t_{i}")
            for i in range(2)
        ]
        backend.add_triples(triples)

        decomposer = HubDecomposer(min_degree=5)
        derived = decomposer.enrich([], backend)
        assert derived == []

    def test_multiple_predicate_groups(self, backend: NetworkXBackend) -> None:
        triples = [
            _triple("hub", Predicate.INFLUENCES, "a"),
            _triple("hub", Predicate.INFLUENCES, "b"),
            _triple("hub", Predicate.INFLUENCES, "c"),
            _triple("hub", Predicate.PREDICTS, "d"),
            _triple("hub", Predicate.PREDICTS, "e"),
        ]
        backend.add_triples(triples)

        decomposer = HubDecomposer(min_degree=5)
        derived = decomposer.enrich([], backend)

        sub_entities = {
            t.obj.name for t in derived
            if t.subject.name == "hub" and t.predicate == Predicate.RELATED_TO
        }
        assert "hub_drivers" in sub_entities
        assert "hub_forecast" in sub_entities

    def test_name_property(self) -> None:
        d = HubDecomposer()
        assert d.name == "hub_decomposer"


class TestEnrichmentPipeline:
    def test_empty_pipeline(self, backend: NetworkXBackend) -> None:
        pipeline = EnrichmentPipeline()
        derived = pipeline.run(backend)
        assert derived == []

    def test_single_enricher(self, backend: NetworkXBackend) -> None:
        triples = [
            _triple("hub", Predicate.INFLUENCES, f"t_{i}")
            for i in range(6)
        ]
        backend.add_triples(triples)

        pipeline = EnrichmentPipeline([HubDecomposer(min_degree=5)])
        derived = pipeline.run(backend)
        assert len(derived) > 0

        all_triples = backend.query_triples()
        assert len(all_triples) > 6

    def test_add_enricher(self, backend: NetworkXBackend) -> None:
        pipeline = EnrichmentPipeline()
        pipeline.add(HubDecomposer(min_degree=5))
        assert len(pipeline._enrichers) == 1

    def test_pipeline_feeds_derived_into_graph(self, backend: NetworkXBackend) -> None:
        triples = [
            _triple("hub", Predicate.INFLUENCES, f"t_{i}")
            for i in range(6)
        ]
        backend.add_triples(triples)

        initial_count = len(backend.query_triples())
        pipeline = EnrichmentPipeline([HubDecomposer(min_degree=5)])
        pipeline.run(backend)
        final_count = len(backend.query_triples())

        assert final_count > initial_count
