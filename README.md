# ontology-kernel

Domain-agnostic ontology kernel — a typed knowledge graph engine.

## What it does

Stores semantic triples (subject → predicate → object) in a namespace-qualified, confidence-weighted directed graph. Designed to power prediction market agents, ML inference pipelines, and multi-domain knowledge systems.

## Install

```bash
conda activate onto-market
pip install -e ".[dev]"
```

Requires Python >= 3.11.

## Quick start

```python
from ontology import OntologyGraph, Triple, EntityRef, Predicate
from ontology.config import KernelConfig

graph = OntologyGraph(KernelConfig(persist_path="data/ontology.json"))

graph.add_triple(Triple(
    subject=EntityRef(namespace="polymarket", name="bitcoin_price"),
    predicate=Predicate.INFLUENCES,
    obj=EntityRef(namespace="polymarket", name="market_sentiment"),
    confidence=0.85,
    source="planning_agent",
))

context = graph.context_for("bitcoin market")
graph.persist()
```

## Commands

```bash
make test        # pytest -x -q
make lint        # ruff check
make typecheck   # mypy src/
make dryrun      # all three
```

## Architecture

- **schema.py** — Pydantic v2 models: `Triple`, `EntityRef`, `Predicate`, `Entity`
- **protocols.py** — `OntologyBackend`, `EnricherProtocol`, `DomainPlugin` (typing.Protocol)
- **namespace.py** — namespace registry + migration helpers
- **backends/networkx.py** — MultiDiGraph reference backend (test fallback)
- **backends/kuzu.py** — embedded Kuzu backend (discrete relation types per predicate)
- **backends/neo4j.py** — production stub (not yet implemented)
- **graph.py** — thin facade with convenience methods (`context_for`, `prune`, `stats`)
- **enricher.py** — `HubDecomposer` + `EnrichmentPipeline` (explicit, no reactive events)
- **migration.py** — load onto-market's legacy `ontology.json`
- **registry.py** — `PluginRegistry` + `discover_plugins` (entry-point auto-discovery)
- **config.py** — `KernelConfig` via pydantic-settings

## Backends

| Backend | Status | Use case |
|---------|--------|----------|
| NetworkX | Reference | Tests, lightweight usage |
| Kuzu | Production-ready | Embedded, fast, millions of triples |
| Neo4j | Stub | Production cluster scale (future) |

Set via `ONTOLOGY_BACKEND=kuzu` env var or `KernelConfig(backend="kuzu")`.

## Plugin system

Domain plugins register via `pyproject.toml` entry points:

```toml
[project.entry-points."ontology.plugins"]
polymarket = "onto_market.domains.polymarket:PolymarketPlugin"
```

```python
from ontology import OntologyGraph, PluginRegistry, discover_plugins

graph = OntologyGraph()
registry = PluginRegistry()
for plugin in discover_plugins():
    registry.register_plugin(plugin)
registry.register_all(graph)
```

## Key design decisions

- `EntityRef(namespace, name)` is structured internally; `"ns:name"` only at IO boundaries
- Closed predicate vocabulary via `StrEnum` — unknown predicates raise `ValidationError`
- Each predicate is a discrete relation type (separate Kuzu table, separate NX edge key)
- Backend-owned `RLock` on all mutations — facade stays thin
- Convenience methods (`context_for`, `prune`) live in facade, not backend protocol
- Enrichment is explicit pipeline invocation — no reactive events yet (planned v2.0)
