# Memora System Architecture — Full Lecture

> **Course Context:** CSC148 — Introduction to Computer Science, UTM
> **Prerequisites assumed:** Python, basic OOP (classes, inheritance, composition), abstract data types (stacks, queues, linked lists, trees), recursion, Big-O notation
> **New concepts introduced:** Knowledge graphs, AI agents, databases, APIs, web architecture, vector search, retrieval-augmented generation

---

## Part 1: What Are We Building and Why?

### 1.1 The Problem We're Solving

Think about your life right now as a UTM student. You have:

- Lecture notes in Google Docs
- Assignments tracked in Quercus
- A calendar in Google Calendar
- Texts and group chats on iMessage and Discord
- Financial stuff in your bank app
- Health goals in some fitness app
- Side project ideas scattered in Apple Notes

Here is the problem: **none of these tools talk to each other.**

When you're stressed about a midterm, your calendar doesn't know that you also promised your friend you'd help them move this weekend, that you have a CSC148 assignment due Monday, and that you've been skipping the gym for two weeks. No single tool sees the full picture of your life.

Research backs this up:

- **67% of saved notes are never revisited** — your notes app is a graveyard
- **No tool models life holistically** — calendar, CRM, task manager, journal, none of them talk
- **Cross-domain connections are invisible** — stress correlates with overcommitment correlates with declining grades, but no tool sees this

### 1.2 What Memora Actually Does

Memora is a **decision intelligence platform**. You tell it things — by typing, speaking, or taking screenshots — and it builds a structured **knowledge graph** of your life. Then three AI agents continuously reason over that graph to:

1. Surface hidden connections ("Your stress mentions correlate with your 4 overdue commitments")
2. Flag things you've forgotten ("You promised Sam an intro to your VC contact 14 days ago — still open")
3. Give you a morning briefing ("Here's what needs your attention today, ranked by urgency")
4. Help you make decisions ("Should I take this job offer?" → it considers your commitments, finances, goals, relationships, and current market data)

**This is not a note-taking app.** The input is context capture. The output is **better decisions**.

### 1.3 The Palantir Analogy

To understand what Memora is architecturally, you need to know about Palantir Technologies.

Palantir is a $250B+ company that builds software for governments and large enterprises. Their core product does one thing: **take siloed, disconnected data from dozens of sources and weave it into a unified knowledge graph** where entities (people, places, events, organizations) are linked by typed relationships. Then AI agents reason over that graph to surface hidden connections, predict outcomes, and recommend actions.

For example, in intelligence work:
- A phone number appears in two unrelated cases → Palantir links them
- A financial transaction connects to a known suspect → flagged automatically
- An analyst asks "Who are the key players in this network?" → Palantir traverses the graph

**Memora is that same architecture applied to a single human life.** Instead of government databases, the inputs are your voice memos, text captures, and screenshots. Instead of intelligence analysts, the consumer is you. The entity resolution, the graph construction, the agent-driven reasoning — it's all structurally identical to what Palantir does at nation-state scale.

### 1.4 Connecting to CSC148

If you've taken CSC148, you already know the foundational concepts Memora is built on:

| CSC148 Concept | How Memora Uses It |
|---|---|
| **Trees** | The graph ontology is a hierarchical type system (NodeType → specific properties) |
| **Graphs** | The entire knowledge graph is a directed, labeled, weighted graph — nodes and edges with typed attributes |
| **Abstract Data Types** | Every node type (PERSON, EVENT, COMMITMENT) is an ADT with defined operations |
| **Classes and Inheritance** | Pydantic models use inheritance — `NodeProposal` extends `BaseModel`, all node types share a base schema |
| **Composition** | Agents are composed of tools, context sources, and an LLM backbone |
| **Recursion** | Graph traversal (BFS/DFS) is used in bridge discovery, neighborhood expansion, and gap detection |
| **Big-O** | Vector search is O(log N) via HNSW index. Bridge discovery per-capture is O(log N). Decay scoring is O(N) daily |
| **Queues** | The proposal review system is a priority queue ranked by confidence |
| **Hash tables** | Content deduplication uses SHA-256 hashing. Entity resolution uses hash-based exact matching |

The point: you are not starting from zero. This lecture will connect every architectural concept back to things you already understand.

---

## Part 2: System Architecture — The Big Picture

### 2.1 What is "System Architecture"?

In CSC148, you learned to design individual classes and data structures. **System architecture** is the next level up — it's how you organize an entire application into components, decide how those components communicate, and choose what technologies each component uses.

Think of it like this:
- **CSC148**: You designed a `LinkedList` class with `insert`, `remove`, `search` methods
- **System architecture**: You decide that your application has a **frontend** (what the user sees), a **backend** (the logic), a **database** (where data lives), and **AI agents** (that reason over the data) — and you define exactly how these pieces interact

### 2.2 The Five Layers

Memora is organized into five horizontal layers. Each layer has a specific responsibility and only talks to the layers directly adjacent to it. This is called **layered architecture** — a fundamental pattern in software engineering.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PRESENTATION    What the user sees and interacts with                 │
│                  (React web app, graph visualization, capture input)    │
├─────────────────────────────────────────────────────────────────────────┤
│  API             The communication layer between frontend and backend  │
│                  (REST endpoints, WebSocket for streaming)              │
├─────────────────────────────────────────────────────────────────────────┤
│  INTELLIGENCE    AI agents that reason over the data                   │
│                  (Archivist, Strategist, Researcher, Orchestrator)      │
├─────────────────────────────────────────────────────────────────────────┤
│  CORE ENGINE     Deterministic algorithms that run on schedule         │
│                  (Decay, bridge discovery, health scoring, SM-2)        │
├─────────────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE  Where data actually lives                             │
│                  (Graph database, vector database, embedding model)     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why layers matter:**

Imagine you want to swap the AI model from Claude to GPT-4. With layers, you only change the Intelligence layer. The Core Engine doesn't care — it runs deterministic algorithms that never touch the LLM. The database doesn't care — it just stores nodes and edges. The frontend doesn't care — it just displays whatever the API returns.

This is the **separation of concerns** principle you learned in CSC148, but applied to an entire system instead of a single class.

### 2.3 Why "Local-First"?

Memora runs entirely on your computer. There's no cloud server, no account to create, no monthly subscription to the platform itself. The databases are **embedded** — they run inside the application process, storing files on your disk.

Why does this matter?

1. **Privacy**: Your life data never leaves your machine. The only external call is to the Claude API when AI agents need to think, and even then, the Researcher agent anonymizes queries before searching the web.

2. **Cost**: Infrastructure cost is literally $0. The only cost is the LLM API usage ($10–15/month).

3. **Ownership**: You own your data files. If Memora the company disappeared tomorrow, your graph database files are still on your disk, queryable with standard tools.

4. **Lesson from history**: When Meta acquired Limitless/Rewind in December 2025, users lost their data permanently. When Mem.ai failed (called a "$40M failure"), users had no proprietary data structures to export. Memora avoids this by keeping everything local.

### 2.4 Technology Choices Explained

Here's every technology in the stack, and why it was chosen. Since you're in CSC148, I'll explain the ones you may not have encountered:

**Frontend (what the user sees):**

| Technology | What It Is | Why It's Used |
|---|---|---|
| **React** | A JavaScript library for building user interfaces. You define components (like classes) that render HTML. | Industry standard. Component model maps cleanly to Memora's views |
| **TypeScript** | JavaScript with type annotations. Like adding type hints to Python. | Catches bugs at compile time, essential for large codebases |
| **Vite** | A build tool that bundles your frontend code for the browser. Like compiling, but for web code. | Extremely fast hot-reload during development |
| **Sigma.js** | A library for rendering graphs (nodes + edges) in the browser using WebGL (GPU acceleration). | Can handle 10,000+ nodes smoothly. The graph is the core UI |
| **TipTap** | A rich text editor component. Think Google Docs, but embeddable in your app. | Users need a good text input for captures |
| **Tailwind CSS** | A utility-first CSS framework. Instead of writing custom CSS, you compose utility classes. | Fast styling without writing custom CSS files |
| **Zustand** | A lightweight state management library. Like a global dictionary that all components can read/write. | Simpler than Redux. Manages graph state, agent state, notifications |

**Backend (the logic):**

| Technology | What It Is | Why It's Used |
|---|---|---|
| **Python 3.12+** | The language you already know from CSC148 | AI/ML ecosystem, Pydantic, FastAPI all Python-native |
| **FastAPI** | A Python web framework for building APIs. You define functions that handle HTTP requests. | Auto-generates docs, built-in validation, async support |
| **Uvicorn** | An ASGI server — the actual process that listens for HTTP requests and routes them to FastAPI. Like a receptionist at a hotel desk. | Production-grade, handles concurrent connections |
| **Pydantic** | A Python library for data validation using type annotations. Like dataclasses, but with automatic validation. | The Archivist's output is validated against Pydantic schemas |
| **LangGraph** | A framework for building multi-agent AI systems with state machines. | Orchestrates the three agents with defined state transitions |

**AI / Intelligence:**

| Technology | What It Is | Why It's Used |
|---|---|---|
| **Claude API** | Anthropic's large language model, accessed via API. You send text, it sends back text. | Powers the three AI agents (Archivist, Strategist, Researcher) |
| **Claude Haiku** | A smaller, faster, cheaper Claude model. | Used for the Archivist (runs on every capture — needs to be fast and cheap) |
| **Claude Sonnet** | A larger, smarter, more expensive Claude model. | Used for Strategist and Researcher (complex reasoning, less frequent) |
| **MCP (Model Context Protocol)** | A standard protocol for connecting AI agents to external tools (like web search). | The Researcher uses 6 MCP servers to access the internet |

**Data / Infrastructure:**

| Technology | What It Is | Why It's Used |
|---|---|---|
| **RyuGraph** | An embedded graph database (fork of KuzuDB). Stores nodes and edges with properties. Supports Cypher queries (like SQL but for graphs). | Zero infrastructure cost, runs in-process |
| **DuckDB** | An embedded SQL database (like SQLite but much faster for analytics). Fallback if RyuGraph isn't sufficient. | Proven technology, excellent performance |
| **LanceDB** | An embedded vector database. Stores numerical vectors and enables similarity search. | Enables semantic search — "find nodes similar to this query" |
| **BGE-M3** | A local embedding model that converts text into 1024-dimensional numerical vectors. | Runs locally (no API cost), supports 100+ languages |
| **APScheduler** | A Python library for scheduling recurring jobs. Like cron, but in Python. | Runs background mechanics (decay, bridges, health) on schedule |

