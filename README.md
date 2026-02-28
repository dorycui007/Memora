# Memora

**A local-first decision intelligence platform that turns your life into a structured, interconnected knowledge graph.**

You tell Memora things — by typing, speaking, or taking screenshots. It builds a living graph of your life, then three AI agents continuously reason over it to surface hidden connections, flag forgotten commitments, and help you make better decisions.

**This is not a note-taking app.** Context capture is the input. Better high-stakes decisions, proactive recommendations, and strategic foresight are the output.

---

## The Problem

Your life is fragmented across dozens of tools. Calendar, notes, messages, finances, health apps — none of them talk to each other. When you're stressed about a deadline, no tool knows you also promised a friend you'd help them move, have an overdue invoice, and haven't exercised in two weeks.

- **67% of saved notes are never revisited** — your notes app is a graveyard
- **No tool models life holistically** — calendar, task manager, journal, CRM, none of them connect
- **Cross-domain connections are invisible** — stress correlates with overcommitment correlates with declining health, but no tool sees this

## What Memora Does

Memora ingests raw data from your life, resolves entities, builds an ontology graph, deploys AI agents, and surfaces hidden connections — the same pipeline Palantir uses at enterprise/government scale, applied to a single human life.

**Capture anything:**
> "Had coffee with Sam Chen today. He promised to introduce me to his investor by next Friday. We discussed the pitch deck — he thinks we should emphasize the graph differentiation more."

**Memora extracts and structures it:**
- Creates an EVENT (coffee meeting), a COMMITMENT (investor intro, due Friday), and a NOTE (pitch deck feedback)
- Links everything to the existing PERSON (Sam Chen) and PROJECT (Memora)
- Classifies into the right life domains (Professional, Ventures)
- Scores confidence, checks for duplicates, and commits atomically

**Then reasons over it continuously:**
- "Sam has missed 2 of his last 5 commitments — follow up Thursday, not Friday"
- "Your stress mentions correlate with your 4 overdue commitments — you're overextended"
- "Your Academic network has had no input in 8 days — CSC148 assignment due in 2 days"

---

## Core Concepts

### The Knowledge Graph

Everything in your life becomes nodes and edges in a typed, attributed graph:

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

### Three AI Agents

| Agent | Role | What It Does |
|---|---|---|
| **Archivist** | Graph Writer | Extracts structured entities and relationships from every capture |
| **Strategist** | Graph Analyst | Reads the graph, generates daily briefings, recommends actions, challenges your assumptions |
| **Researcher** | Internet Bridge | Searches the web (with anonymized queries), deposits verified facts into the Truth Layer |

An orchestrator coordinates the agents. For high-stakes questions like "Should I take this job offer?", all three agents work in parallel, then deliberate and synthesize a recommendation with citations.

### The Living Graph Engine

Unlike static note-taking apps, Memora's graph evolves on its own through deterministic algorithms — no AI required:

- **Decay scoring** — unvisited knowledge fades exponentially, like human memory
- **Bridge discovery** — finds hidden connections between different life domains using embedding similarity
- **Network health** — computes per-network status (On Track / Needs Attention / Falling Behind) from commitment completion rates and alert ratios
- **Spaced repetition (SM-2)** — resurfaces important knowledge on a scientifically-optimized schedule
- **Gap detection** — identifies orphaned commitments, stalled goals, and neglected relationships
- **Commitment scanning** — flags overdue promises and approaching deadlines

These algorithms are the anti-wrapper defense. Remove the LLM entirely and the graph, the decay mechanics, the health scores, the bridge discovery, the spaced repetition — all of it still works.

### The Truth Layer

A verified fact store that prevents AI recommendations from being built on fiction:

- Facts are typed by source reliability: **Primary** (official records) > **Secondary** (articles, papers) > **Self-Reported** (hearsay)
- Static facts never expire. Dynamic facts get periodic rechecking.
- Every agent recommendation is cross-referenced against verified facts. Contradictions are flagged.

### Human-in-the-Loop

Memora proposes, you decide:

