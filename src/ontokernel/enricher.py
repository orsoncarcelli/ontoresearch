"""Domain-agnostic enrichment — explicit pipeline, no reactive events.

Only HubDecomposer ships with the kernel. Domain-specific enrichers
(market metadata, ML features, resolved outcomes) stay in onto-market.

Enrichment is explicit: callers invoke EnrichmentPipeline.run() after
mutations complete. No inline event firing during locked mutations.
"""

from __future__ import annotations

import logging
import time

from ontokernel.protocols import EnricherProtocol, OntologyBackend
from ontokernel.schema import EntityRef, Predicate, Triple

logger = logging.getLogger(__name__)

_PRED_FACETS: dict[str, str] = {
    "influences": "drivers",
    "predicts": "forecast",
    "correlates_with": "correlations",
    "contradicts": "risks",
    "opposes": "opposition",
    "supports": "support",
    "involves": "context",
    "related_to": "relations",
    "caused_by": "causes",
    "resolves_to": "outcomes",
    "has_outcome": "outcomes",
    "precedes": "timeline",
}


class HubDecomposer:
    """Split high-degree nodes into faceted sub-entities.

    When a node accumulates >= min_degree edges, group its neighbors
    by predicate type and create sub-entity nodes:
      "bitcoin" (degree 8) -> "bitcoin:drivers", "bitcoin:forecast", etc.

    Ported from onto-market/enricher.py decompose_hub_entities().
    """

    def __init__(self, min_degree: int = 5, default_namespace: str = "system") -> None:
        self._min_degree = min_degree
        self._default_ns = default_namespace

    @property
    def name(self) -> str:
        return "hub_decomposer"

    def enrich(
        self, triples: list[Triple], backend: OntologyBackend
    ) -> list[Triple]:
        """Examine the graph for hub entities and decompose them."""
        derived: list[Triple] = []
        now = time.time()

        all_triples = backend.query_triples()
        degree: dict[str, int] = {}
        for t in all_triples:
            s = t.subject.qualified
            o = t.obj.qualified
            degree[s] = degree.get(s, 0) + 1
            degree[o] = degree.get(o, 0) + 1

        hubs = [k for k, d in degree.items() if d >= self._min_degree]
        for hub_key in hubs:
            hub_ref = EntityRef.parse(hub_key)
            neighbors = backend.neighbors(hub_ref, direction="both")

            pred_groups: dict[str, list[EntityRef]] = {}
            for t in neighbors:
                pred_val = t.predicate.value
                other = t.obj if t.subject == hub_ref else t.subject
                pred_groups.setdefault(pred_val, []).append(other)

            for pred_str, group_refs in pred_groups.items():
                if len(group_refs) < 2:
                    continue
                facet = _PRED_FACETS.get(pred_str, pred_str)
                sub_name = f"{hub_ref.name}_{facet}"
                sub_ref = EntityRef(namespace=hub_ref.namespace, name=sub_name)

                derived.append(
                    Triple(
                        subject=hub_ref,
                        predicate=Predicate.RELATED_TO,
                        obj=sub_ref,
                        confidence=0.8,
                        source="hub_decomposer",
                        timestamp=now,
                    )
                )
                pred_enum = Predicate(pred_str)
                for nb_ref in group_refs[:6]:
                    derived.append(
                        Triple(
                            subject=sub_ref,
                            predicate=pred_enum,
                            obj=nb_ref,
                            confidence=0.7,
                            source="hub_decomposer",
                            timestamp=now,
                        )
                    )

        if derived:
            logger.info(
                "HubDecomposer: decomposed %d hubs into %d triples",
                len(hubs),
                len(derived),
            )
        return derived


class EnrichmentPipeline:
    """Run a sequence of enrichers, feeding derived triples into the graph.

    Explicit invocation only — caller decides when to enrich.
    """

    def __init__(self, enrichers: list[EnricherProtocol] | None = None) -> None:
        self._enrichers: list[EnricherProtocol] = enrichers or []

    def add(self, enricher: EnricherProtocol) -> None:
        self._enrichers.append(enricher)

    def run(
        self, backend: OntologyBackend, triples: list[Triple] | None = None
    ) -> list[Triple]:
        """Run all enrichers in sequence. Returns all derived triples."""
        input_triples = triples or []
        all_derived: list[Triple] = []

        for enricher in self._enrichers:
            derived = enricher.enrich(input_triples, backend)
            if derived:
                backend.add_triples(derived)
                all_derived.extend(derived)
                logger.info(
                    "EnrichmentPipeline: %s produced %d triples",
                    enricher.name,
                    len(derived),
                )

        return all_derived
