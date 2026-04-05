"""Plugin registry — auto-discovery via entry points.

Discovers domain plugins registered under the 'ontology.plugins' entry-point
group. Plugins are loaded lazily and registered with the graph on demand.

Manual registration is also supported for testing.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING

from ontokernel.protocols import DomainPlugin

if TYPE_CHECKING:
    from ontokernel.graph import OntologyGraph

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Manages discovered and manually registered domain plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, DomainPlugin] = {}

    def register_plugin(self, plugin: DomainPlugin) -> None:
        """Manually register a plugin (useful for testing)."""
        self._plugins[plugin.name] = plugin
        logger.info("Registered plugin: %s (namespace=%s)", plugin.name, plugin.namespace)

    def get_plugin(self, name: str) -> DomainPlugin | None:
        """Look up a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """Return sorted list of registered plugin names."""
        return sorted(self._plugins)

    @property
    def plugins(self) -> dict[str, DomainPlugin]:
        """All registered plugins."""
        return dict(self._plugins)

    def register_all(self, graph: OntologyGraph) -> None:
        """Call register() on all loaded plugins."""
        for plugin in self._plugins.values():
            try:
                plugin.register(graph)
                logger.info("Plugin %s registered with graph", plugin.name)
            except Exception:
                logger.warning(
                    "Plugin %s failed to register", plugin.name, exc_info=True
                )


def discover_plugins(group: str = "ontology.plugins") -> list[DomainPlugin]:
    """Discover plugins via importlib entry points.

    Each entry point should reference a callable that returns a DomainPlugin
    instance (typically a class with no-arg constructor).
    """
    plugins: list[DomainPlugin] = []
    matching = importlib.metadata.entry_points(group=group)

    for ep in matching:
        try:
            plugin_cls = ep.load()
            plugin = plugin_cls() if callable(plugin_cls) else plugin_cls
            plugins.append(plugin)
            logger.info("Discovered plugin via entry point: %s", ep.name)
        except Exception:
            logger.warning(
                "Failed to load plugin entry point: %s", ep.name, exc_info=True
            )

    return plugins