---

## Part 3: The Knowledge Graph — Core Data Structure

### 3.1 What Is a Knowledge Graph?

In CSC148, you studied graphs: nodes connected by edges. A **knowledge graph** is a specific kind of graph where:

1. **Nodes represent real-world entities** (people, events, ideas) — not just abstract values
2. **Edges represent typed relationships** between entities (not just "connected to")
3. **Both nodes and edges carry properties** (metadata, timestamps, confidence scores)

Here's the CSC148 version of a graph:

```python
# CSC148-style graph
class Graph:
    """A simple graph with nodes and edges."""
    def __init__(self):
        self._nodes = {}       # {node_id: node_data}
        self._edges = {}       # {(source, target): edge_data}
```

Here's what Memora's knowledge graph adds:

```python
# Memora-style knowledge graph (conceptual)
class KnowledgeGraph:
    """A typed, attributed knowledge graph."""
    def __init__(self):
        self._nodes = {}       # {UUID: TypedNode}
        self._edges = {}       # {UUID: TypedEdge}
        self._networks = {}    # {NetworkType: set[UUID]}  subgraph membership
        self._index = None     # HNSW vector index for semantic search
```

The key differences:
- Every node has a **type** (PERSON, EVENT, COMMITMENT, etc.)
- Every edge has a **category** and **subtype** (SOCIAL.KNOWS, TEMPORAL.TRIGGERED, etc.)
- Nodes carry **embeddings** (numerical vectors for similarity search)
- Nodes belong to **networks** (subgraphs representing life domains)
- Everything has **confidence scores** and **provenance** (where it came from)

### 3.2 Nodes: The Entities

Memora has **12 node types** organized into two clusters:

**Life Context Nodes** — things that *happen* in your life:

| Type | What It Represents | Example |
|---|---|---|
| `EVENT` | Something that happened or will happen | "Coffee meeting with Sam on Feb 25" |
| `PERSON` | A person in your life | "Sam Chen — investor contact" |
| `COMMITMENT` | A promise made (by you or to you) | "Sam will intro me to his investor by Friday" |
| `DECISION` | A choice you made or need to make | "Decided to focus on graph differentiation" |
| `GOAL` | Something you're working toward | "Launch Memora MVP by March 31" |
| `FINANCIAL_ITEM` | A monetary event | "$5.40 Starbucks receipt on Feb 20" |

**Knowledge Nodes** — things you *know* or *think*:

| Type | What It Represents | Example |
|---|---|---|
| `NOTE` | An observation or reflection | "Sam thinks we should emphasize graph differentiation" |
| `IDEA` | A concept you're developing | "What if we added Obsidian vault import?" |
| `PROJECT` | An organized effort with deliverables | "Memora — decision intelligence platform" |
| `CONCEPT` | An abstract concept you're learning | "Entity resolution — deduplicating graph nodes" |
| `REFERENCE` | An external source | "Palantir Foundry documentation" |
| `INSIGHT` | A cross-domain realization | "My stress correlates with open commitment count" |

**Why two clusters?** The highest-value connections are the ones that **cross clusters**. When a CONCEPT you're studying in CSC148 (knowledge) connects to a PROJECT you're building (life context), that's where the magic happens. These cross-cluster edges are the ones Memora's bridge discovery algorithm specifically looks for.

### 3.3 Understanding Node Properties with Python

Every node, regardless of type, carries a set of shared properties. Let's look at this as a Python class hierarchy — something you're very familiar with from CSC148:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
import hashlib


@dataclass
class BaseNode:
    """
    The base class for all nodes in Memora's knowledge graph.

    CSC148 connection: This is the abstract base class pattern.
    All 12 node types inherit from this class.
    """
    # Identity
    id: str = field(default_factory=lambda: str(uuid4()))
    content_hash: str = ""                # SHA-256 for deduplication

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Content
    title: str = ""
    content: str = ""

    # Embeddings (for semantic search — explained in Part 6)
    embedding: list[float] = field(default_factory=list)  # 1024 dimensions
    # sparse_embedding stored separately

    # Confidence & Trust
    confidence: float = 0.0      # 0.0 to 1.0 — how sure is the Archivist?
    human_approved: bool = False  # has a human verified this?
    proposed_by: str = ""         # which AI agent created this?

    # Context
    networks: list[str] = field(default_factory=list)  # which life domains
    source_capture_id: str = ""   # link back to raw input
    tags: list[str] = field(default_factory=list)

    # Decay & Memory (explained in Part 8)
    access_count: int = 0
    last_accessed: datetime | None = None
    decay_score: float = 1.0     # 1.0 = fresh, 0.0 = forgotten
    review_date: datetime | None = None  # SM-2 spaced repetition

    def compute_content_hash(self) -> str:
        """
        SHA-256 hash of content for deduplication.

        CSC148 connection: This is just a hash function.
        If two nodes have identical content, they get the same hash.
        Used for O(1) duplicate detection.
        """
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class PersonNode(BaseNode):
    """
    A person in the user's life.

    CSC148 connection: This is inheritance.
    PersonNode IS-A BaseNode with additional person-specific attributes.
    """
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    role: str = ""
    relationship_to_user: str = ""
    organization: str = ""
    last_interaction: datetime | None = None


@dataclass
class CommitmentNode(BaseNode):
    """
    A promise made by or to the user.

    CSC148 connection: Uses an enum for status — like the
    state pattern you may have seen.
    """
    due_date: datetime | None = None
    status: str = "open"        # open, completed, overdue, cancelled
    committed_by: str = ""       # who made the promise
    committed_to: str = ""       # who it was made to
    priority: str = "medium"     # low, medium, high, critical


@dataclass
class GoalNode(BaseNode):
    """A goal the user is working toward."""
    target_date: datetime | None = None
    progress: float = 0.0        # 0.0 to 1.0
    milestones: list[dict] = field(default_factory=list)
    status: str = "active"       # active, paused, achieved, abandoned
