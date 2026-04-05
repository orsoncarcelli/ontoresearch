"""Kuzu-specific tests beyond the shared conformance suite.

Covers: discrete relation types, batch insert, persistence recovery,
all predicate types, and schema validation.
"""

from __future__ import annotations

import time
from pathlib import Path

from ontokernel.backends.kuzu import KuzuBackend
from ontokernel.schema import EntityRef, Predicate, Triple


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


class TestDiscreteRelationTypes:
    """Each Predicate enum member is stored in its own Kuzu relation table."""

    def test_all_predicate_types(self, tmp_path: Path) -> None:
        """Every predicate in the enum can be stored and retrieved."""
        b = KuzuBackend(db_path=tmp_path / "kuzu_all_preds")
        for i, pred in enumerate(Predicate):
            b.add_triple(_triple(f"s_{i}", pred, f"o_{i}"))

        for _i, pred in enumerate(Predicate):
            results = b.query_triples(predicate=pred)
            assert len(results) == 1, f"Predicate {pred} returned {len(results)} results"
            assert results[0].predicate == pred

    def test_same_pair_different_predicates(self, tmp_path: Path) -> None:
        """Same (s,o) pair with different predicates = separate edges."""
        b = KuzuBackend(db_path=tmp_path / "kuzu_multi_pred")
        b.add_triple(_triple("a", Predicate.INFLUENCES, "b"))
        b.add_triple(_triple("a", Predicate.PREDICTS, "b"))
        b.add_triple(_triple("a", Predicate.SUPPORTS, "b"))

        all_triples = b.query_triples()
        assert len(all_triples) == 3
        preds = {t.predicate for t in all_triples}
        assert preds == {Predicate.INFLUENCES, Predicate.PREDICTS, Predicate.SUPPORTS}

    def test_remove_one_predicate_keeps_others(self, tmp_path: Path) -> None:
        b = KuzuBackend(db_path=tmp_path / "kuzu_remove_pred")
        b.add_triple(_triple("a", Predicate.INFLUENCES, "b"))
        b.add_triple(_triple("a", Predicate.PREDICTS, "b"))

        b.remove_triple(_ref("a"), Predicate.INFLUENCES, _ref("b"))
        results = b.query_triples()
        assert len(results) == 1
        assert results[0].predicate == Predicate.PREDICTS


class TestPersistenceRecovery:
    def test_reopen_after_close(self, tmp_path: Path) -> None:
        """Data survives database close/reopen."""
        db_path = tmp_path / "kuzu_recovery"
        b1 = KuzuBackend(db_path=db_path)
        triples = [
            _triple("x", Predicate.SUPPORTS, "y", confidence=0.95),
            _triple("y", Predicate.OPPOSES, "z", confidence=0.6),
            _triple("z", Predicate.CORRELATES_WITH, "x", confidence=0.8),
        ]
        b1.add_triples(triples)
        del b1

        b2 = KuzuBackend(db_path=db_path)
        results = b2.query_triples()
        assert len(results) == 3

    def test_entity_data_persists(self, tmp_path: Path) -> None:
        db_path = tmp_path / "kuzu_entity_persist"
        b1 = KuzuBackend(db_path=db_path)
        b1.add_triple(_triple("alpha", source="agent_x"))
        del b1

        b2 = KuzuBackend(db_path=db_path)
        e = b2.get_entity(_ref("alpha"))
        assert e is not None
        assert "agent_x" in e.sources


class TestBatchInsert:
    def test_500_triples_batch(self, tmp_path: Path) -> None:
        b = KuzuBackend(db_path=tmp_path / "kuzu_batch")
        triples = [
            _triple(f"src_{i}", Predicate.INFLUENCES, f"tgt_{i}", confidence=i / 500)
            for i in range(500)
        ]
        t0 = time.monotonic()
        b.add_triples(triples)
        dt = time.monotonic() - t0

        stats = b.stats()
        assert stats["edges"] == 500
        assert dt < 60.0, f"Batch insert of 500 triples took {dt:.2f}s"

    def test_mixed_predicate_batch(self, tmp_path: Path) -> None:
        b = KuzuBackend(db_path=tmp_path / "kuzu_mixed")
        preds = list(Predicate)
        triples = [
            _triple(f"s_{i}", preds[i % len(preds)], f"o_{i}")
            for i in range(100)
        ]
        b.add_triples(triples)
        assert b.stats()["edges"] == 100


class TestNamespaceHandling:
    def test_cross_namespace_triples(self, tmp_path: Path) -> None:
        b = KuzuBackend(db_path=tmp_path / "kuzu_ns")
        t = Triple(
            subject=EntityRef(namespace="polymarket", name="btc_price"),
            predicate=Predicate.INFLUENCES,
            obj=EntityRef(namespace="crypto", name="bitcoin"),
            confidence=0.9,
            source="cross_ns_test",
        )
        b.add_triple(t)
        results = b.query_triples()
        assert len(results) == 1
        assert results[0].subject.namespace == "polymarket"
        assert results[0].obj.namespace == "crypto"
