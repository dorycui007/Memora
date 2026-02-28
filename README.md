# Memora

**A local-first decision intelligence platform that turns your life into a structured, interconnected knowledge graph.**

You tell Memora things by typing text captures. An AI agent extracts structured entities and relationships, resolves them against your existing graph, and commits them atomically. Deterministic algorithms then continuously maintain the graph — scoring decay, discovering cross-domain bridges, computing network health, and scheduling spaced repetition reviews.

**This is not a note-taking app.** Context capture is the input. A living, queryable knowledge graph is the output.

---

## The Problem

Your life is fragmented across dozens of tools. Calendar, notes, messages, finances, health apps — none of them talk to each other. When you're stressed about a deadline, no tool knows you also promised a friend you'd help them move, have an overdue invoice, and haven't exercised in two weeks.

- **67% of saved notes are never revisited** — your notes app is a graveyard
- **No tool models life holistically** — calendar, task manager, journal, CRM, none of them connect
- **Cross-domain connections are invisible** — stress correlates with overcommitment correlates with declining health, but no tool sees this

## What Memora Does

Memora ingests text, resolves entities, builds an ontology graph, and runs deterministic algorithms over it — the same pipeline Palantir uses at enterprise/government scale, applied to a single human life.

**Capture anything:**
> "Had coffee with Sam Chen today. He promised to introduce me to his investor by next Friday. We discussed the pitch deck — he thinks we should emphasize the graph differentiation more."

**Memora extracts and structures it:**
- Creates an EVENT (coffee meeting), a COMMITMENT (investor intro, due Friday), and a NOTE (pitch deck feedback)
- Links everything to the existing PERSON (Sam Chen) and PROJECT (Memora)
- Classifies into the right life domains (Professional, Ventures)
- Scores confidence, checks for duplicates, and commits atomically

**Then maintains the graph continuously:**
- Flags overdue commitments and approaching deadlines
- Discovers cross-network bridges via embedding similarity
- Computes per-network health status from commitment completion rates
- Resurfaces fading knowledge through SM-2 spaced repetition

---

## Core Concepts

### The Knowledge Graph

Everything in your life becomes nodes and edges in a typed, attributed graph stored in DuckDB:

**12 node types** across two clusters:

| Life Context (things that happen) | Knowledge (things you know) |
|---|---|
| Event, Person, Commitment | Note, Idea, Project |
| Decision, Goal, Financial Item | Concept, Reference, Insight |

**28 relationship types** across 7 categories — structural, associative, provenance, temporal, personal, social, and cross-network connections.

### Seven Context Networks

The graph is organized into seven living subgraphs, each representing a domain of your life:

| Network | What It Tracks |
|---|---|
| **Academic** | Courses, research, study commitments |
| **Professional** | Work, clients, career goals |
| **Financial** | Transactions, budgets, investments |
| **Health** | Exercise, sleep, stress, medical |
| **Personal Growth** | Learning, skills, habits |
| **Social** | Friends, family, relationships |
| **Ventures** | Side projects, entrepreneurship |

A single node can belong to multiple networks. These multi-membership nodes are where cross-domain intelligence naturally emerges.

### AI Agents

| Agent | Role | Status |
|---|---|---|
| **Archivist** | Extracts structured entities and relationships from text captures via GPT-5-nano | Working |
| **Strategist** | Reads the graph, generates analysis and briefings | Partial — analysis works, briefing generation in progress |
| **Researcher** | Searches the web with anonymized queries, deposits verified facts | Scaffolded — MCP tool integrations in progress |
| **Orchestrator** | LangGraph-based multi-agent coordination and query routing | Partial — routing works, deliberation in progress |

### The Living Graph Engine

Unlike static note-taking apps, Memora's graph evolves on its own through deterministic algorithms — no AI required:

- **Decay scoring** — unvisited knowledge fades exponentially, like human memory
- **Bridge discovery** — finds hidden connections between different life domains using embedding similarity
- **Network health** — computes per-network status (On Track / Needs Attention / Falling Behind) from commitment completion rates and alert ratios
- **Spaced repetition (SM-2)** — resurfaces important knowledge on a scientifically-optimized schedule
- **Gap detection** — identifies orphaned nodes and stalled goals
- **Commitment scanning** — flags overdue promises and approaching deadlines