```

**Key insight for CSC148 students:** Look at the inheritance hierarchy. `PersonNode`, `CommitmentNode`, `GoalNode` all inherit from `BaseNode`. They all get `id`, `content_hash`, `embedding`, `confidence`, `decay_score`, etc. for free. The type-specific properties (like `due_date` for commitments or `name` for people) are added by the subclass. This is exactly the inheritance pattern you practice in CSC148 — the only difference is that in production, we use Pydantic instead of dataclasses (Pydantic adds automatic validation).

### 3.4 Edges: The Relationships

In CSC148, an edge in a graph is typically just a connection between two nodes, maybe with a weight:

```python
# CSC148-style edge
edge = (source_id, target_id, weight)
```

In Memora, edges are **first-class objects** with their own types, categories, and properties:

```python
@dataclass
class Edge:
    """
    A typed, attributed edge in the knowledge graph.

    CSC148 connection: This is like a weighted, directed edge in a graph,
    but with a type label and additional metadata.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    source_id: str = ""          # UUID of source node
    target_id: str = ""          # UUID of target node
    edge_type: str = ""          # e.g., "KNOWS", "TRIGGERED", "PART_OF"
    edge_category: str = ""      # e.g., "SOCIAL", "TEMPORAL", "STRUCTURAL"
    confidence: float = 0.0
    weight: float = 1.0
    bidirectional: bool = False
    properties: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
```

There are **7 edge categories** with **30+ subtypes**. Here's what each category captures, with examples a student would relate to:

**1. STRUCTURAL** — hierarchy and composition
```
PROJECT("Memora") --[CONTAINS]--> COMMITMENT("Build graph DB")
GOAL("Graduate") --[CONTAINS]--> COMMITMENT("Pass CSC148")
COMMITMENT("Pass CSC148") --[SUBTASK_OF]--> GOAL("Graduate")
```
This is like a **tree structure** from CSC148. Projects contain commitments, goals contain sub-goals.

**2. ASSOCIATIVE** — semantic relationships
```
IDEA("Obsidian import") --[RELATED_TO]--> PROJECT("Memora")
CONCEPT("Knowledge graphs") --[INSPIRED_BY]--> REFERENCE("Palantir docs")
NOTE("Sam disagrees") --[CONTRADICTS]--> NOTE("Sam agrees")
```
These are the "soft" connections — things that are related but not in a hierarchical way.

**3. PROVENANCE** — where information came from
```
INSIGHT("Stress correlates with overcommitment") --[DERIVED_FROM]--> NOTE("Felt stressed this week")
FACT("Company X revenue: $50M") --[VERIFIED_BY]--> REFERENCE("SEC filing 2025")
```
**CSC148 connection:** This is like keeping track of your sources in an essay. Every piece of information knows where it came from.

**4. TEMPORAL** — time-ordered causation
```
DECISION("Took the job") --[PRECEDED_BY]--> EVENT("Interview with Company X")
IDEA("V1 of Memora") --[EVOLVED_INTO]--> IDEA("V2 with Truth Layer")
EVENT("Missed deadline") --[TRIGGERED]--> COMMITMENT("Apologize to prof")
```
These edges create a **timeline** of how things developed. The `EVOLVED_INTO` edge is especially powerful — it tracks how your ideas change over time.

**5. PERSONAL** — your stakes and emotions
```
PERSON("You") --[COMMITTED_TO]--> COMMITMENT("Submit CSC148 A3")
PERSON("You") --[DECIDED]--> DECISION("Switch to CS major")
PERSON("You") --[FELT_ABOUT]--> EVENT("Failed midterm")  # sentiment: negative
```

**6. SOCIAL** — people dynamics
```
PERSON("Sam") --[KNOWS]--> PERSON("VC Investor")
PERSON("Prof. Singh") --[INTRODUCED_BY]--> PERSON("Academic advisor")
PERSON("You") --[OWES_FAVOR]--> PERSON("Sam")  # he helped you move
```

**7. NETWORK** — cross-domain connections (the gold)
```
NODE_IN_HEALTH --[BRIDGES]--> NODE_IN_PROFESSIONAL
NODE_IN_ACADEMIC --[CORRELATES_WITH]--> NODE_IN_VENTURES
```
These are the **highest-value edges** in the entire system. They represent connections that no single-domain tool could ever see. A stress mention in your Health network correlating with overdue commitments in your Professional network — that's a BRIDGES edge.

### 3.5 Context Networks: Subgraphs of Your Life

In CSC148, you learned about graphs. A **subgraph** is a subset of a graph's nodes and edges. Memora organizes the knowledge graph into **7 subgraphs called context networks**, each representing a domain of your life:

| Network | What It Tracks | Student Example |
|---|---|---|
| **Academic** | Courses, grades, research, study commitments | CSC148 assignments, lecture notes, study groups |
| **Professional** | Work, clients, career goals | Part-time job, internship applications |
| **Financial** | Money in, money out, budgets | Tuition, rent, part-time job income |
| **Health** | Exercise, sleep, stress, medical | Gym routine, stress levels, doctor visits |
| **Personal Growth** | Learning, skills, habits | Books you're reading, skills you're developing |
| **Social** | Friends, family, social events | Friendships, family calls, social gatherings |
| **Ventures** | Side projects, entrepreneurial ideas | Startup ideas, hackathon projects |

**Critical design point:** A node can belong to **multiple networks**. Your friend "Sam" might be in both Social (he's your friend) and Ventures (he's your co-founder). A commitment to "finish the pitch deck" might be in both Academic (it's for a course project) and Ventures (it's for your startup). These multi-membership nodes are where cross-domain intelligence naturally emerges.

**Network Health:**

Each network has a computed health status:

- 🟢 **On Track** — commitments met, recent engagement
- 🟡 **Needs Attention** — some open alerts, stale commitments
- 🔴 **Falling Behind** — multiple overdue items, no recent input

As a student, imagine getting a notification: "Your Academic network is Falling Behind — 3 overdue commitments, no study input in 5 days." That's actionable intelligence no calendar app gives you.

### 3.6 Graph Operations and Complexity

Let's analyze the time complexity of common graph operations — exactly the kind of analysis you do in CSC148:

| Operation | Algorithm | Time Complexity | Notes |
|---|---|---|---|
| **Add node** | Insert into DB + vector index | O(log N) | HNSW insertion |
| **Add edge** | Insert into DB with FK lookup | O(1) amortized | Index-backed |
| **Find node by ID** | Hash lookup | O(1) | UUID primary key |
| **Find neighbors** | Index scan on edges | O(degree) | Where degree = number of edges from node |
| **Semantic search** | HNSW approximate nearest neighbor | O(log N) | Not exact, but ~95% recall |
| **BFS/DFS traversal** | Standard BFS/DFS | O(V + E) | Same as CSC148! |
| **Bridge discovery** | Embedding comparison across networks | O(log N) per node | HNSW index per network |
| **Decay scoring** | Iterate all nodes, apply formula | O(N) | Run once daily |

**CSC148 connection:** The graph traversal algorithms (BFS, DFS) you learned are exactly what Memora uses for things like "find all nodes within 2 hops of this node" (neighborhood expansion) or "find all GOAL nodes with no recent PROGRESS edges" (gap detection).

---

## Part 4: The Input-to-Graph Pipeline — How Data Gets In

### 4.1 Pipeline Architecture

When you capture something in Memora (type a note, record a voice memo, take a screenshot), it doesn't just get stored — it goes through a **9-stage pipeline** that transforms raw text into structured graph nodes and edges.

This pipeline is the core data flow of the entire system. Every single piece of information traverses all 9 stages.

```
[You type/speak/photograph something]
        │
        ▼
  Stage 1: Raw Input Capture
        │   (accept text, voice, or image)
        ▼
  Stage 2: Preprocessing
        │   (transcribe, OCR, normalize — NO AI involved)
        ▼
  Stage 3: Archivist Extraction
        │   (AI reads your text and proposes graph changes)
        ▼
  Stage 4: Entity Resolution
        │   (is "Sam" the same Sam from yesterday?)
        ▼
  Stage 5: Graph Proposal Assembly
        │   (package all changes into one atomic proposal)
        ▼
  Stage 6: Validation Gate
        │   (how confident are we? route accordingly)
        ├──────────────────┬─────────────────┐
        ▼                  ▼                 ▼
  Auto-Approve      Daily Digest      Explicit Confirm
  (≥ 85% conf.)    (batch review)    (high-impact)
        │                  │                 │
        └──────────────────┴─────────────────┘
        │
        ▼
  Stage 8: Graph Commit
        │   (atomic transaction — all or nothing)
        ▼
  Stage 9: Post-Commit Processing
        │   (generate embeddings, discover bridges, check notifications)
        ▼
  [Knowledge graph updated]
```

Let's walk through each stage in detail with a concrete example.

### 4.2 Running Example

You open Memora and type:

> "Had coffee with Sam Chen today. He promised to introduce me to his investor by next Friday. We discussed the Memora pitch deck — he thinks we should emphasize the graph differentiation more."

Let's trace this through all 9 stages.

### 4.3 Stage 1: Raw Input Capture

**What happens:** The system accepts your text and creates a `Capture` record.

```python
capture = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "modality": "text",
    "raw_content": "Had coffee with Sam Chen today. He promised to introduce me to his investor by next Friday. We discussed the Memora pitch deck — he thinks we should emphasize the graph differentiation more.",
    "content_hash": "a1b2c3d4...",   # SHA-256 of the content
    "created_at": "2026-02-27T10:30:00Z"
}
```

**The SHA-256 hash** is used for **deduplication**. If you accidentally submit the same text twice, the system detects that the hash already exists and skips processing.

**CSC148 connection:** This is a hash table lookup — O(1) to check if we've seen this content before.

**Design constraint:** This stage must complete in **< 2 seconds**. If capture is slow, users won't use it. Zero friction is the design goal.

### 4.4 Stage 2: Preprocessing

**What happens:** Deterministic normalization. No AI involved — this ensures reproducibility.

For our text example:
1. ~~Transcription~~ (not needed — it's already text)
2. ~~OCR~~ (not needed — no image)
3. **Text normalization**:
   - "today" → `2026-02-27` (resolved to actual date)
   - "next Friday" → `2026-03-06` (resolved to actual date)
   - "Sam Chen" → normalized form
4. **Language detection**: English
5. **Dedup check**: Content hash is new → proceed

After preprocessing:
```python
processed = {
    "content": "Had coffee with Sam Chen on 2026-02-27. He promised to introduce me to his investor by 2026-03-06. We discussed the Memora pitch deck — he thinks we should emphasize the graph differentiation more.",
    "detected_dates": ["2026-02-27", "2026-03-06"],
    "detected_names": ["Sam Chen"],
    "language": "en"
}
```

**Why is this stage deterministic (no AI)?** Two reasons:
1. **Reproducibility**: Given the same input, you always get the same output. This is important for debugging.
2. **Cost**: This stage runs on every capture. Making it deterministic means it costs $0.

### 4.5 Stage 3: Archivist Extraction — The Key Stage

**What happens:** The Archivist AI agent reads the processed text and proposes structured graph changes.

This is where the **LLM (Large Language Model)** comes in for the first time. The Archivist is given:

1. **The graph schema** (all 12 node types, 7 edge categories, their properties)
2. **Existing relevant nodes** (fetched via semantic search — "do we already know about Sam Chen?")
3. **The processed text** (from Stage 2)

And it produces a `GraphProposal` — a structured JSON object describing exactly what nodes and edges to create or update.

For our example, the Archivist would produce something like:

```python
proposal = GraphProposal(
    source_capture_id="550e8400...",
    timestamp="2026-02-27T10:30:00Z",
    confidence=0.88,

    nodes_to_create=[
        NodeProposal(
            temp_id="temp_1",
            node_type="EVENT",
            title="Coffee meeting with Sam Chen",
            content="Had coffee with Sam Chen to discuss Memora pitch deck",
            properties={"event_date": "2026-02-27", "location": None,
                        "participants": ["Sam Chen"], "event_type": "meeting"},
            confidence=0.95,
            networks=["PROFESSIONAL", "VENTURES"],
            temporal=TemporalAnchor(occurred_at="2026-02-27", temporal_type="past")
        ),
        NodeProposal(
            temp_id="temp_2",
            node_type="COMMITMENT",
            title="Sam intro to investor",
            content="Sam Chen promised to introduce me to his investor",
            properties={"due_date": "2026-03-06", "status": "open",
                        "committed_by": "Sam Chen", "committed_to": "user",
                        "priority": "high"},
            confidence=0.92,
            networks=["VENTURES"],
            temporal=TemporalAnchor(due_at="2026-03-06", temporal_type="future")
        ),
        NodeProposal(
            temp_id="temp_3",
            node_type="NOTE",
            title="Sam's feedback on pitch deck",
            content="Sam thinks we should emphasize the graph differentiation more",
            properties={"source_context": "coffee meeting 2026-02-27",
                        "note_type": "observation"},
            confidence=0.90,
            networks=["VENTURES"],
            temporal=None
        )
    ],

    nodes_to_update=[
        # If "Sam Chen" already exists in the graph, update last_interaction
        NodeUpdate(
            node_id="existing-sam-chen-uuid",
            updates={"last_interaction": "2026-02-27"},
            confidence=0.95,
            reason="Met with user today"
        )
    ],

    edges_to_create=[
        # Sam Chen was at the coffee meeting
        EdgeProposal(source_id="existing-sam-chen-uuid", target_id="temp_1",
                     edge_type="PARTICIPATED_IN", edge_category="SOCIAL",
                     confidence=0.95, bidirectional=False, properties={}),

        # The commitment came from the meeting
        EdgeProposal(source_id="temp_1", target_id="temp_2",
                     edge_type="TRIGGERED", edge_category="TEMPORAL",
                     confidence=0.90, bidirectional=False, properties={}),

        # Sam committed to the intro
        EdgeProposal(source_id="existing-sam-chen-uuid", target_id="temp_2",
                     edge_type="COMMITTED_TO", edge_category="PERSONAL",
                     confidence=0.92, bidirectional=False, properties={}),

        # The note relates to the Memora project
        EdgeProposal(source_id="temp_3", target_id="existing-memora-project-uuid",
                     edge_type="RELATED_TO", edge_category="ASSOCIATIVE",
                     confidence=0.88, bidirectional=False, properties={}),

        # The note came from the meeting
        EdgeProposal(source_id="temp_3", target_id="temp_1",
                     edge_type="DERIVED_FROM", edge_category="PROVENANCE",
                     confidence=0.95, bidirectional=False, properties={})
    ],

    edges_to_update=[],

    network_assignments=[
        NetworkAssignment(node_id="temp_1", network="PROFESSIONAL", confidence=0.85),
        NetworkAssignment(node_id="temp_1", network="VENTURES", confidence=0.90),
        NetworkAssignment(node_id="temp_2", network="VENTURES", confidence=0.95),
        NetworkAssignment(node_id="temp_3", network="VENTURES", confidence=0.90),
    ]
)
```

**CSC148 students — notice what just happened:**

From a single paragraph of natural language, the Archivist extracted:
- **3 new nodes** (an EVENT, a COMMITMENT, and a NOTE)
- **1 node update** (Sam Chen's last interaction date)
- **5 new edges** (connecting everything together with typed relationships)
- **4 network assignments** (placing nodes in the right life domains)

All of this is validated against the Pydantic schema. If the Archivist tries to create an edge type that doesn't exist, or assigns a node to a network that's not one of the 7 defined networks, the validation fails and the proposal is rejected. This is how the system prevents hallucinated graph structure.

**Why Pydantic and not just raw JSON?**

```python
# Without Pydantic — anything goes:
{"node_type": "BLORP", "confidence": 999, "networks": ["IMAGINARY"]}
# This would silently corrupt the graph

# With Pydantic — validated at creation time:
NodeProposal(node_type="BLORP", ...)
# Raises: ValidationError - "BLORP" is not a valid NodeType
```

**CSC148 connection:** This is the precondition/representation invariant concept. Pydantic enforces that every object in the system satisfies its representation invariant — a node's confidence must be between 0 and 1, its type must be one of the 12 defined types, etc.

### 4.6 Stage 4: Entity Resolution — The Hardest Problem

**The problem:** The user typed "Sam Chen." But is this the same "Sam" they mentioned yesterday? Last week? Or is it a different Sam?

This is called **entity resolution** — determining whether a newly extracted entity refers to an existing node in the graph or is genuinely new.

**Why it's hard:** People are sloppy. You might say "Sam," "Sam Chen," "Samuel," "Chen," or even just "he" in different captures. The system needs to figure out these all refer to the same person.

Memora uses a **multi-signal approach** — it considers 6 different signals and combines them:

```python
class EntityResolver:
    """
    Resolves whether a proposed entity matches an existing node.

    CSC148 connection: This is essentially a weighted scoring algorithm.
    Each signal contributes a score, and we combine them.
    """

    # Signal weights
    WEIGHTS = {
        "exact_name_match": 0.95,
        "embedding_similarity": 0.80,
        "same_context_network": 0.15,
        "temporal_proximity": 0.10,
        "shared_relationships": 0.20,
        "llm_adjudication": 0.90,
    }

    def resolve(self, proposed_node: NodeProposal,
                candidates: list[BaseNode]) -> ResolutionResult:
        """
        Compare proposed node against candidate existing nodes.

        Returns the best match (if any) with a confidence score.
        """
        best_match = None
        best_score = 0.0

        for candidate in candidates:
            score = 0.0
            signals_used = 0

            # Signal 1: Exact name match (O(1) — string comparison)
            if self._names_match(proposed_node, candidate):
                score += self.WEIGHTS["exact_name_match"]
                signals_used += 1

            # Signal 2: Embedding similarity (O(1) — cosine of pre-computed vectors)
            similarity = self._cosine_similarity(
                proposed_node.embedding, candidate.embedding
            )
            if similarity > 0.92:
                score += self.WEIGHTS["embedding_similarity"] * similarity
                signals_used += 1

            # Signal 3: Same context network (O(1) — set intersection)
            if set(proposed_node.networks) & set(candidate.networks):
                score += self.WEIGHTS["same_context_network"]
                signals_used += 1

            # Signal 4: Temporal proximity (within 7-day window)
            if self._within_temporal_window(proposed_node, candidate, days=7):
                score += self.WEIGHTS["temporal_proximity"]
                signals_used += 1

            # Signal 5: Shared relationships (check if connected to same nodes)
            shared = self._count_shared_relationships(proposed_node, candidate)
            if shared > 0:
                score += self.WEIGHTS["shared_relationships"] * min(shared / 3, 1.0)
                signals_used += 1

            # Normalize by signals used
            if signals_used > 0:
                score = score / signals_used

            if score > best_score:
                best_score = score
                best_match = candidate

        # Determine outcome
        if best_score >= 0.85:
            return ResolutionResult("merge", best_match, best_score)
        elif best_score >= 0.60:
            return ResolutionResult("defer", best_match, best_score)  # human review
        else:
            return ResolutionResult("create", None, best_score)  # new node

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """
        Cosine similarity between two vectors.

        CSC148 connection: This is just the dot product divided by
        the product of magnitudes. O(d) where d is vector dimension (1024).

        cos(θ) = (A · B) / (||A|| × ||B||)
        """
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = sum(a ** 2 for a in vec_a) ** 0.5
        magnitude_b = sum(b ** 2 for b in vec_b) ** 0.5
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        return dot_product / (magnitude_a * magnitude_b)
```

**Four possible outcomes:**

| Outcome | When | What Happens |
|---|---|---|
| **Merge** | Score ≥ 0.85 | Two nodes confirmed as same entity. Merge properties, keep all edges |
| **Create** | Score < 0.60 | No match found. Create a new node |
| **Link** | Entities related but distinct | Create an edge between them (e.g., "Sam the investor" and "Sam the friend" might be different people) |
| **Defer** | Score 0.60–0.85 | Ambiguous. Flag for human review with both candidates shown |

**CSC148 connection:** This is fundamentally a **searching and scoring** problem. You're searching a collection of candidates and scoring each one, then selecting the best match — like finding the closest item in a collection. The twist is that the "distance metric" combines multiple signals with different weights.

### 4.7 Stages 5-6: Proposal Assembly and Validation Gate

**Stage 5** packages everything from Stages 3–4 into a single `GraphProposal` — an atomic, reviewable, reversible set of changes. Think of it as a **git commit for your knowledge graph**. You can see exactly what changed, why, and undo it if needed.

**Stage 6** routes the proposal based on confidence:

```python
def route_proposal(proposal: GraphProposal) -> str:
    """
    Route a proposal to the appropriate review path.

    CSC148 connection: This is a simple decision tree / conditional routing.
    """
    # High-impact changes always need explicit review
    if proposal.has_deletions() or proposal.has_merges():
        return "explicit_confirm"

    # High confidence → auto-approve
    if proposal.confidence >= 0.85:
        return "auto_approve"

    # Medium confidence → batch into daily digest
    if proposal.confidence >= 0.60:
        return "daily_digest"

    # Low confidence → explicit review
    return "explicit_confirm"
```

**Why auto-approve at 0.85?** Research by Baumeister et al. shows that decision quality degrades after ~35 micro-decisions per day ("decision fatigue"). If every capture required manual approval, you'd burn out and stop using the system. Auto-approve at ≥85% confidence means most routine captures flow through silently, while the daily review digest catches the ~5% of errors.

### 4.8 Stages 7-9: Commit and Post-Processing

**Stage 7** (Human Review): Depending on routing:
- **Auto-approved**: Committed silently, shown in tomorrow's daily digest for retrospective correction
- **Digest-routed**: Batched into your morning review
- **Explicit-confirm**: Shown immediately with full context

**Stage 8** (Graph Commit): An **atomic transaction** — all changes succeed or all fail. No partial commits.

```python
def commit_proposal(proposal: GraphProposal, graph_db: GraphDB) -> bool:
    """
    Atomically commit a graph proposal.

    CSC148 connection: This is the concept of atomicity —
    either ALL operations succeed, or NONE do.
    Similar to how you'd implement a multi-step operation
    that must not leave data in an inconsistent state.
    """
    transaction = graph_db.begin_transaction()

    try:
        # 1. Create all new nodes
        node_id_map = {}  # temp_id -> real UUID
        for node in proposal.nodes_to_create:
            real_id = transaction.create_node(node)
            node_id_map[node.temp_id] = real_id

        # 2. Update existing nodes
        for update in proposal.nodes_to_update:
            transaction.update_node(update.node_id, update.updates)

        # 3. Create edges (resolve temp_ids to real UUIDs)
        for edge in proposal.edges_to_create:
            source = node_id_map.get(edge.source_id, edge.source_id)
            target = node_id_map.get(edge.target_id, edge.target_id)
            transaction.create_edge(source, target, edge)

        # 4. Update existing edges
        for update in proposal.edges_to_update:
            transaction.update_edge(update.edge_id, update.updates)

        # 5. Log provenance (audit trail)
        transaction.log_provenance(proposal)

        # 6. Commit — all or nothing
        transaction.commit()
        return True

    except Exception:
        transaction.rollback()  # undo everything
        return False
```

**Stage 9** (Post-Commit Processing): After successful commit, several async processes fire:

1. **Embedding generation**: BGE-M3 converts new node content into 1024-dimensional vectors, stored in LanceDB
2. **Bridge discovery**: New node's embedding is compared against nodes in *other* networks via HNSW index
3. **Network health recalculation**: If the new data affects commitment counts or alerts, health status is updated
4. **Notification triggers**: Check if any notification rules fire (deadline approaching, relationship decay, etc.)
5. **Truth Layer cross-reference**: If the committed data contains claims that intersect with verified facts, flag contradictions

---

## Part 5: The AI Agent System — Three Agents, One Council

### 5.1 Why Agents?

In CSC148, when you write a program, it does exactly what you tell it. An **AI agent** is different — it's given a goal, a set of tools, and context, and it figures out how to accomplish the goal on its own.

Memora has three specialized agents and one orchestrator:

```
                    ┌─────────────────┐
                    │   Orchestrator   │
                    │   (LangGraph)    │
                    └─────┬───────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Archivist│ │Strategist│ │Researcher│
        │ (Haiku)  │ │ (Sonnet) │ │ (Sonnet) │
        └──────────┘ └──────────┘ └──────────┘
        Writes to      Reads from    Bridges to
        the graph      the graph     the internet
```

### 5.2 Why Three Agents and Not One?

You might wonder: why not just have one AI that does everything?

Research from Google DeepMind (December 2025) showed that in multi-agent systems:
- Independent agents **amplify errors by 17.2x** compared to single agents
- Accuracy **saturates at 4–5 agents** (more doesn't help)
- Single agents with better tools are strictly superior for sequential reasoning
- The optimal topology is a **graph-mesh** (agents can communicate), not an unstructured "bag of agents"

So Memora uses exactly 3 agents, each with a clear, non-overlapping role:

| Agent | Role | Model | Frequency | Analogy |
|---|---|---|---|---|
| **Archivist** | Writes to the graph | Claude Haiku | Every capture (10+/day) | A librarian who catalogs every new book |
| **Strategist** | Reads and analyzes the graph | Claude Sonnet | Daily + on-demand | An intelligence analyst who spots patterns |
| **Researcher** | Bridges graph to internet | Claude Sonnet | On-demand | A research assistant who checks external facts |

### 5.3 The Archivist — Deep Dive

The Archivist is the workhorse. It runs on **every single capture** — the highest-frequency agent by far.

**Why Haiku (the smaller model)?**
- It runs 10+ times per day
- Its output is **constrained** by Pydantic schemas — it can only produce valid graph operations
- Speed matters more than deep reasoning for extraction
- With prompt caching (explained below), it's extremely cheap

**Prompt Caching — The Cost Trick:**

The Archivist's prompt has 5 components:

```
Components 1-4 (STATIC — identical every time):
  - Graph schema definition (~1000 tokens)
  - Network definitions (~500 tokens)
  - Extraction rules (~500 tokens)
  - Output format / Pydantic schema (~500 tokens)
  Total: ~2,500 tokens → CACHED at 0.1x cost

Component 5 (DYNAMIC — changes every time):
  - Recent nodes from RAG (~500-1000 tokens)
  - User's actual capture (~100-500 tokens)
  Total: ~1,000 tokens → Full cost
```

Anthropic's API caches the static prefix of prompts. Since 70% of the Archivist's prompt is identical across calls, you pay 0.1x for that portion. **Net result: 60-70% cost reduction.**

**CSC148 connection:** This is conceptually like memoization. Instead of recomputing the same result every time, you cache it. The difference is that here we're caching at the API level (the LLM provider caches the static prefix of the prompt).

### 5.4 The Strategist — Deep Dive

The Strategist is the intelligence analyst. It doesn't write to the graph — it reads it and generates insights.

**Daily briefing generation:**

Every morning, the Strategist receives pre-computed metrics from the Core Engine (health scores, bridge discoveries, overdue commitments, SM-2 items) and synthesizes them into a human-readable intelligence report.

**On-demand analysis:**

When you ask "Should I follow up with Sam about the investor intro?", the Strategist:

1. Queries the graph for all nodes related to Sam Chen
2. Checks Sam's commitment history (has he followed through before?)
3. Looks at your Ventures network health
4. Checks if the commitment is approaching its due date
5. Consults the Truth Layer for any verified facts about the investor
6. Generates a recommendation with citations

**Critic mode:**

This is unique. You can ask the Strategist to deliberately **challenge** your thinking:

> You: "I'm planning to take the job offer from Company X."
> Strategist (Critic mode): "Your graph shows 3 open commitments in your Ventures network that conflict with a full-time role. Your Social network health would drop — you've mentioned wanting to spend more time with family. Also, the last time you switched jobs (Event: 2025-06-15), your stress mentions increased 3x for 2 months. Are you sure about the timing?"

### 5.5 The Researcher — Deep Dive

The Researcher bridges your private graph with the public internet. When the Strategist (or you) needs external information, the Researcher searches the web, academic databases, and code repositories.

**Tools available (via MCP servers):**

| Tool | What It Does | Rate Limit |
|---|---|---|
| Google Search | Web search | 100 free queries/day |
| Brave Search | Fallback web search | 2,000 free/month |
| Playwright | Full web page scraping | On-demand |
| Semantic Scholar + arXiv | Academic paper search | On-demand |
| GitHub MCP | Code and repo search | On-demand |
| Graph + Vector DB | Query Memora's own graph | Unlimited |

**Critical constraint — Privacy:**

The Researcher must **anonymize** all queries before sending them to external services. It cannot leak your personal information to Google.

```python
# BAD — leaks personal info:
google_search("Sam Chen investor introduction for my startup Memora")

# GOOD — anonymized:
google_search("angel investor introduction etiquette startup fundraising 2026")
```

### 5.6 The Council Decision Pattern

When you ask a high-stakes question, the Orchestrator invokes the full Council:

**Step-by-step for "Should I take this job offer?":**

1. **Decomposition** — The Orchestrator breaks this into sub-queries:
   - Archivist sub-query: "What is the user's current professional context, commitments, and financial situation?"
   - Strategist sub-query: "What cross-network impacts would this decision have? What's the risk profile?"
   - Researcher sub-query: "What are current market conditions for this role? Company reputation? Glassdoor data?"

2. **Independent Analysis** — All three agents work **in parallel** on their sub-queries

3. **Proposal Submission** — Each agent submits:
   - An answer
   - A confidence score (0–1)
   - Evidence (graph nodes + facts cited)
   - Risks identified

4. **Deliberation** (optional, max 2–3 rounds) — For high-stakes queries, agents review each other's proposals and look for contradictions

5. **Synthesis** — The Orchestrator performs confidence-weighted aggregation. If agents strongly disagree, the disagreement is flagged for you to resolve

**CSC148 connection:** This is like a **divide-and-conquer** algorithm. Break the problem into sub-problems, solve them independently, then merge the results. The twist is that the "sub-problems" are solved by different agents with different specialties.

---

## Part 6: Vector Embeddings and Semantic Search

### 6.1 What Is an Embedding?

This is probably a new concept for CSC148 students, so let me explain from scratch.

An **embedding** is a way to convert text into a list of numbers (a vector) such that **semantically similar text produces similar vectors**.

```python
# Conceptual example (real embeddings have 1024 dimensions)

embed("I feel stressed about my midterm")     → [0.8, 0.2, -0.5, 0.9, ...]
embed("I'm anxious about my exam")            → [0.79, 0.21, -0.48, 0.88, ...]
embed("I had pizza for lunch")                → [-0.1, 0.7, 0.3, -0.2, ...]
```

Notice that the first two sentences — which mean similar things — produce similar vectors. The third sentence, which is about something completely different, produces a very different vector.

**Why does this matter?** It enables **semantic search** — finding information based on meaning rather than exact keywords.

```python
# Keyword search (traditional):
search("stressed") → only finds documents containing the word "stressed"

# Semantic search (embedding-based):
search("stressed") → finds documents about stress, anxiety, pressure,
                      overwork, burnout — even if they don't use the
                      word "stressed"
```

### 6.2 How Embeddings Work in Memora

Memora uses the **BGE-M3** model to generate embeddings. This model:
- Runs **locally** on your machine (no API cost)
- Produces **1024-dimensional** dense vectors
- Also produces **sparse vectors** (for keyword-style matching)
- Supports **100+ languages**

Every node in the graph gets an embedding stored in LanceDB:

```python
# When a new node is committed:
node_content = "Sam Chen promised to introduce me to his investor"
embedding = bge_m3_model.encode(node_content)  # → list of 1024 floats

# Store in LanceDB
vector_store.add({
    "node_id": node.id,
    "content": node_content,
    "dense": embedding,          # 1024-dim float vector
    "node_type": "COMMITMENT",
    "networks": ["VENTURES"]
})
```

### 6.3 Cosine Similarity — The Math

To find similar nodes, we compute **cosine similarity** between vectors:

```
cos(θ) = (A · B) / (||A|| × ||B||)
```

In Python (from our CSC148 foundation):

```python
import math

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.

    Returns a value between -1 and 1:
      1.0  = identical direction (very similar)
      0.0  = orthogonal (unrelated)
     -1.0  = opposite direction (very dissimilar)

    Time complexity: O(d) where d = len(a) = len(b)
    For BGE-M3: d = 1024, so this is O(1024) ≈ O(1)
    """
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))

    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)
