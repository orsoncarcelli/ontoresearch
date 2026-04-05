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
from ontokernel import OntologyGraph, Triple, EntityRef, Predicate
from ontokernel.config import KernelConfig

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
from ontokernel import OntologyGraph, PluginRegistry, discover_plugins

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

## Polymarket & external data

**Ontokernel does not call HTTP APIs.** It only stores and queries typed triples. Consumers (for example **onto-market** / prediction-markets) pull markets from Polymarket’s **Gamma** and **CLOB** surfaces; Polymarket’s own reference is the [`polymarket-agents`](https://github.com/Polymarket/polymarket-agents) repo (`GammaMarketClient`, `py-clob-client`).

**Alignment for your mission:** When mapping API payloads into the graph, use **stable ids** (Gamma market id, CLOB token ids) inside `EntityRef` names or `metadata`, alongside display strings. That keeps ontology-backed priors joinable with official trader tooling and with SQLite / ML datasets derived from the same exports.

See **onto-market** `CLAUDE.md` → *Polymarket data sources (official stack alignment)* for the concrete endpoint and env-var mapping.



 How Ontokernel Works

  Ontokernel is a typed knowledge graph engine. It stores
  facts as triples (subject → predicate → object),
  validates everything through Pydantic v2, and lets you
  swap storage backends without changing consumer code.

  Core Data Model

  Everything flows through four types defined in
  schema.py:

  EntityRef — the atom. Every entity in the graph is a
  (namespace, name) pair, not a raw string. Internally
  it's always structured; the "polymarket:bitcoin" string
  form only appears at IO boundaries.

  EntityRef(namespace="polymarket", name="bitcoin")
    .qualified  →  "polymarket:bitcoin"
    .parse("polymarket:bitcoin")  →
  EntityRef(namespace="polymarket", name="bitcoin")
    .parse("bitcoin", default_ns="polymarket")  →  same
  thing

  Both fields are normalized to lowercase+stripped on
  creation via a model validator.

  Predicate — a closed StrEnum of 9 allowed relationships:

  influences, related_to, contradicts, predicts,
  caused_by,
  involves, supports, opposes, correlates_with

  Unknown values raise ValidationError — no silent
  coercion.

  Triple — the fundamental unit. Frozen (immutable)
  Pydantic model:

  Triple(
      subject: EntityRef,        # who
      predicate: Predicate,      # relationship type
      obj: EntityRef,            # to whom
      confidence: float,         # 0.0–1.0, default 0.7
      source: str,               # where this fact came
  from
      timestamp: float,          # when (epoch)
      metadata: dict[str, Any],  # extensible
  )

  Entity — accumulated node metadata (sources, first/last
  seen, properties). Created implicitly when a triple
  references a new entity.

  The Layer Cake

  ┌─────────────────────────────────────────┐
  │  Consumer (pred-markets, agents, etc.)  │
  ├─────────────────────────────────────────┤
  │  OntologyGraph  (graph.py — facade)     │  ← public
  API
  │    context_for(), prune(), stats()      │  ←
  convenience methods
  ├─────────────────────────────────────────┤
  │  OntologyBackend  (protocol)            │  ← contract
  ├──────────┬──────────┬───────────────────┤
  │ NetworkX │  Kuzu    │  Neo4j (stub)     │  ← backends
  └──────────┴──────────┴───────────────────┘

  1. Backend Protocol (protocols.py)

  The contract every storage engine must satisfy — 10
  methods:

  ┌───────────────────────┬───────────────────────────┐
  │        Method         │          Purpose          │
  ├───────────────────────┼───────────────────────────┤
  │ add_triple(t)         │ Insert one triple         │
  ├───────────────────────┼───────────────────────────┤
  │ add_triples(ts)       │ Batch insert              │
  ├───────────────────────┼───────────────────────────┤
  │ remove_triple(s, p,   │ Delete specific edge      │
  │ o)                    │                           │
  ├───────────────────────┼───────────────────────────┤
  │ remove_entity(ref)    │ Delete node + all edges   │
  ├───────────────────────┼───────────────────────────┤
  │ get_entity(ref)       │ Node metadata lookup      │
  ├───────────────────────┼───────────────────────────┤
  │ query_triples(s?, p?, │ Pattern match (any combo  │
  │  o?)                  │ of filters)               │
  ├───────────────────────┼───────────────────────────┤
  │ neighbors(ref,        │ Out/in/both edges for a   │
  │ direction)            │ node                      │
  ├───────────────────────┼───────────────────────────┤
  │ stats()               │ Node + edge counts        │
  ├───────────────────────┼───────────────────────────┤
  │ persist()             │ Write to disk             │
  ├───────────────────────┼───────────────────────────┤
  │ load()                │ Read from disk            │
  └───────────────────────┴───────────────────────────┘

  Critically, context_for, prune, and analytics are not in
   this protocol. They live in the facade.

  2. NetworkX Backend (backends/networkx.py)

  The reference implementation. Uses MultiDiGraph
  (multiple edges between same node pair — one per
  predicate type).

  Key mechanics:

  - Upsert semantics: Adding a triple with the same
  (subject, predicate, obj) merges — confidence takes the
  max, metadata merges. It doesn't create duplicates.
  - Edge key = predicate value: The MultiDiGraph edge key
  is the predicate string ("influences", "predicts",
  etc.), so you can have both A influences B and A
  predicts B as separate edges.
  - Node key = qualified name: Nodes are keyed by
  "namespace:name" strings. Node data stores the Entity
  fields (sources, timestamps).
  - RLock on all mutations: add_triple, add_triples,
  remove_triple, remove_entity, persist — all held under
  one reentrant lock. The facade does NOT add a second
  lock.
  - Atomic persistence: JSON via temp file + os.replace().
   If the process dies mid-write, you get the old file,
  not a corrupt one.
  - Orphan cleanup: When an edge is removed, nodes with
  degree 0 are automatically deleted.

  3. Kuzu Backend (backends/kuzu.py)

  The optimized backend. Embedded database (no server).
  The critical design choice:

  One relationship table per predicate. Instead of a
  generic Relation table with a predicate column, each
  enum member gets its own Kuzu relationship type:

  Node table:  Entity(qname PRIMARY KEY, namespace, name,
  sources, first_seen, last_seen, properties)
  Rel tables:  INFLUENCES(confidence, source, ts,
  metadata)
               PREDICTS(confidence, source, ts, metadata)
               CORRELATES_WITH(...)
               ...9 total

  This means queries like "find all things that influence
  X" hit a single table instead of scanning and filtering.
   Same RLock pattern as NetworkX.

  4. Facade (graph.py)

  OntologyGraph is the public API. Constructor takes an
  optional KernelConfig, instantiates the right backend
  via create_backend().

  It delegates all 10 core ops straight to the backend,
  then adds three convenience methods:

  - context_for(query, top_n=15) — token-overlap
  retrieval. Splits query into words > 3 chars, finds
  entities whose names match, walks their neighbors,
  returns the top facts ranked by confidence. This is what
   agents call to get prior knowledge.
  - prune(min_confidence=0.3) — removes all edges below
  the threshold. Returns count removed.
  - stats() — wraps the backend's basic stats with top-10
  entities by degree.

  Enrichment Pipeline (enricher.py)

  Two components, both domain-agnostic:

  HubDecomposer — finds nodes with degree >= min_degree,
  groups their neighbors by predicate, and creates faceted
   sub-entities:

  "bitcoin" (degree 8)
    → "bitcoin_drivers"     (influences neighbors)
    → "bitcoin_forecast"    (predicts neighbors)
    → "bitcoin_correlations" (correlates_with neighbors)

  Each facet gets a related_to edge back to the hub and
  inherits the hub's neighbors under the original
  predicate. This prevents hub nodes from becoming noisy
  catch-alls.

  EnrichmentPipeline — takes a list of EnricherProtocol
  instances, runs them in sequence, feeds derived triples
  into the backend. Explicit invocation only — the caller
  decides when to enrich. No event bus, no reactive
  firing.

  Namespace System (namespace.py)

  NamespaceRegistry tracks valid prefixes. Built-in:
  default, system. Plugins register their own (e.g.,
  polymarket). Prefixes must be lowercase alphanumeric
  with underscores.

  migrate_bare_entity("bitcoin price", "polymarket") →
  EntityRef(namespace="polymarket", name="bitcoin_price")
  — normalizes spaces to underscores, lowercases, strips.

  Migration (migration.py)

  Reads onto-market's legacy ontology.json (NetworkX
  node_link_data format):

  1. Parse nodes → convert bare strings to namespaced
  EntityRef via migrate_bare_entity
  2. Parse edges → validate predicates against closed
  vocabulary (unknown → related_to with warning)
  3. Return typed Triple list
  4. migrate_graph() wraps this: load → add_triples →
  persist

  Plugin System (registry.py)

  Entry-point auto-discovery:

  # in a consumer's pyproject.toml
  [project.entry-points."ontology.plugins"]
  polymarket =
  "onto_market.domains.polymarket:PolymarketPlugin"

  discover_plugins() calls importlib.metadata.entry_points
  (group="ontology.plugins"), loads each, returns
  DomainPlugin instances. PluginRegistry manages them and
  calls plugin.register(graph) on demand.

  Config (config.py)

  Four fields, that's it:

  class KernelConfig(BaseSettings):
      backend: Literal["networkx", "kuzu", "neo4j"] =
  "networkx"
      persist_path: Path = Path("data/ontology.json")
      default_namespace: str = "default"
      auto_discover_plugins: bool = True

  Reads from env vars with ONTOLOGY_ prefix. No
  thread_safe toggle — locking is always on.

  How Pred-Markets Uses It

  Pred-markets has an adapter layer
  (onto_market/ontology/graph.py) that wraps the kernel:

  pred-markets Triple (dataclass, string fields)
      ↓  .to_kernel()
  kernel Triple (Pydantic, EntityRef fields)
      ↓
  kernel backend (NetworkX/Kuzu)

  The adapter preserves the old string-based API so agents
   and enrichers don't need to change. Unnamespaced
  strings like "bitcoin" automatically get the default
  namespace ("polymarket"). The enricher pipeline (market
  metadata, ML features, resolved outcomes, hub
  decomposition) produces adapter Triples, which convert
  to kernel Triples at the boundary.