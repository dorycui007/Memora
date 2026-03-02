# Memora

**A personal Palantir. Your entire life as a living, queryable knowledge graph.**

Memora turns unstructured text into a structured intelligence layer over your life. Type what happened, what you're thinking, what you owe someone — an AI agent extracts entities and relationships, resolves them against your existing graph, and commits them atomically. Then deterministic algorithms take over: decay scoring, bridge discovery, health monitoring, spaced repetition, pattern detection, and gap analysis run continuously without any AI involvement.

This is not a note-taking app. Notes are the input. A living knowledge graph is the output.

---

## Why This Is Cool

Most "AI productivity tools" are thin wrappers around an LLM. Remove the LLM and nothing remains. Memora is the opposite:

- **Graph-first architecture** — 12 node types, 29 edge types, 7 context networks. The same ontology-driven approach Palantir uses at government scale, applied to a single human life.
- **The LLM is replaceable** — Remove it entirely and the graph, the decay mechanics, the health scores, the bridge discovery, the spaced repetition, pattern detection — all of it still works. The AI extracts; the algorithms reason.
- **Cross-domain intelligence** — Your calendar app doesn't know you're overcommitted. Your task manager doesn't know your finances are strained. Memora connects everything and surfaces patterns across domains that no single-purpose tool can see.
- **Fully local** — Both databases are embedded (DuckDB + Weaviate). Embeddings run on your machine. The only external call is OpenAI for extraction. Infrastructure cost: **$0/month**.

---

## How It Works

```
You type text
    → AI extracts entities & relationships (9-stage pipeline)
    → Entity resolution matches against existing graph (6 weighted signals)
    → Atomic commit to knowledge graph
    → 10 background algorithms continuously maintain and evolve the graph
```

**Example capture:**
> "Had coffee with Sam today. He'll intro me to his investor by Friday. Thinks we should emphasize the graph differentiation in the pitch deck."

**Memora extracts:** an EVENT (coffee meeting), a COMMITMENT (investor intro, due Friday), a NOTE (pitch feedback) — links them to PERSON (Sam) and PROJECT (Memora), classifies into Professional + Ventures networks, checks for duplicates, and commits atomically.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+, Pydantic v2 |
| Graph Storage | DuckDB (embedded) |
| Vector Storage | Weaviate (embedded, HNSW) |
| Embeddings | all-mpnet-base-v2 (768-dim, local) |
| LLM | OpenAI gpt-5-nano (Responses API, BYOK) |
| Orchestration | LangGraph (multi-agent state machine) |
| Scheduling | APScheduler (10 background jobs) |
| Interface | CLI with ANSI terminal rendering |

---

## Key Systems

- **AI Council** — 3 specialized agents (Archivist, Strategist, Researcher) coordinated by a LangGraph orchestrator with weighted query classification and CRAG fallback
- **Entity Resolution** — 6-signal weighted matching: exact name, embedding similarity, network overlap, temporal proximity, shared relationships, LLM adjudication
- **Living Graph Engine** — 10 scheduled jobs: decay scoring, bridge discovery, health monitoring, commitment scanning, relationship decay, SM-2 spaced repetition, gap detection, daily briefing, pattern detection, outcome review
- **Truth Layer** — Verified fact store with semantic contradiction detection, confidence tracking, and lifecycle management
- **Pattern Engine** — 11 behavioral detectors that surface recurring patterns across your life domains
- **6 MCP Servers** — Google Search, Brave Search, Semantic Scholar, Playwright Scraper, GitHub, Graph query

---

## Getting Started

```bash
git clone https://github.com/dorycui007/Memora.git
cd Memora
pip install -r requirements.txt
cp .env.example .env   # add your OPENAI_API_KEY
python cli.py
```

---

## Documentation

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — Full technical architecture (schemas, algorithms, data flows)
- **[LECTURE.md](./LECTURE.md)** — Architecture walkthrough designed for CSC148 students at UTM

---

## License

Proprietary. All rights reserved.
