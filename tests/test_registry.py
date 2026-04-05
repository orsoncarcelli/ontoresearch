"""Tests for the plugin registry and discovery system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ontology.protocols import DomainPlugin, EnricherProtocol
from ontology.registry import PluginRegistry, discover_plugins

if TYPE_CHECKING:
    from ontology.graph import OntologyGraph


class StubEnricher:
    """Minimal enricher for testing."""

    @property
    def name(self) -> str:
        return "stub_enricher"

    def enrich(self, triples: list, backend: object) -> list:
        return []


class StubPlugin:
    """Minimal DomainPlugin implementation for testing."""

    def __init__(self, plugin_name: str = "test_plugin", ns: str = "testns") -> None:
        self._name = plugin_name
        self._namespace = ns
        self.registered = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def namespace(self) -> str:
        return self._namespace

    def register(self, graph: OntologyGraph) -> None:
        self.registered = True

    def enrichers(self) -> list[EnricherProtocol]:
        return [StubEnricher()]  # type: ignore[list-item]


class FailingPlugin:
    """Plugin that raises during register()."""

    @property
    def name(self) -> str:
        return "failing_plugin"

    @property
    def namespace(self) -> str:
        return "fail"

    def register(self, graph: OntologyGraph) -> None:
        raise RuntimeError("Plugin registration failed")

    def enrichers(self) -> list[EnricherProtocol]:
        return []


class TestPluginRegistry:
    def test_register_and_list(self) -> None:
        reg = PluginRegistry()
        plugin = StubPlugin()
        reg.register_plugin(plugin)
        assert "test_plugin" in reg.list_plugins()
        assert reg.get_plugin("test_plugin") is plugin

    def test_get_nonexistent_returns_none(self) -> None:
        reg = PluginRegistry()
        assert reg.get_plugin("nope") is None

    def test_register_multiple(self) -> None:
        reg = PluginRegistry()
        p1 = StubPlugin("alpha", "ns_a")
        p2 = StubPlugin("beta", "ns_b")
        reg.register_plugin(p1)
        reg.register_plugin(p2)
        assert reg.list_plugins() == ["alpha", "beta"]

    def test_register_overwrites_same_name(self) -> None:
        reg = PluginRegistry()
        p1 = StubPlugin("dup", "ns1")
        p2 = StubPlugin("dup", "ns2")
        reg.register_plugin(p1)
        reg.register_plugin(p2)
        assert reg.get_plugin("dup") is p2

    def test_plugins_property_returns_copy(self) -> None:
        reg = PluginRegistry()
        reg.register_plugin(StubPlugin())
        plugins = reg.plugins
        plugins["hacked"] = StubPlugin("hacked")  # type: ignore[assignment]
        assert "hacked" not in reg.plugins

    def test_register_all_calls_register(self, tmp_path: object) -> None:
        from ontology.config import KernelConfig
        from ontology.graph import OntologyGraph

        config = KernelConfig(backend="networkx", persist_path=tmp_path / "g.json")  # type: ignore[operator]
        graph = OntologyGraph(config=config)

        reg = PluginRegistry()
        p = StubPlugin()
        reg.register_plugin(p)
        reg.register_all(graph)
        assert p.registered is True

    def test_register_all_handles_failure(self, tmp_path: object) -> None:
        from ontology.config import KernelConfig
        from ontology.graph import OntologyGraph

        config = KernelConfig(backend="networkx", persist_path=tmp_path / "g.json")  # type: ignore[operator]
        graph = OntologyGraph(config=config)

        reg = PluginRegistry()
        good = StubPlugin("good")
        bad = FailingPlugin()
        reg.register_plugin(good)
        reg.register_plugin(bad)
        reg.register_all(graph)
        assert good.registered is True


class TestDomainPluginProtocol:
    def test_stub_satisfies_protocol(self) -> None:
        plugin = StubPlugin()
        assert isinstance(plugin, DomainPlugin)

    def test_enrichers_returns_list(self) -> None:
        plugin = StubPlugin()
        enrichers = plugin.enrichers()
        assert len(enrichers) == 1


class TestDiscoverPlugins:
    def test_discover_returns_list(self) -> None:
        """discover_plugins with no matching entry points returns empty list."""
        result = discover_plugins(group="ontology.test.nonexistent")
        assert result == []
