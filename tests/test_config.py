"""Tests for ontology.config — defaults, env var override."""

from __future__ import annotations

from pathlib import Path

from ontokernel.config import KernelConfig


class TestKernelConfig:
    def test_defaults(self) -> None:
        cfg = KernelConfig()
        assert cfg.backend == "networkx"
        assert cfg.persist_path == Path("data/ontology.json")
        assert cfg.default_namespace == "default"
        assert cfg.auto_discover_plugins is True

    def test_explicit_override(self) -> None:
        cfg = KernelConfig(
            backend="kuzu",
            persist_path=Path("/tmp/test.db"),
            default_namespace="polymarket",
            auto_discover_plugins=False,
        )
        assert cfg.backend == "kuzu"
        assert cfg.persist_path == Path("/tmp/test.db")
        assert cfg.default_namespace == "polymarket"
        assert cfg.auto_discover_plugins is False

    def test_env_var_override(self, monkeypatch: object) -> None:
        import pytest

        mp = pytest.MonkeyPatch()
        mp.setenv("ONTOLOGY_BACKEND", "kuzu")
        mp.setenv("ONTOLOGY_DEFAULT_NAMESPACE", "nba")
        try:
            cfg = KernelConfig()
            assert cfg.backend == "kuzu"
            assert cfg.default_namespace == "nba"
        finally:
            mp.undo()
