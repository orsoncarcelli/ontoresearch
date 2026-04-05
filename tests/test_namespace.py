"""Tests for ontology.namespace — registry, parsing, migration."""

from __future__ import annotations

import pytest

from ontokernel.namespace import NamespaceRegistry, migrate_bare_entity
from ontokernel.schema import EntityRef


class TestNamespaceRegistry:
    def test_builtins_registered(self) -> None:
        reg = NamespaceRegistry()
        assert reg.is_registered("default")
        assert reg.is_registered("system")

    def test_register_custom(self) -> None:
        reg = NamespaceRegistry()
        reg.register("polymarket")
        assert reg.is_registered("polymarket")
        assert "polymarket" in reg.list_namespaces()

    def test_register_empty_raises(self) -> None:
        reg = NamespaceRegistry()
        with pytest.raises(ValueError, match="empty"):
            reg.register("")

    def test_register_invalid_format_raises(self) -> None:
        reg = NamespaceRegistry()
        with pytest.raises(ValueError, match="Invalid"):
            reg.register("123bad")
        with pytest.raises(ValueError, match="Invalid"):
            reg.register("has space")

    def test_register_normalizes_case(self) -> None:
        reg = NamespaceRegistry()
        reg.register("UPPER")
        assert reg.is_registered("upper")

    def test_register_idempotent(self) -> None:
        reg = NamespaceRegistry()
        reg.register("crypto")
        reg.register("crypto")
        assert reg.list_namespaces().count("crypto") == 1

    def test_list_sorted(self) -> None:
        reg = NamespaceRegistry()
        reg.register("zulu")
        reg.register("alpha")
        ns_list = reg.list_namespaces()
        assert ns_list == sorted(ns_list)

    def test_parse_ref_registered(self) -> None:
        reg = NamespaceRegistry()
        reg.register("polymarket")
        ref = reg.parse_ref("polymarket:bitcoin")
        assert ref.namespace == "polymarket"
        assert ref.name == "bitcoin"

    def test_parse_ref_unregistered_raises(self) -> None:
        reg = NamespaceRegistry()
        with pytest.raises(ValueError, match="not registered"):
            reg.parse_ref("unknown:entity")

    def test_parse_ref_with_default(self) -> None:
        reg = NamespaceRegistry()
        ref = reg.parse_ref("entity_name", default_ns="default")
        assert ref.namespace == "default"
        assert ref.name == "entity_name"

    def test_qualify(self) -> None:
        ref = EntityRef(namespace="test", name="hello")
        assert NamespaceRegistry.qualify(ref) == "test:hello"


class TestMigrateBareEntity:
    def test_basic(self) -> None:
        ref = migrate_bare_entity("bitcoin price", "polymarket")
        assert ref.namespace == "polymarket"
        assert ref.name == "bitcoin_price"

    def test_extra_spaces(self) -> None:
        ref = migrate_bare_entity("  fed  interest  rate  ", "polymarket")
        assert ref.name == "fed_interest_rate"

    def test_case_normalization(self) -> None:
        ref = migrate_bare_entity("Bitcoin Price", "Polymarket")
        assert ref.namespace == "polymarket"
        assert ref.name == "bitcoin_price"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            migrate_bare_entity("", "polymarket")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            migrate_bare_entity("   ", "polymarket")

    def test_leading_trailing_underscores_stripped(self) -> None:
        ref = migrate_bare_entity("_bitcoin_", "test")
        assert ref.name == "bitcoin"