These algorithms are the anti-wrapper defense. Remove the LLM entirely and the graph, the decay mechanics, the health scores, the bridge discovery, the spaced repetition — all of it still works.

### The Truth Layer

A verified fact store with lifecycle management:

- Facts are stored with confidence scores and lifecycle type (static or dynamic)
- Dynamic facts track recheck intervals (default 90 days)
- Status tracking: active, stale, contradicted, retired

### Human-in-the-Loop

Memora proposes, you decide:

- High-confidence extractions (>=85%) are auto-approved, with a daily review digest as a safety net
- Ambiguous cases are flagged for your review
- High-impact changes (merges, deletions) require explicit confirmation

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTATION    React + TypeScript + Sigma.js + TipTap         │
├─────────────────────────────────────────────────────────────────┤
│  API             FastAPI + WebSocket streaming                  │
├─────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE    Archivist + Strategist + Researcher agents     │
│                  LangGraph Orchestrator + OpenAI API (BYOK)     │
├─────────────────────────────────────────────────────────────────┤
│  CORE ENGINE     Decay, Bridges, Health, SM-2, Gap Detection    │
│                  Commitment Scan, Relationship Decay, Backup    │
├─────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE  DuckDB + LanceDB + all-mpnet-base-v2           │
└─────────────────────────────────────────────────────────────────┘
```

**Local-first.** Everything runs on your machine. The databases are embedded. The embedding model runs locally. The only external call is to the OpenAI API (BYOK — bring your own key). Infrastructure cost: **$0/month**. LLM cost: **~$10–15/month**.

---

## The Capture Pipeline

Every text capture flows through a 9-stage pipeline before becoming committed knowledge:

```
Text input
    │
    ▼
 1. Raw Input ─── accept, timestamp, content-hash for dedup
    │
    ▼
 2. Preprocessing ─── normalize dates and currency, detect language (no AI)
    │
    ▼
 3. Archivist Extraction ─── LLM proposes graph changes as structured JSON
    │
    ▼
 4. Entity Resolution ─── 6-signal matching against existing nodes
    │
    ▼
 5. Proposal Assembly ─── package all changes into atomic proposal
    │
    ▼
 6. Validation Gate ─── route by confidence
    │
    ├── Auto-Approve (>=85%)
    ├── Daily Digest (60–85%)
    └── Explicit Confirm (high-impact)
    │
    ▼
 7. Human Review / Auto-Approve
    │
    ▼
 8. Graph Commit ─── atomic DuckDB transaction, all-or-nothing
    │
    ▼
 9. Post-Commit ─── generate embeddings, discover bridges,
                    update health scores, trigger notifications
```

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Sigma.js, TipTap, Tailwind CSS, Zustand |
| **Backend** | Python 3.12+, FastAPI, Uvicorn, Pydantic v2, LangGraph |
| **AI** | OpenAI Responses API (GPT-5-nano with json_schema mode) |
| **Storage** | DuckDB (graph + proposals + health snapshots), LanceDB (vector embeddings) |
| **Embeddings** | all-mpnet-base-v2 via sentence-transformers (768-dim, runs locally) |
| **Scheduling** | APScheduler (decay, health, bridges, commitment scan, spaced repetition) |
| **CLI** | Rich terminal interface (1600+ lines) with capture, graph browse, review, dashboard |

---

## Project Structure

```
memora/
├── frontend/                 # React + TypeScript web app
│   └── src/
│       ├── components/
│       │   ├── capture/      # CaptureBar (TipTap text input)
│       │   ├── graph/        # GraphCanvas (Sigma.js), NodeDetailPanel, controls
│       │   ├── network/      # NetworkGrid, NetworkCard, NetworkDetail
│       │   ├── council/      # CouncilChat, AgentResponse, streaming
│       │   ├── proposals/    # ReviewQueue, ProposalCard, ProposalDetail
│       │   ├── briefing/     # BriefingView, AlertCard, BridgeCard
│       │   └── common/       # CommandPalette, Layout, EmptyState, errors
│       ├── stores/           # Zustand (graph, capture, council, network, notification)
│       └── lib/              # API client, utilities
│
├── backend/
│   ├── memora/
│   │   ├── agents/           # Archivist, Strategist, Researcher, Orchestrator
│   │   │   └── prompts/      # System prompt templates (.md files)
│   │   ├── api/
│   │   │   ├── routes/       # captures, graph, proposals, council, facts, networks
│   │   │   ├── schemas/      # Pydantic request/response models
│   │   │   └── websocket.py  # WebSocket streaming handler
│   │   ├── core/             # Pipeline, entity resolution, decay, bridges,
│   │   │                     # health scoring, SM-2, truth layer, gap detection,
│   │   │                     # commitment scan, relationship decay, notifications
│   │   ├── graph/            # DuckDB models, repository, ontology, migrations
│   │   ├── vector/           # LanceDB store, sentence-transformers embeddings
│   │   ├── scheduler/        # APScheduler job definitions and setup
│   │   └── mcp/              # MCP tool servers (search, scraping, academic)
│   ├── cli.py                # Rich terminal interface
│   └── tests/
│       ├── unit/             # 15 test files (models, repo, vectors, pipeline,
│       │                     # entity resolution, decay, health, SM-2, bridges, etc.)
│       └── integration/      # 5 test files (archivist, council, e2e, RAG)
│
├── architecture.md           # Full system architecture document
├── lecture.md                # Architecture lecture (CSC148 context)
├── docker-compose.yml        # Docker setup (backend + frontend)
├── Makefile
└── .env.example              # Environment template
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- An OpenAI API key

