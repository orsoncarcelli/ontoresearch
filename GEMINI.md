# ontokernel

`ontokernel` is a standalone, domain-agnostic ontology kernel — a typed knowledge graph engine designed to power AI agents and swarm intelligence. It is a greenfield rebuild of the ontology logic from `onto-market`, focusing on architectural purity, pluggable backends, and thread safety.

## Project Overview

- **Purpose:** A typed knowledge graph engine for feature extraction, ML inference (Brier scoring), and multi-domain support (prediction markets, crypto, NBA, politics).
- **Core Principles:**
  - **Kernel Purity:** Domains consume the kernel but never modify it.
  - **Pluggable Backends:** Supports Kuzu (embedded, default), NetworkX (fallback), and Neo4j (production scale).
  - **Pydantic v2:** Used for typed schemas and validation (Triple, Entity, Relation, Namespace).
  - **Namespaced Triples:** Every entity uses namespaced identifiers (e.g., `polymarket:Market`).
  - **Thread Safety:** RLock on all mutations.

## Building and Running

### Environment Setup
Requires Python >= 3.11.
```bash
conda activate onto-market
pip install -e ".[dev]"
```

### Development Commands
- **Tests:** `python -m pytest tests/ -x -q`
- **Type Checking:** `mypy src/`
- **Linting:** `ruff check src/ tests/` (once configured)

## Development Conventions

- **Language:** Python >= 3.11 with Pydantic v2 for data validation.
- **Code Style:** Use spaces (not tabs), keep filenames/directories lowercase.
- **Project Structure:**
  - `src/ontokernel/`: Main implementation.
  - `tests/`: Test suite mirroring the `src/` structure.
- **Interfaces:** Use `typing.Protocol` for all pluggable components (backends, plugins, enrichers) to avoid rigid base class inheritance.
- **Plugin System:** Register domain plugins via `pyproject.toml` entry points under `[project.entry-points."ontology.plugins"]`.
- **Event Bus:** Use the lightweight pub/sub system in `events.py` for reactive enrichment.

## Target Directory Layout

```
src/ontokernel/
├── protocols.py          # Abstract interfaces (OntologyBackend, DomainPlugin, EnricherProtocol)
├── schema.py             # Pydantic v2 models: Triple, Entity, Relation, Namespace
├── namespace.py          # Namespace registry + validation
├── graph.py              # Facade — delegates to current backend
├── registry.py           # Auto-discovery via entry_points
├── enricher.py           # Domain-agnostic enrichers (e.g., topological)
├── events.py             # Lightweight pub/sub event bus
├── backends/             # Kuzu (default), NetworkX, Neo4j
└── config.py             # Kernel configuration
```
