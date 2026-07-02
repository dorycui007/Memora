# Memora

Personal strategic intelligence platform. CLI-first, event-driven knowledge graph.

## Tech Stack

- **Language:** Python 3.12+, Pydantic v2
- **Graph Storage:** DuckDB (embedded)
- **Vector Storage:** Weaviate (embedded, HNSW)
- **Embeddings:** all-mpnet-base-v2 (768-dim, local)
- **LLM:** OpenAI gpt-5-nano (Responses API)
- **Orchestration:** LangGraph (multi-agent state machine)
- **Scheduling:** APScheduler (13 background jobs)
- **Events:** In-process async event bus (asyncio.Queue)
- **CLI:** ANSI terminal rendering (primary interface)

## Commands

```bash
# Run the CLI (primary)
python cli.py

# Run tests
pytest

# Run tests with coverage
pytest --cov=memora --cov-report=term-missing

# Lint
ruff check .

# Seed data
python scripts/seed_positions.py
python scripts/import_courses.py
python scripts/import_people.py
python scripts/import_strategy.py
```

## Architecture

- `memora/agents/` — AI agents (Archivist, Strategist, Researcher, Orchestrator, Watch Agent)
- `memora/core/` — Domain logic (pipeline, event bus, entity resolution, decay, patterns, position tracker, academic tracker, deadline manager, election intel, web monitor, etc.)
- `memora/graph/` — Graph models (17 node types, 36 edge types), YAML-driven ontology registry, repository (DuckDB), migrations (v1-v7)
- `memora/vector/` — Embedding engine + Weaviate vector store
- `memora/connectors/` — Data source adapters (calendar, markdown)
- `memora/mcp/` — MCP tool servers (search, GitHub, Playwright)
- `memora/scheduler/` — APScheduler background jobs (13 jobs)
- `cli/` — CLI commands and rendering
- `scripts/` — Data seeding scripts

## Key Patterns

- **CLI-first** — ANSI terminal rendering as the only interface; talks directly to the repository/core modules, no HTTP layer in between
- **Event-driven** — In-process async event bus with publish/subscribe
- **YAML-driven ontology** — Entity/edge types defined in `ontology_default.yaml`, loaded by `OntologyRegistry`
- **Dependency Injection** throughout (pipeline, engines, agents)
- **Pydantic v2 BaseModel** for all graph entities (17 node types, 36 edge types, 9 networks)
- **Async-first** pipeline with `asyncio.to_thread` for CPU-bound work
- **Lazy initialization** for expensive dependencies (embedding model, truth layer)
- **Atomic graph commits** via DuckDB transactions
- **`@safe_run` decorator** (`memora/core/decorators.py`) for graceful error handling
- **Custom exceptions** in `memora/core/exceptions.py`

## Conventions

- Use `from __future__ import annotations` in all files
- Union types: `X | Y` (not `Optional[X]`)
- Enums for all type fields (NodeType, EdgeType, NetworkType, etc.)
- Parameterized SQL queries only (no string interpolation)
- `yaml.safe_load()` only (never `yaml.load()`)
