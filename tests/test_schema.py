"""Tests for ontology.schema — validation, parsing, clamping."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ontology.schema import Entity, EntityRef, Predicate, QueryResult, Triple


class TestPredicate:
    def test_all_members(self) -> None:
        expected = {
            "influences", "related_to", "contradicts", "predicts",
            "caused_by", "involves", "supports", "opposes", "correlates_with",
            "resolves_to", "has_outcome", "precedes",
        }
        assert {p.value for p in Predicate} == expected

    def test_valid_construction(self) -> None:
        assert Predicate("influences") == Predicate.INFLUENCES

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            Predicate("nonsense_predicate")


class TestEntityRef:
    def test_basic_construction(self) -> None:
        ref = EntityRef(namespace="test", name="hello")
        assert ref.namespace == "test"
        assert ref.name == "hello"
        assert ref.qualified == "test:hello"

    def test_normalization(self) -> None:
        ref = EntityRef(namespace="  TEST ", name=" Hello World ")
        assert ref.namespace == "test"
        assert ref.name == "hello world"

    def test_parse_qualified(self) -> None:
        ref = EntityRef.parse("polymarket:bitcoin_price")
        assert ref.namespace == "polymarket"
        assert ref.name == "bitcoin_price"

    def test_parse_with_default_ns(self) -> None:
        ref = EntityRef.parse("bitcoin_price", default_ns="polymarket")
        assert ref.namespace == "polymarket"
        assert ref.name == "bitcoin_price"

    def test_parse_no_ns_no_default_raises(self) -> None:
        with pytest.raises(ValueError, match="no namespace"):
            EntityRef.parse("bitcoin_price")

    def test_parse_empty_parts_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid"):
            EntityRef.parse(":name")

    def test_parse_colon_in_name(self) -> None:
        ref = EntityRef.parse("ns:name:with:colons")
        assert ref.namespace == "ns"
        assert ref.name == "name:with:colons"

    def test_frozen(self) -> None:
        ref = EntityRef(namespace="test", name="hello")
        with pytest.raises(ValidationError):
            ref.namespace = "other"  # type: ignore[misc]

    def test_hashable(self) -> None:
        a = EntityRef(namespace="test", name="hello")
        b = EntityRef(namespace="test", name="hello")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_str_repr(self) -> None:
        ref = EntityRef(namespace="test", name="hello")
        assert str(ref) == "test:hello"
        assert "test:hello" in repr(ref)

    def test_empty_namespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EntityRef(namespace="", name="hello")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EntityRef(namespace="test", name="")


class TestTriple:
    def test_basic_construction(self) -> None:
        t = Triple(
            subject=EntityRef(namespace="test", name="a"),
            predicate=Predicate.INFLUENCES,
            obj=EntityRef(namespace="test", name="b"),
        )
        assert t.confidence == 0.7
        assert t.source == ""
        assert t.metadata == {}
        assert t.timestamp > 0

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            Triple(
                subject=EntityRef(namespace="t", name="a"),
                predicate=Predicate.INFLUENCES,
                obj=EntityRef(namespace="t", name="b"),
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            Triple(
                subject=EntityRef(namespace="t", name="a"),
                predicate=Predicate.INFLUENCES,
                obj=EntityRef(namespace="t", name="b"),
                confidence=-0.1,
            )

    def test_invalid_predicate_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Triple(
                subject=EntityRef(namespace="t", name="a"),
                predicate="garbage",  # type: ignore[arg-type]
                obj=EntityRef(namespace="t", name="b"),
            )

    def test_frozen(self) -> None:
        t = Triple(
            subject=EntityRef(namespace="t", name="a"),
            predicate=Predicate.INFLUENCES,
            obj=EntityRef(namespace="t", name="b"),
        )
        with pytest.raises(ValidationError):
            t.confidence = 0.5  # type: ignore[misc]

    def test_metadata(self) -> None:
        t = Triple(
            subject=EntityRef(namespace="t", name="a"),
            predicate=Predicate.INFLUENCES,
            obj=EntityRef(namespace="t", name="b"),
            metadata={"key": "value"},
        )
        assert t.metadata == {"key": "value"}


class TestDecayedConfidence:
    def _make(self, confidence: float = 0.8, ts: float | None = None) -> Triple:
        return Triple(
            subject=EntityRef(namespace="t", name="a"),
            predicate=Predicate.INFLUENCES,
            obj=EntityRef(namespace="t", name="b"),
            confidence=confidence,
            timestamp=ts if ts is not None else time.time(),
        )

    def test_no_age_returns_full_confidence(self) -> None:
        now = time.time()
        t = self._make(0.9, ts=now)
        assert abs(t.decayed_confidence(as_of=now) - 0.9) < 1e-6

    def test_one_half_life_halves_confidence(self) -> None:
        now = time.time()
        one_week_ago = now - 168 * 3600
        t = self._make(1.0, ts=one_week_ago)
        assert abs(t.decayed_confidence(half_life_hours=168.0, as_of=now) - 0.5) < 1e-6

    def test_two_half_lives(self) -> None:
        now = time.time()
        two_weeks_ago = now - 2 * 168 * 3600
        t = self._make(1.0, ts=two_weeks_ago)
        assert abs(t.decayed_confidence(half_life_hours=168.0, as_of=now) - 0.25) < 1e-6

    def test_datetime_as_of(self) -> None:
        ts = 1_700_000_000.0
        one_week_later = datetime.fromtimestamp(ts + 168 * 3600, tz=timezone.utc)
        t = self._make(1.0, ts=ts)
        assert abs(t.decayed_confidence(half_life_hours=168.0, as_of=one_week_later) - 0.5) < 1e-6

    def test_future_timestamp_clamps_to_zero_age(self) -> None:
        now = time.time()
        t = self._make(0.8, ts=now + 3600)
        result = t.decayed_confidence(as_of=now)
        assert abs(result - 0.8) < 1e-6

    def test_default_as_of_uses_now(self) -> None:
        t = self._make(0.8)
        result = t.decayed_confidence()
        assert abs(result - 0.8) < 0.01


class TestEntity:
    def test_defaults(self) -> None:
        e = Entity(ref=EntityRef(namespace="t", name="x"))
        assert e.sources == []
        assert e.properties == {}
        assert e.first_seen > 0
        assert e.last_seen > 0

    def test_mutable(self) -> None:
        e = Entity(ref=EntityRef(namespace="t", name="x"))
        e.sources.append("agent_1")
        assert "agent_1" in e.sources


class TestQueryResult:
    def test_empty(self) -> None:
        qr = QueryResult()
        assert qr.triples == []
        assert qr.entities == []

    def test_with_data(self) -> None:
        t = Triple(
            subject=EntityRef(namespace="t", name="a"),
            predicate=Predicate.RELATED_TO,
            obj=EntityRef(namespace="t", name="b"),
        )
        e = Entity(ref=EntityRef(namespace="t", name="a"))
        qr = QueryResult(triples=[t], entities=[e])
        assert len(qr.triples) == 1
        assert len(qr.entities) == 1