```

**CSC148 connection:** This is just arithmetic on lists. The dot product is a loop over two lists, computing element-wise products and summing. You've done this kind of list processing many times in CSC148.

### 6.4 HNSW Index — Why Search Is O(log N)

If you have 10,000 nodes and want to find the 10 most similar ones, the naive approach is:

```python
# Naive: compute similarity against ALL nodes
# Time: O(N × d) where N = 10,000 and d = 1024
similarities = [(cosine_similarity(query_vec, node.embedding), node)
                for node in all_nodes]
top_10 = sorted(similarities, reverse=True)[:10]
```

This is O(N) — too slow at scale. Instead, LanceDB uses an **HNSW (Hierarchical Navigable Small World)** index that achieves approximate nearest neighbor search in **O(log N)** time.

**How HNSW works (simplified):**

Imagine your nodes arranged in multiple layers:
- Top layer: a few "hub" nodes connected to each other
- Each lower layer: more nodes, more connections
- Bottom layer: all nodes

To find nearest neighbors, you start at the top layer, find the closest hub, then "zoom in" to each lower layer, always following the closest connection. It's like using a map — first find the right country, then the right city, then the right street.

```
Layer 3:    [A] ---- [B]                     ← few nodes, coarse navigation
Layer 2:    [A] - [C] - [B] - [D]           ← more nodes
Layer 1:    [A]-[E]-[C]-[F]-[B]-[G]-[D]     ← most nodes
Layer 0:    [A][E][H][C][I][F][J][B][K][G][L][D]  ← all nodes
```

**CSC148 connection:** This is conceptually similar to a **balanced BST** or a **skip list** — data structures that achieve O(log N) search by organizing data in layers of increasing granularity. The difference is that HNSW operates in high-dimensional vector space instead of 1D.

### 6.5 Hybrid Search: Combining Dense and Sparse

Memora uses **hybrid search** — combining two types of retrieval:

1. **Dense search** (semantic): Uses BGE-M3 embeddings + cosine similarity. Good at finding conceptually similar content even with different words.

2. **Sparse search** (keyword/BM25): Uses sparse vectors that represent term frequency. Good at finding exact term matches.

Results are combined using **Reciprocal Rank Fusion (RRF)**:

```python
def reciprocal_rank_fusion(dense_results: list, sparse_results: list,
                            k: int = 60) -> list:
    """
    Combine dense and sparse search results.

    For each result, its fused score is:
      score = 1 / (k + rank_in_dense) + 1 / (k + rank_in_sparse)

    Higher fused score = better match.

    CSC148 connection: This is just a scoring algorithm over
    two sorted lists, producing a merged sorted list.
    """
    scores = {}

    for rank, (node_id, _) in enumerate(dense_results):
        scores[node_id] = scores.get(node_id, 0) + 1 / (k + rank + 1)

    for rank, (node_id, _) in enumerate(sparse_results):
        scores[node_id] = scores.get(node_id, 0) + 1 / (k + rank + 1)

    # Sort by fused score, descending
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