### Setup

```bash
# Clone
git clone <repo-url>
cd memora

# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env    # Add your OPENAI_API_KEY

# Frontend
cd ../frontend
npm install
```

### Run

**Option 1: Docker**
```bash
docker compose up
```

**Option 2: Manual**
```bash
# Terminal 1 — Backend
cd backend
uvicorn memora.api.app:app --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

**Option 3: CLI only (no frontend needed)**
```bash
cd backend
python cli.py
```

The web app runs at `http://localhost:5173`, API at `http://localhost:8000`.

### Configuration

Memora auto-creates `~/.memora/` on first run with a default `config.yaml`. Key settings:

| Setting | Default | What It Controls |
|---|---|---|
| `auto_approve_threshold` | 0.85 | Confidence cutoff for auto-approving proposals |
| `embedding_model` | all-mpnet-base-v2 | Sentence-transformers model for embeddings |
| `bridge_similarity_threshold` | 0.75 | Cosine similarity cutoff for cross-network bridges |
| `sm2_default_easiness` | 2.5 | SM-2 initial easiness factor |
| `decay_lambda` | per-network | Exponential decay rate (higher = faster fade) |

---

## What Works Today

**Fully functional:**
- Text capture with content-hash deduplication
- 9-stage async pipeline (preprocess → extract → resolve → validate → commit)
- Archivist agent: LLM extraction into Pydantic-validated graph proposals
- Entity resolution: 6-signal weighted matching (exact name, embedding similarity, network overlap, temporal proximity, shared relationships, LLM adjudication)
- DuckDB graph storage with atomic transactions and full CRUD
- LanceDB vector store with dense search, hybrid search, and filtered search
- Proposal review system (auto-approve, digest, explicit confirm)
- Decay scoring with per-network lambda rates
- Network health scoring (on_track / needs_attention / falling_behind)
- SM-2 spaced repetition scheduling
- Bridge discovery (cross-network embedding similarity)
- Commitment scanning (overdue detection)
- Gap detection (orphaned nodes, stalled goals)
- Relationship decay tracking
- Rich CLI with full capture, browse, review, and dashboard flows
- REST API with 6 route groups (captures, graph, proposals, council, facts, networks)
- WebSocket streaming for council queries
- 20 test files (15 unit + 5 integration)

**In progress:**
- Strategist agent: graph analysis works, briefing generation partially implemented
- Orchestrator: query routing works, multi-agent deliberation incomplete
- Researcher agent: query anonymization works, MCP tool integrations scaffolded but not yet connected
- Truth Layer: fact storage and lifecycle tracking work, contradiction detection not yet implemented
- Frontend: components exist for all views (graph, capture, council, network, proposals, briefing, command palette) but integration is ongoing

---

## Documentation

- **[architecture.md](./architecture.md)** — Full technical architecture (schemas, algorithms, API spec, deployment)
- **[lecture.md](./lecture.md)** — Architecture walkthrough with CSC148 connections (designed for students)

---

## License

Proprietary. All rights reserved.