- High-confidence extractions (>85%) are auto-approved, with a daily review digest as a safety net
- Ambiguous cases are flagged for your review
- High-impact changes (merges, deletions, contradictions) always require explicit confirmation

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTATION    React + TypeScript + Sigma.js graph viz        │
├─────────────────────────────────────────────────────────────────┤
│  API             FastAPI + WebSocket streaming                  │
├─────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE    3 AI Agents + LangGraph Orchestrator           │
├─────────────────────────────────────────────────────────────────┤
│  CORE ENGINE     Decay, Bridges, Health, SM-2, Gap Detection    │
├─────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE  DuckDB + LanceDB + all-mpnet-base-v2           │
└─────────────────────────────────────────────────────────────────┘
```

**Local-first.** Everything runs on your machine. The databases are embedded. The embedding model runs locally. The only external call is to the LLM API (BYOK — bring your own key). Infrastructure cost: **$0/month**. LLM cost: **~$10–15/month**.

---

## The 9-Stage Pipeline

Every capture flows through a complete pipeline before becoming committed knowledge:

```
You type / speak / photograph something
    │
    ▼
 1. Raw Input Capture ─── accept and timestamp
    │
    ▼
 2. Preprocessing ─── normalize dates, detect language, dedup (no AI)
    │
    ▼
 3. Archivist Extraction ─── AI proposes graph changes (structured JSON)
    │
    ▼
 4. Entity Resolution ─── is "Sam" the same Sam from yesterday? (6 signals)
    │
    ▼
 5. Proposal Assembly ─── package all changes atomically
    │
    ▼
 6. Validation Gate ─── route by confidence
    │
    ├── Auto-Approve (≥85%)
    ├── Daily Digest (60–85%)
    └── Explicit Confirm (high-impact)
    │
    ▼
 7. Graph Commit ─── atomic transaction, all-or-nothing
    │
    ▼
 8. Post-Commit ─── embeddings, bridge discovery, notifications, fact-checking
```

---

## Daily Briefing

Every morning, Memora delivers a life situation report:

1. **Network Status** — per-network health with momentum direction
2. **Open Alerts** — approaching deadlines, decaying relationships, stale commitments
3. **Cross-Network Bridges** — new correlations discovered ("Your stress mentions correlate with your overdue commitments")
4. **Recommended Actions** — people to contact, deadlines to renegotiate, opportunities to pursue
5. **Review Queue** — knowledge nodes due for spaced repetition

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, TypeScript, Vite, Sigma.js, TipTap, Tailwind, Zustand |
| **Backend** | Python 3.12+, FastAPI, Uvicorn, Pydantic, LangGraph |
| **AI** | OpenAI API (GPT-5-nano), MCP servers for web research |
| **Storage** | DuckDB (graph), LanceDB (vectors), all-mpnet-base-v2 (embeddings) |
| **Scheduling** | APScheduler for background jobs |

---

## Project Structure

```
memora/
├── frontend/                 # React + TypeScript web app
│   └── src/
│       ├── components/       # Capture, graph, network, briefing, council UI
│       ├── views/            # Page-level components
│       ├── stores/           # Zustand state management
│       └── lib/              # API client, utilities
│
├── backend/
│   ├── memora/
│   │   ├── agents/           # Archivist, Strategist, Researcher, Orchestrator
│   │   ├── api/              # FastAPI routes, schemas, WebSocket
│   │   ├── core/             # Pipeline, entity resolution, decay, bridges,
│   │   │                     # health scoring, SM-2, truth layer, gap detection
│   │   ├── graph/            # DuckDB models, repository, ontology, migrations
│   │   ├── vector/           # LanceDB store, embedding engine
│   │   ├── scheduler/        # APScheduler job definitions
│   │   └── mcp/              # MCP tool servers (search, scraping, academic)
│   ├── cli.py                # Rich terminal interface
│   └── tests/
│
├── architecture.md           # Full system architecture document
├── lecture.md                # Architecture lecture (CSC148 context)
└── docker-compose.yml        # Local deployment
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- An OpenAI API key

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/memora.git
cd memora

# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env          # Add your OPENAI_API_KEY

# Frontend
cd ../frontend
npm install

# Run
cd ../backend && uvicorn memora.api.app:app --reload &
cd ../frontend && npm run dev
```

Memora will be available at `http://localhost:5173` with the API at `http://localhost:8000`.

### CLI

```bash
cd backend
python cli.py
```

The CLI provides a full terminal interface for captures, graph browsing, proposal review, network health dashboards, and council queries.

---

## Why Not Just Use ChatGPT?

| Capability | ChatGPT | Memora |
|---|---|---|
| Remembers your life across sessions | No | Yes — persistent knowledge graph |
| Tracks commitments and deadlines | No | Yes — with decay and alerts |
| Finds cross-domain connections | No | Yes — bridge discovery algorithm |
| Cites specific evidence | Hallucination risk | Yes — graph nodes + verified facts |
| Works without internet | No | Mostly — only LLM calls need internet |
| You own your data | No | Yes — everything local on your disk |
| Resurfaces forgotten knowledge | No | Yes — SM-2 spaced repetition |

**The graph is the product, the LLM is the interface.** Remove the LLM and the knowledge graph, truth layer, decay mechanics, health scoring, bridge discovery, and spaced repetition all remain a fully queryable life database.

---

## Documentation

- **[architecture.md](./architecture.md)** — Full technical architecture (schemas, algorithms, API spec, deployment)
- **[lecture.md](./lecture.md)** — Architecture walkthrough with CSC148 connections (designed for students)

---

## License

Proprietary. All rights reserved.