**Why hybrid?** Dense search understands meaning but can miss exact terms. Sparse search catches exact keywords but misses synonyms. Together, they get the best of both worlds.

---

## Part 7: The Adaptive RAG Pipeline — How Queries Are Answered

### 7.1 What Is RAG?

**RAG (Retrieval-Augmented Generation)** is a pattern where, before asking an LLM to answer a question, you first **retrieve relevant information** and include it in the prompt.

Without RAG:
```
User: "When did I meet Sam?"
LLM: "I don't know — I don't have access to your personal data." ← useless
```

With RAG:
```
1. Search graph for nodes related to "Sam" and "meeting"
2. Find: EVENT("Coffee meeting with Sam Chen", date: 2026-02-27)
3. Include this in the prompt:
   "Based on the following context:
    - EVENT: Coffee meeting with Sam Chen on 2026-02-27
    Answer the user's question: When did I meet Sam?"
4. LLM: "You met Sam on February 27, 2026, for a coffee meeting." ← useful!
```

### 7.2 Why "Adaptive"?

Not all queries need the same retrieval strategy. Memora classifies queries into four types and routes them differently:

```python
def classify_query(query: str) -> str:
    """
    Classify a query to determine retrieval strategy.

    CSC148 connection: This is pattern matching / classification.
    """
    # Simple factual — can be answered by a single node
    if is_factual_lookup(query):
        return "simple"         # → vector search only

    # Relationship — needs to traverse edges
    if involves_relationships(query):
        return "relationship"   # → graph traversal + vector

    # Cross-network — needs to look across multiple networks
    if spans_domains(query):
        return "cross_network"  # → multi-network graph walk

    # Complex decision — needs multiple agents
    return "complex"            # → full council deliberation
```

