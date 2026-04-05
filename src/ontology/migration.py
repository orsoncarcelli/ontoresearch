"""Migration adapter for onto-market's legacy ontology format.

Loads onto-market's data/ontology.json (NetworkX node_link_data format),
converts bare-string entities to namespaced EntityRef, validates predicates
against the closed vocabulary, and returns typed Triples.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ontology.namespace import migrate_bare_entity
from ontology.protocols import OntologyBackend
from ontology.schema import EntityRef, Predicate, Triple

logger = logging.getLogger(__name__)


def load_legacy_json(path: Path, namespace: str) -> list[Triple]:
    """Read onto-market's ontology.json and convert to typed Triples.

    The legacy format uses NetworkX node_link_data with:
    - Nodes keyed by bare strings (e.g. "bitcoin price")
    - Edges with "predicate", "confidence", "source", "timestamp"

    Unknown predicates are mapped to RELATED_TO with a warning.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))

    node_map: dict[str, EntityRef] = {}
    nodes = raw.get("nodes", [])
    for node in nodes:
        node_id = str(node.get("id", ""))
        if not node_id:
            continue
        try:
            ref = migrate_bare_entity(node_id, namespace)
            node_map[node_id] = ref
        except ValueError:
            logger.warning("Skipping unmigrateable node: %r", node_id)
            continue

    triples: list[Triple] = []
    links = raw.get("links", [])
    for link in links:
        source_id = str(link.get("source", ""))
        target_id = str(link.get("target", ""))

        s_ref = node_map.get(source_id)
        o_ref = node_map.get(target_id)
        if not s_ref or not o_ref:
            logger.warning(
                "Skipping edge with unknown node: %r -> %r", source_id, target_id
            )
            continue

        pred_str = str(link.get("predicate", "related_to")).lower().strip()
        try:
            pred = Predicate(pred_str)
        except ValueError:
            logger.warning(
                "Unknown predicate %r in legacy edge %r -> %r, mapping to related_to",
                pred_str,
                source_id,
                target_id,
            )
            pred = Predicate.RELATED_TO

        confidence = float(link.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))

        triples.append(
            Triple(
                subject=s_ref,
                predicate=pred,
                obj=o_ref,
                confidence=confidence,
                source=str(link.get("source_agent", link.get("source", "legacy"))),
                timestamp=float(link.get("timestamp", 0.0)),
            )
        )

    logger.info(
        "Loaded %d triples from legacy file %s (namespace=%s)",
        len(triples),
        path,
        namespace,
    )
    return triples


def migrate_graph(
    legacy_path: Path,
    backend: OntologyBackend,
    namespace: str,
) -> int:
    """Load legacy JSON and ingest into a backend. Returns triple count."""
    triples = load_legacy_json(legacy_path, namespace)
    if triples:
        backend.add_triples(triples)
        backend.persist()
    return len(triples)
