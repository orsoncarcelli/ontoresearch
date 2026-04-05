"""Namespace registry and validation.

Enforces that every entity reference carries a namespace prefix.
Provides migration helpers for bare-string entities from onto-market.
"""

from __future__ import annotations

import re

from ontokernel.schema import EntityRef


class NamespaceRegistry:
    """Register and validate namespace prefixes.

    Built-in namespaces 'default' and 'system' are always available.
    Plugins register their own (e.g. 'polymarket', 'nba', 'crypto').
    """

    _BUILTIN = frozenset({"default", "system"})

    def __init__(self) -> None:
        self._registered: set[str] = set(self._BUILTIN)

    def register(self, prefix: str) -> None:
        """Register a namespace prefix."""
        prefix = prefix.lower().strip()
        if not prefix:
            raise ValueError("Namespace prefix cannot be empty")
        if not re.match(r"^[a-z][a-z0-9_]*$", prefix):
            raise ValueError(
                f"Invalid namespace prefix {prefix!r}: "
                "must be lowercase alphanumeric with underscores, starting with a letter"
            )
        self._registered.add(prefix)

    def is_registered(self, prefix: str) -> bool:
        """Check if a namespace prefix is registered."""
        return prefix.lower().strip() in self._registered

    def list_namespaces(self) -> list[str]:
        """Return sorted list of registered namespaces."""
        return sorted(self._registered)

    def parse_ref(self, s: str, default_ns: str | None = None) -> EntityRef:
        """Parse a string into an EntityRef, validating the namespace.

        If the string contains ':', split on first ':' and validate the namespace.
        If no ':', requires default_ns.
        """
        ref = EntityRef.parse(s, default_ns=default_ns)
        if not self.is_registered(ref.namespace):
            raise ValueError(
                f"Namespace {ref.namespace!r} is not registered. "
                f"Registered: {self.list_namespaces()}"
            )
        return ref

    @staticmethod
    def qualify(ref: EntityRef) -> str:
        """Serialize an EntityRef to 'namespace:name' string form."""
        return ref.qualified


def migrate_bare_entity(name: str, namespace: str) -> EntityRef:
    """Convert a bare-string entity from onto-market into a namespaced EntityRef.

    Normalizes: lowercase, strip, replace spaces with underscores,
    collapse multiple underscores.
    """
    normalized = name.lower().strip()
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized)
    normalized = normalized.strip("_")
    if not normalized:
        raise ValueError(f"Cannot migrate empty entity name: {name!r}")
    return EntityRef(namespace=namespace.lower().strip(), name=normalized)