**Examples for each type:**

| Query | Type | Strategy | Why |
|---|---|---|---|
| "When did I meet Sam?" | Simple | Vector search finds the EVENT node | One node answers it |
| "Who introduced me to the VC?" | Relationship | Traverse INTRODUCED_BY edges from the VC node | Need to follow edges |
| "How is my health affecting my work?" | Cross-network | Walk bridges between Health and Professional networks | Spans two domains |
| "Should I take this job offer?" | Complex | Full council — Archivist for context, Strategist for analysis, Researcher for market data | Multi-factor decision |

### 7.3 CRAG — Corrective RAG

What if the retrieval step finds poor results? Maybe the query is about something not in your graph yet.

**CRAG (Corrective RAG)** detects poor retrieval quality and falls back to the Researcher agent for web search:

```python
def crag_quality_check(results: list[SearchResult], threshold: float = 0.5) -> bool:
    """
    Check if retrieval results are sufficient.

    Returns True if quality is good enough, False if we need web fallback.

    CSC148 connection: Simple threshold check on a quality metric.
    """
    if not results:
        return False

    # Check if top result is relevant enough
    if results[0].relevance_score < threshold:
        return False

    # Check if we have enough results
    if len(results) < 3:
        return False

    return True
```

If CRAG determines the retrieval is poor, the Researcher agent searches the web, finds relevant information, deposits it into the Truth Layer, and the pipeline continues with this enriched context.

This is how Memora seamlessly blends your private knowledge graph with public internet information.

### 7.4 Graph-Augmented Context Expansion

After finding relevant nodes via hybrid search, Memora **expands** the results by including neighboring nodes (1-hop BFS):

```python
def expand_context(seed_nodes: list[str], graph: KnowledgeGraph,
                   max_hops: int = 1) -> list[str]:
    """
    Expand seed nodes to include 1-hop neighbors.

    CSC148 connection: This is literally BFS with a depth limit!
    You learned this exact algorithm in CSC148.
    """
    expanded = set(seed_nodes)
    frontier = list(seed_nodes)

    for hop in range(max_hops):
        next_frontier = []
        for node_id in frontier:
            neighbors = graph.get_neighbors(node_id)
            for neighbor_id in neighbors:
                if neighbor_id not in expanded:
                    expanded.add(neighbor_id)
                    next_frontier.append(neighbor_id)
        frontier = next_frontier

    return list(expanded)
```

**Why expand?** If you search for "Sam" and find the PERSON node, expanding to 1-hop includes:
- All of Sam's commitments to you
- Events where Sam was present
- Projects Sam is involved in
- Other people connected to Sam

This gives the LLM much richer context for generating a useful answer.

---

## Part 8: Background Mechanics — The Living Graph Engine

### 8.1 What Makes the Graph "Living"?

A traditional note-taking app is a **static** document store — you put notes in, they sit there forever, unchanged. Memora's graph is a **living system** that evolves on its own through deterministic algorithms running on schedule.

These algorithms are the "engine room" of Memora. They are:
- **Deterministic** — no AI, no randomness, same input always produces same output
- **LLM-independent** — they work even if the AI layer is completely removed
- **Scheduled** — they run automatically at defined intervals

This is a critical architectural point: the Core Engine layer is what makes Memora NOT an LLM wrapper. If Anthropic shut off the Claude API tomorrow, the graph, the decay mechanics, the health scores, the bridge discovery, the spaced repetition — all of it would still work.

### 8.2 Decay Scoring — Knowledge Fading

**The idea:** Just like human memory, information in the graph should fade if you don't revisit it. The decay function is exponential:

```
decay_score(t) = e^(-λ · (t_now - t_last_access))
```

Let's unpack this with Python:

```python
import math
from datetime import datetime, timedelta

def compute_decay_score(last_accessed: datetime,
                         now: datetime,
                         decay_constant: float = 0.05) -> float:
    """
    Compute the decay score for a node.

    Args:
        last_accessed: when the node was last referenced
        now: current time
        decay_constant: lambda — how fast knowledge decays
                        (configurable per network)

    Returns:
        Float between 0 and 1:
          1.0 = just accessed (perfectly fresh)
          0.0 = hasn't been accessed in a very long time

    CSC148 connection: This is just evaluating a mathematical function.
    The exponential function e^(-x) approaches 0 as x grows —
    you might have seen this in MAT102/MAT137.
    """
    delta_days = (now - last_accessed).total_seconds() / 86400  # convert to days
    return math.exp(-decay_constant * delta_days)


# Example:
now = datetime(2026, 2, 27)

# Accessed yesterday → very fresh
score_1 = compute_decay_score(datetime(2026, 2, 26), now)
# = e^(-0.05 * 1) = 0.951

# Accessed a week ago → still fresh
score_7 = compute_decay_score(datetime(2026, 2, 20), now)
# = e^(-0.05 * 7) = 0.705

# Accessed a month ago → fading
score_30 = compute_decay_score(datetime(2026, 1, 28), now)
# = e^(-0.05 * 30) = 0.223

# Accessed 3 months ago → nearly forgotten
score_90 = compute_decay_score(datetime(2025, 11, 29), now)
# = e^(-0.05 * 90) = 0.011
```

**What happens to low-decay nodes?**
- They get surfaced in spaced repetition ("You haven't thought about this in 30 days — still relevant?")
- They get lower weight in search results (fresh knowledge is prioritized)
- Eventually, they become archival candidates

**Lambda (λ) is configurable per network:** Academic knowledge (concepts you're studying) might have a slower decay rate (you should remember theory for longer), while Social network interactions (who you talked to at a party) might decay faster.

**CSC148 complexity:** Computing decay for all N nodes is **O(N)**, run once daily.

### 8.3 Bridge Discovery — Finding Hidden Connections

This is the most valuable algorithm in the system. Bridge discovery finds **connections between nodes in different networks** that you'd never notice on your own.

**How it works:**

1. **Per-capture (incremental):** When a new node is committed, compare its embedding against nodes in *other* networks:

```python
def discover_bridges_incremental(new_node: BaseNode,
                                  vector_store: VectorStore) -> list[Bridge]:
    """
    Find potential cross-network bridges for a newly committed node.

    CSC148 connection: This is a nearest-neighbor search with filtering.
    We search for similar nodes but EXCLUDE nodes in the same network.

    Time complexity: O(log N) per network — HNSW index lookup
    """
    bridges = []

    for network in ALL_NETWORKS:
        # Skip the node's own networks
        if network in new_node.networks:
            continue

        # Find similar nodes in OTHER networks
        similar_nodes = vector_store.search(
            query_vector=new_node.embedding,
            filter={"networks": network},
            top_k=5,
            min_similarity=0.75
        )

        for match in similar_nodes:
            bridges.append(Bridge(
                source_node_id=new_node.id,
                target_node_id=match.node_id,
                source_network=new_node.networks[0],
                target_network=network,
                similarity=match.similarity
            ))

    return bridges
```

2. **Daily batch:** Once a day, scan all nodes modified in the last 24 hours for potential bridges. Batch the candidates into a **single LLM call** for validation:

```python
# Instead of 15 individual LLM calls:
# "Is this a meaningful connection?" × 15

# We make 1 call:
# "Here are 15 potential connections. For each, tell me if it's meaningful
#  and why. Respond as JSON."
```

**Real example:** You mention stress twice this week (Health network). You have 4 open commitments past due (Professional network). Bridge discovery finds high embedding similarity between the stress mentions and the overdue commitment nodes. The daily batch LLM validates: "Yes, this is meaningful — stress correlates with professional overcommitment." → A BRIDGES edge is created.

The Strategist then surfaces this in your briefing: "You're stressed because you're overextended. The commitment from Sam is stale — he missed his last two promises. Consider deprioritizing the venture with Sam and focusing on your 3 remaining professional commitments."

No single-domain tool could ever make this connection.

### 8.4 Spaced Repetition (SM-2)

The SM-2 algorithm is used in flashcard apps like Anki. Memora applies it to knowledge graph nodes to fight the "67% of notes never revisited" problem.

```python
def sm2_update(easiness_factor: float,
               repetition_number: int,
               interval: int,
               quality: int) -> tuple[float, int, int]:
    """
    SM-2 spaced repetition algorithm.

    Args:
        easiness_factor: how easy this item is to recall (min 1.3)
        repetition_number: how many times reviewed successfully
        interval: current interval in days
        quality: user's recall quality rating (0-5)
                 0 = complete blackout
                 3 = correct with difficulty
                 5 = perfect recall

    Returns:
        (new_easiness_factor, new_repetition_number, new_interval)

    CSC148 connection: This is just a function that updates state
    based on input. It's essentially a state machine:
    quality >= 3 → advance (longer interval)
    quality < 3  → reset (start over)
    """
    if quality >= 3:
        # Successful recall → increase interval
        if repetition_number == 0:
            new_interval = 1
        elif repetition_number == 1:
            new_interval = 6
        else:
            new_interval = round(interval * easiness_factor)

        new_repetition = repetition_number + 1
    else:
        # Failed recall → reset
        new_interval = 1
        new_repetition = 0

    # Update easiness factor
    new_ef = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(1.3, new_ef)

    return new_ef, new_repetition, new_interval


# Example: First review of a CONCEPT node
ef, rep, interval = sm2_update(
    easiness_factor=2.5,
    repetition_number=0,
    interval=0,
    quality=4  # recalled correctly
)
# ef=2.5, rep=1, interval=1 → review again tomorrow

# Second review, recalled well
ef, rep, interval = sm2_update(ef, rep, interval, quality=4)
# ef=2.5, rep=2, interval=6 → review in 6 days

# Third review, still good
ef, rep, interval = sm2_update(ef, rep, interval, quality=5)
# ef=2.6, rep=3, interval=16 → review in 16 days
```

### 8.5 Network Health Scoring

Every 6 hours, Memora computes health status for each of the 7 networks:

```python
def compute_network_health(network: str, graph: KnowledgeGraph) -> HealthStatus:
    """
    Compute health status for a context network.

    CSC148 connection: This is a weighted scoring algorithm
    that combines multiple metrics into a single status.
    """
    # 1. Commitment completion rate
    commitments = graph.get_nodes(type="COMMITMENT", network=network)
    open_count = sum(1 for c in commitments if c.status == "open")
    overdue_count = sum(1 for c in commitments if c.status == "overdue")
    completed_count = sum(1 for c in commitments if c.status == "completed")
    total = open_count + overdue_count + completed_count

    if total > 0:
        completion_rate = completed_count / total
    else:
        completion_rate = 1.0  # no commitments = fine

    # 2. Alert ratio
    alerts = graph.get_alerts(network=network)
    total_nodes = graph.count_nodes(network=network)
    alert_ratio = len(alerts) / max(total_nodes, 1)

    # 3. Staleness flag
    # Only triggered when commitments exist but haven't been updated
    if open_count > 0:
        most_recent_update = max(c.updated_at for c in commitments if c.status == "open")
        days_since_update = (datetime.now() - most_recent_update).days
        is_stale = days_since_update > 7
    else:
        is_stale = False  # silence is fine when there are no deadlines

    # Determine status
    if overdue_count >= 3 or (is_stale and alert_ratio > 0.3):
        return HealthStatus("falling_behind", momentum="down")
    elif overdue_count >= 1 or alert_ratio > 0.15 or is_stale:
        return HealthStatus("needs_attention", momentum="stable")
    else:
        return HealthStatus("on_track", momentum="up" if completion_rate > 0.8 else "stable")
```

### 8.6 Gap Detection

Weekly, the system scans for structural weaknesses in the graph:

```python
def detect_gaps(graph: KnowledgeGraph) -> list[Gap]:
    """
    Find structural weaknesses in the knowledge graph.

    CSC148 connection: These are all GRAPH ALGORITHMS!
    - Orphaned nodes = nodes with degree 0 (no edges)
    - Stalled goals = nodes with no recent incoming edges of a specific type
    - Dead-end projects = same
    - Isolated concepts = nodes not connected to any practical node type
    """
    gaps = []

    # 1. Orphaned nodes — degree 0
    for node in graph.get_all_nodes():
        if graph.degree(node.id) == 0:
            gaps.append(Gap("orphaned", node.id,
                           f"'{node.title}' has no connections"))

    # 2. Stalled goals — GOAL nodes with no recent PROGRESS edges
    for goal in graph.get_nodes(type="GOAL", status="active"):
        recent_progress = graph.get_edges(
            target=goal.id,
            edge_type="PROGRESS",
            since=datetime.now() - timedelta(days=14)
        )
        if not recent_progress:
            gaps.append(Gap("stalled_goal", goal.id,
                           f"Goal '{goal.title}' has no progress in 14 days"))

    # 3. Dead-end projects
    for project in graph.get_nodes(type="PROJECT", status="active"):
        recent_activity = graph.get_edges(
            source=project.id,
            since=datetime.now() - timedelta(days=14)
        )
        if not recent_activity:
            gaps.append(Gap("dead_end_project", project.id,
                           f"Project '{project.title}' has no activity in 14 days"))

    # 4. Isolated concepts
    for concept in graph.get_nodes(type="CONCEPT"):
        connected_to_practical = any(
            graph.get_node(edge.target_id).node_type in
            ["PROJECT", "GOAL", "COMMITMENT", "DECISION"]
            for edge in graph.get_edges(source=concept.id)
        )
        if not connected_to_practical:
            gaps.append(Gap("isolated_concept", concept.id,
                           f"Concept '{concept.title}' isn't linked to any practical application"))

    return gaps
```

**CSC148 connection:** Gap detection is pure graph analysis. Orphaned nodes = degree-0 vertices. Stalled goals = nodes with no incoming edges of a specific type within a time window. These are exactly the kinds of graph traversal problems you solve in CSC148.

---

## Part 9: The Truth Layer — Fact Verification

### 9.1 Why Facts Need Verification

The graph contains three categories of information with very different reliability:

1. **Things the LLM extracted** — the Archivist inferred "Sam is an investor" from your text. But did you actually say that, or did the LLM misinterpret?

2. **Things the Researcher found online** — "Company X raised $50M in Series B." But is that article from 2024 still accurate in 2026?

3. **Things you self-reported** — "Sam told me the deal closed." But Sam might have been wrong, or you might have misheard.

**The risk:** If the Strategist recommends an action based on a hallucinated LLM inference layered on top of stale web data layered on top of self-reported hearsay, you've made a decision based on fiction.

The Truth Layer prevents this.

### 9.2 Source Confidence Hierarchy

```python
class SourceType:
    """
    CSC148 connection: This is just an ordered enum.
    PRIMARY > SECONDARY > SELF_REPORTED
    """
    PRIMARY = "PRIMARY"           # Official records, government databases, published financials
    SECONDARY = "SECONDARY"       # News articles, research papers, third-party reports
    SELF_REPORTED = "SELF_REPORTED"  # User hearsay ("Sam told me X")
```

| Source Type | Confidence | Examples |
|---|---|---|
| `PRIMARY` | Highest | Official records, government databases, published financials, SEC filings |
| `SECONDARY` | Medium | News articles, research papers, third-party reports (with citation) |
| `SELF_REPORTED` | Lowest | User-stated hearsay ("Sam told me X") — always flagged as such |

### 9.3 The Fact-Check Gate

Before any agent generates a recommendation, it cross-references against the Truth Layer:

```python
def fact_check_gate(claims: list[str], truth_layer: TruthLayer) -> list[FactCheckResult]:
    """
    Cross-reference claims against verified facts.

    CSC148 connection: This is a search/match algorithm over
    a collection of verified facts.
    """
    results = []

    for claim in claims:
        # Search Truth Layer for related facts
        related_facts = truth_layer.search(claim)

        if not related_facts:
            results.append(FactCheckResult(
                claim=claim,
                status="unverified",
                message="No verified facts found — unverified claim"
            ))
        else:
            for fact in related_facts:
                if fact.contradicts(claim):
                    results.append(FactCheckResult(
                        claim=claim,
                        status="contradicted",
                        message=f"Contradicted by {fact.source_type} source: {fact.source_title}",
                        conflicting_fact=fact
                    ))
                else:
                    results.append(FactCheckResult(
                        claim=claim,
                        status="supported",
                        message=f"Supported by {fact.source_type} source: {fact.source_title}",
                        supporting_fact=fact
                    ))

    return results
```

---

## Part 10: The API Layer — How Frontend Talks to Backend

### 10.1 What Is an API?

In CSC148, your programs are self-contained — you call functions directly. In a web application, the frontend (running in your browser) and the backend (running on your computer) are separate programs that communicate over **HTTP**.

An **API (Application Programming Interface)** defines the contract for this communication: what requests the frontend can make, what data it sends, and what the backend responds with.

**Analogy:** Think of the API as a restaurant menu. The frontend (customer) looks at the menu (API docs) and orders (makes a request). The backend (kitchen) prepares the order and sends it back (response). The customer doesn't need to know how the kitchen works internally.

### 10.2 REST Endpoints

Memora's API uses **REST** — a standard pattern where each resource has a URL, and you use HTTP methods (GET, POST, PATCH, DELETE) to interact with it:

```python
# Framework: FastAPI (Python)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


# ─── Captures ───────────────────────────────────

class CaptureCreate(BaseModel):
    """Request body for creating a capture."""
    modality: str       # "text", "voice", "image"
    content: str
    metadata: dict = {}

class CaptureResponse(BaseModel):
    """Response after creating a capture."""
    id: str
    status: str         # "processing", "completed"
    pipeline_stage: str
    created_at: str


@app.post("/api/v1/captures", response_model=CaptureResponse)
async def create_capture(capture: CaptureCreate):
    """
    Create a new capture and start the pipeline.

    CSC148 connection: This is just a function that takes input
    and returns output — but it's triggered by an HTTP request
    instead of a direct function call.
    """
    # 1. Store the raw capture
    record = await capture_store.save(capture)

    # 2. Start the 9-stage pipeline (async — doesn't block)
    await pipeline.start(record.id)

    return CaptureResponse(
        id=record.id,
        status="processing",
        pipeline_stage="preprocessing",
        created_at=record.created_at.isoformat()
    )


@app.get("/api/v1/captures")
async def list_captures(limit: int = 20, offset: int = 0):
    """List captures with pagination."""
    return await capture_store.list(limit=limit, offset=offset)


# ─── Graph ──────────────────────────────────────

@app.get("/api/v1/graph/nodes/{node_id}")
async def get_node(node_id: str):
    """Get a node with all its properties and edges."""
    node = await graph_db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    edges = await graph_db.get_edges(node_id=node_id)
    return {"node": node, "edges": edges}


@app.get("/api/v1/graph/nodes/{node_id}/neighborhood")
async def get_neighborhood(node_id: str, hops: int = 1):
    """
    Get the local subgraph around a node.

    CSC148 connection: This triggers a BFS with depth limit!
    """
    return await graph_db.bfs_neighborhood(node_id, max_hops=hops)


@app.get("/api/v1/graph/search")
async def search_graph(query: str, top_k: int = 10):
    """Hybrid search (BM25 + dense vector fusion)."""
    return await search_engine.hybrid_search(query, top_k=top_k)


# ─── AI Council ─────────────────────────────────

class CouncilQuery(BaseModel):
    query: str
    mode: str = "council"       # "council" or "single_agent"
    include_critique: bool = False

@app.post("/api/v1/council/query")
async def council_query(request: CouncilQuery):
    """Submit a question to the AI Council."""
    # Response streams via WebSocket (see Section 10.3)
    session_id = await orchestrator.start_query(
        query=request.query,
        mode=request.mode,
        include_critique=request.include_critique
    )
    return {"session_id": session_id, "ws_url": f"/api/v1/ws/stream/{session_id}"}
```

### 10.3 WebSocket — Real-Time Streaming

When the AI Council is answering a complex question, you don't want to wait for the entire answer to be generated. You want to see tokens streaming in real-time (like ChatGPT).

**WebSocket** is a protocol that maintains a persistent connection between the browser and the server, allowing the server to push data to the browser at any time.

```python
from fastapi import WebSocket

@app.websocket("/api/v1/ws/stream/{session_id}")
async def stream_council_response(websocket: WebSocket, session_id: str):
    """
    Stream AI Council response token-by-token.

    CSC148 connection: Think of this as an iterator/generator.
    Instead of returning one big response, we yield tokens one at a time.
    """
    await websocket.accept()

    async for token in orchestrator.stream(session_id):
        await websocket.send_json({
            "type": "agent_token",
            "agent": token.agent_name,    # "archivist", "strategist", "researcher"
            "text": token.text,
            "metadata": {
                "confidence": token.confidence,
                "citing_nodes": token.cited_node_ids
            }
        })

    # Send completion signal
    await websocket.send_json({"type": "complete"})
    await websocket.close()
```

---

## Part 11: Putting It All Together — A Full User Flow

Let's trace a complete user interaction through the entire system architecture.

### Scenario: Monday Morning

**7:00 AM — Daily Briefing**

The APScheduler triggers the daily briefing job. Here's the execution path:

```
APScheduler (cron: 7am daily)
  │
  ├── compute_decay_scores()        ← Core Engine (O(N), no LLM)
  ├── compute_network_health()      ← Core Engine (no LLM)
  ├── run_commitment_scan()         ← Core Engine (no LLM)
  ├── run_bridge_discovery_batch()  ← Core Engine (1 LLM call for batch)
  ├── get_sm2_due_items()           ← Core Engine (no LLM)
  │
  ▼
  Strategist Agent (Claude Sonnet)
    Input: all computed metrics above
    Output: formatted daily briefing
  │
  ▼
  Push notification to frontend
```

Your briefing says:
> **Academic**: 🟡 Needs Attention — CSC148 A3 due in 2 days, no study input in 5 days
> **Professional**: 🟢 On Track
> **Ventures**: 🟡 Needs Attention — Sam's investor intro is due Friday, still open
> **Bridge detected**: Your stress mentions (Health) correlate with your 2 overdue academic commitments

**10:30 AM — New Capture**

You type: "Had coffee with Sam Chen today. He promised to introduce me to his investor by next Friday."

Execution path through all 9 pipeline stages:

```
Frontend (React)
  │ POST /api/v1/captures
  ▼
FastAPI Backend
  │
  ├── Stage 1: Store raw capture (O(1))
  ├── Stage 2: Preprocess — normalize dates, detect language (O(n), no LLM)
  ├── Stage 3: Archivist (Claude Haiku) — extract entities & relationships
  │             Input: processed text + RAG context of existing nodes + schema
  │             Output: GraphProposal (3 nodes, 5 edges, 4 network assignments)
  ├── Stage 4: Entity Resolution — "Sam Chen" matches existing node (O(log N))
  ├── Stage 5: Assemble proposal (O(1))
  ├── Stage 6: Validation gate — confidence 0.88 ≥ 0.85 → AUTO-APPROVE
  ├── Stage 7: Auto-approved → logged for daily digest
  ├── Stage 8: Graph commit — atomic transaction
  └── Stage 9: Post-commit
       ├── Generate embeddings (BGE-M3 local, O(1) per node)
       ├── Bridge discovery (HNSW search, O(log N) per network)
       ├── Network health update (O(1))
       ├── Notification check (commitment due Friday → schedule alert for Thursday)
       └── Truth Layer cross-reference (O(log N))
```

**3:00 PM — Complex Query**

You ask: "Should I follow up with Sam about the investor intro, or wait?"

```
Frontend (React)
  │ POST /api/v1/council/query
  ▼
Orchestrator (LangGraph)
  │ Classify: complex decision → full council
  │
  ├── Archivist sub-query (parallel):
  │     "What is user's context with Sam Chen?"
  │     → Reads graph: Sam's commitment history, meeting history,
  │       reliability (has he followed through before?)
  │
  ├── Strategist sub-query (parallel):
  │     "What are the cross-network impacts?"
  │     → Sam's investor intro is in Ventures network
  │     → User's deadline pressure in Academic network
  │     → Bridge: stress (Health) ↔ overdue commitments
  │
  └── Researcher sub-query (parallel):
        "What's the etiquette for following up on intros?"
        → Google Search (anonymized): "angel investor intro followup timing"
        → Deposits findings into Truth Layer
  │
  ▼
Synthesis (confidence-weighted aggregation)
  │
  ▼
Response (streamed via WebSocket):
  "Based on your graph:
   - Sam has a strong track record — he fulfilled 4 of 5 prior commitments
   - The intro is due Friday, so a gentle Thursday follow-up is appropriate
   - However, your Academic network needs attention — CSC148 A3 is due
     Wednesday. Prioritize that first.

   Recommended action: Focus on CSC148 A3 today and tomorrow.
   Send Sam a brief follow-up Thursday morning.

   Sources: [PERSON: Sam Chen] [COMMITMENT: investor intro]
   [COMMITMENT: CSC148 A3] [Verified fact: Follow-up etiquette (SECONDARY)]"
```

---

## Part 12: Anti-Wrapper Positioning — Why This Isn't Just ChatGPT

### 12.1 The Wrapper Problem

Google VP Darren Mowry (February 2026): "Wrapping thin IP around Gemini or GPT-5 is a sign that a startup is not distinguishing itself."

**The test: If your LLM provider shut off your API key, would your product die?**

Memora passes this test. Here's what survives without any LLM:

| Component | LLM required? | What it does without LLM |
|---|---|---|
| Knowledge graph | No | Fully queryable database of your life |
| Decay scoring | No | Nodes still fade based on access patterns |
| Bridge discovery | Partially (batch validation) | Embedding similarity still finds candidates |
| Health scoring | No | Network status still computed from metrics |
| Spaced repetition | No | SM-2 still schedules reviews |
| Truth Layer | No | Verified facts still stored and queryable |
| Entity resolution | Partially (LLM adjudication) | 5 of 6 signals still work |
| Notifications | No | Deadline and staleness alerts still fire |

What you **lose** without an LLM: the Archivist can't extract entities from natural language, the Strategist can't generate briefings, the Researcher can't synthesize web results. But the underlying data structures and algorithms — the actual intelligence — remain.

### 12.2 The Differentiation Stack

Ordered by distance from "commodity LLM wrapper":

1. **Knowledge graph + ontology** — proprietary data structure, can't be replicated by prompting ChatGPT
2. **Truth Layer** — verified fact store with source typing and staleness detection
3. **Bridge discovery** — custom algorithm (embeddings + graph traversal + LLM validation)
4. **Background mechanics** — decay, health scoring, SM-2, gap detection — all deterministic
5. **Entity resolution** — multi-signal scoring with domain-specific weights
6. **Council chat** — this IS the wrapper zone, but mitigated by always citing graph nodes and verified facts

---

## Part 13: Complexity Analysis Summary

For the CSC148-trained reader, here's every algorithm and its time complexity:

| Algorithm | Time Complexity | Space Complexity | Frequency |
|---|---|---|---|
| Content hash dedup | O(1) lookup | O(N) hash table | Per capture |
| Archivist extraction | O(1) API call | O(1) | Per capture |
| Entity resolution (per candidate) | O(d) cosine similarity | O(1) | Per capture |
| HNSW vector search | O(log N) | O(N log N) index | Per capture + per query |
| BFS neighborhood expansion | O(V + E) for subgraph | O(V) visited set | Per query |
| Hybrid search (BM25 + dense) | O(log N) each + O(K) merge | O(K) results | Per query |
| Decay scoring (all nodes) | O(N) | O(1) | Daily |
| Bridge discovery (incremental) | O(7 × log N) ≈ O(log N) | O(K) candidates | Per commit |
| Bridge discovery (batch) | O(M × log N) + O(1) LLM | O(M) modified nodes | Daily |
| Network health scoring | O(C) per network, C = commitments | O(1) | Every 6 hours |
| SM-2 scheduling | O(N) scan for due items | O(1) per item | Daily |
| Gap detection | O(V + E) | O(V) | Weekly |
| Graph commit (atomic) | O(K) where K = proposal size | O(K) | Per proposal |

Where:
- N = total nodes in graph
- E = total edges in graph
- V = vertices in a subgraph
- K = number of results or items
- M = nodes modified in last 24 hours
- C = commitments in a network
- d = embedding dimension (1024)

---

## Part 14: Key Takeaways

### For CSC148 Students

1. **Graphs are everywhere.** The knowledge graph data structure you studied in CSC148 is the foundation of a real product architecture. Nodes, edges, traversal, neighborhoods — it's all the same.

2. **OOP scales.** The class hierarchy (BaseNode → PersonNode, CommitmentNode, etc.) is exactly the inheritance pattern from CSC148, used at production scale with Pydantic validation.

3. **Algorithms matter.** Decay scoring (exponential function), bridge discovery (nearest neighbor search), spaced repetition (SM-2), gap detection (graph traversal) — these are all algorithms you can implement from your CSC148 knowledge.

4. **Complexity analysis is practical.** The reason we use HNSW (O(log N)) instead of brute-force cosine similarity (O(N)) isn't theoretical — it's the difference between 1ms and 10 seconds at 10,000 nodes.

5. **ADTs have real implementations.** The graph "abstract data type" has a concrete implementation: RyuGraph/DuckDB for the graph, LanceDB for vectors, Pydantic for schema validation.

### For Understanding System Architecture

1. **Separation of concerns** — each layer has one job. Change the LLM? Only the Intelligence layer changes. Swap the database? Only the Infrastructure layer changes.

2. **The pipeline pattern** — complex processing broken into 9 stages, each with a single responsibility. Data flows through stages like items on a conveyor belt.

3. **Deterministic vs. non-deterministic** — the Core Engine is deterministic (same input → same output). The AI layer is non-deterministic (LLMs can produce different outputs for the same input). By grounding non-deterministic AI outputs in deterministic algorithms and verified facts, Memora achieves reliability.

4. **Human-in-the-loop** — the system never acts autonomously on high-impact decisions. It proposes, you decide. The auto-approve threshold is a calibrated tradeoff between convenience and control.

5. **Local-first** — everything on your machine, you own your data, zero infrastructure cost. The only external dependency is the LLM API.

---

*End of Lecture — Memora System Architecture*
*Estimated reading time: 60-75 minutes*
