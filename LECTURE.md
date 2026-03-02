# Memora: Building a Personal Knowledge Graph Engine

## A Complete Technical Lecture for CSC148 Students

**Course:** CSC148 — Introduction to Computer Science, University of Toronto Mississauga
**Duration:** 60-75 minutes of reading
**Prerequisites:** Familiarity with Python, basic OOP, elementary data structures

---

## Table of Contents

1. [Part 1: What Are We Building and Why?](#part-1-what-are-we-building-and-why)
2. [Part 2: System Architecture — The Big Picture](#part-2-system-architecture--the-big-picture)
3. [Part 3: The Knowledge Graph — Core Data Structure](#part-3-the-knowledge-graph--core-data-structure)
4. [Part 4: Network Classification](#part-4-network-classification)
5. [Part 5: The 9-Stage Extraction Pipeline](#part-5-the-9-stage-extraction-pipeline)
6. [Part 6: Entity Resolution](#part-6-entity-resolution)
7. [Part 7: The AI Council](#part-7-the-ai-council)
8. [Part 8: The Living Graph Engine](#part-8-the-living-graph-engine)
9. [Part 9: Truth Layer and Verified Facts](#part-9-truth-layer-and-verified-facts)
10. [Part 10: Adaptive RAG Pipeline](#part-10-adaptive-rag-pipeline)
11. [Part 11: Action Engine, Outcomes, and Patterns](#part-11-action-engine-outcomes-and-patterns)
12. [Part 12: Investigation, Timeline, and People Intel](#part-12-investigation-timeline-and-people-intel)
13. [Part 13: The CLI Interface](#part-13-the-cli-interface)
14. [Part 14: Putting It All Together — Full Walkthrough](#part-14-putting-it-all-together--full-walkthrough)

---

## Part 1: What Are We Building and Why?

### The Problem: Life Fragmentation

You are a second-year UTM student. Think about everything that happened in the last month:

- You attended 12 CSC148 lectures and 4 labs
- You had coffee with three different friends, each time discussing different side projects
- You promised your study group partner Sam you would review their A2 code by Friday
- You read four articles about graph databases for your independent study
- You decided to skip the campus hackathon to focus on midterms
- Your manager at your part-time job mentioned a Python project you might contribute to

Where does all of this live? Some is in your head, some in scattered notes, some in text messages. The **connections** between these fragments — the fact that your manager's Python project uses graph algorithms you just learned in CSC148, or that your friend Sarah is also interested in the hackathon you decided to skip — are invisible.

**Memora** is a personal knowledge graph engine that captures these fragments, extracts their structure, discovers hidden connections, and helps you navigate your life as an interconnected system rather than isolated pieces.

### The Palantir Analogy

Palantir Technologies builds intelligence analysis platforms that help analysts connect disparate data sources. Their Gotham platform ingests intelligence reports, financial records, communication metadata, and geospatial data, then builds a unified knowledge graph where analysts can discover non-obvious connections.

Memora is the same idea, but for your personal life. Instead of intelligence reports, we ingest your notes, conversations, and thoughts. Instead of tracking threat networks, we track your academic, social, professional, and personal networks. Instead of intelligence analysts querying Gotham, you query Memora through a terminal interface to understand your own life.

### CSC148 Connection Map

Every major component in Memora maps directly to concepts you study in CSC148:

| Memora Component | CSC148 Topic | Why It Matters |
|---|---|---|
| Knowledge Graph | Trees & Graphs | Nodes and edges form a directed multigraph |
| Node Type Hierarchy | Inheritance & Polymorphism | `BaseNode` with 12 specialized subclasses |
| Edge Constraints | ADT Invariants | Ontology rules enforce valid relationships |
| 9-Stage Pipeline | Stacks & Queues / Pipelines | Sequential processing with state passing |
| Entity Resolution | Hash Tables & Scoring | Multi-signal weighted matching |
| BFS Path Finding | BFS / Graph Traversal | Shortest path between any two nodes |
| Causal Chain Tracing | BFS along Typed Edges | Temporal graph traversal |
| Decay Scoring | Recursion & Math Functions | Exponential decay with logarithmic damping |
| Network Classification | ADTs / Enum Types | 7 context networks with keyword heuristics |
| Pattern Detection | Graph Analysis / Iteration | 11 behavioral detectors scanning the whole graph |
| SM-2 Spaced Repetition | State Machines | Repetition scheduling algorithm |
| CLI Command Routing | Dispatch Tables / REPL | Read-Eval-Print Loop with command registry |
| Big-O Analysis | Complexity Analysis | Every operation has measurable cost |

---

## Part 2: System Architecture — The Big Picture

### The 5-Layer Architecture

Memora is organized into five layers, each with clear responsibilities:

```
+------------------------------------------------------------+
|                     Layer 5: CLI Interface                   |
|  MemoraApp REPL, ANSI rendering, 20 subcommands, tracker   |
+------------------------------------------------------------+
|                     Layer 4: AI Council                      |
|  Archivist | Strategist | Researcher | Orchestrator         |
|  (LLM extraction, analysis, external research, routing)     |
+------------------------------------------------------------+
|                     Layer 3: Core Engines                    |
|  Pipeline | Entity Resolution | Actions | Outcomes          |
|  Investigation | Timeline | People Intel | Patterns         |
|  Briefing | Decay | Health | Bridges | Truth Layer          |
+------------------------------------------------------------+
|                     Layer 2: Graph + Vector Storage          |
|  DuckDB (nodes, edges, proposals) | Weaviate (embeddings)  |
+------------------------------------------------------------+
|                     Layer 1: Models & Ontology               |
|  Pydantic models | Edge constraints | Network keywords      |
+------------------------------------------------------------+
```

### Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Runtime | Python 3.12+ | Core language |
| Models | Pydantic v2 | Data validation, serialization, schema generation |
| Graph Storage | DuckDB | Embedded analytical database for nodes, edges, proposals |
| Vector Storage | Weaviate (embedded) | Semantic search with HNSW indexes |
| Embeddings | sentence-transformers, all-mpnet-base-v2 | 768-dimensional dense vectors |
| LLM | OpenAI API (gpt-5-nano), Responses API | Structured extraction, analysis, synthesis |
| Orchestration | LangGraph | Multi-agent state machine coordination |
| Scheduling | APScheduler | 10 background maintenance jobs |
| Configuration | pydantic-settings, YAML | Env vars + config file merging |
| Interface | ANSI terminal (raw Python) | Palantir-inspired CLI with boxes, sparklines, colors |

> **CSC148 Connection:** Notice that this is a **composition-heavy** architecture. The `MemoraApp` class does not inherit from anything special — it *composes* a `GraphRepository`, a `VectorStore`, an `ExtractionPipeline`, an `Orchestrator`, and various engines. This is the "has-a" pattern from CSC148: the app *has a* pipeline, the pipeline *has a* repository. Composition over inheritance is a core design principle.

### Local-First Design

Everything runs on your machine. The DuckDB database is a single file at `~/.memora/graph/memora.duckdb`. The Weaviate vector store runs as an embedded process with data at `~/.memora/vectors/`. The sentence-transformers model downloads once and caches locally at `~/.memora/models/`. The only network call is to OpenAI's API for LLM inference.

This means:
- Your data never leaves your machine (except for LLM queries, which are ephemeral)
- No server to deploy or maintain
- No accounts to create
- Works offline for everything except LLM-powered features

---

## Part 3: The Knowledge Graph — Core Data Structure

### What Is a Knowledge Graph?

In CSC148, you learn about graphs: vertices connected by edges. A knowledge graph is a graph where:
- **Nodes** represent real-world entities (people, events, ideas, decisions)
- **Edges** represent typed relationships between entities
- Both nodes and edges carry **properties** (metadata)

Memora's knowledge graph is a **directed labeled multigraph**: edges have direction (source to target), edges have types (labels), and multiple edges can connect the same pair of nodes.

### The BaseNode Class

Every node in Memora inherits from `BaseNode`, defined using Pydantic's `BaseModel`:

```python
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum
from typing import Any

class NodeType(str, Enum):
    EVENT = "EVENT"
    PERSON = "PERSON"
    COMMITMENT = "COMMITMENT"
    DECISION = "DECISION"
    GOAL = "GOAL"
    FINANCIAL_ITEM = "FINANCIAL_ITEM"
    NOTE = "NOTE"
    IDEA = "IDEA"
    PROJECT = "PROJECT"
    CONCEPT = "CONCEPT"
    REFERENCE = "REFERENCE"
    INSIGHT = "INSIGHT"

class BaseNode(BaseModel):
    """Shared properties for all graph nodes."""
    id: UUID = Field(default_factory=uuid4)
    node_type: NodeType
    title: str
    content: str = ""
    content_hash: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    networks: list[NetworkType] = Field(default_factory=list)
    human_approved: bool = False
    proposed_by: str = ""
    source_capture_id: UUID | None = None
    access_count: int = 0
    last_accessed: datetime | None = None
    decay_score: float = 1.0
    review_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        """Compute SHA-256 hash of title + content for dedup."""
        import hashlib
        raw = f"{self.title}|{self.content}"
        self.content_hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.content_hash
```

> **CSC148 Connection:** This is a textbook example of **inheritance with shared interface**. `BaseNode` defines the contract that every node type must satisfy. The `content_hash` method demonstrates **hashing** — the same concept behind Python dictionaries. The `Field(ge=0.0, le=1.0)` on `confidence` is a **class invariant** enforced at construction time, just like ADT preconditions.

### Specialized Node Types (Inheritance)

Each of the 12 node types extends `BaseNode` with type-specific fields:

```python
class EventNode(BaseNode):
    """An event that occurred or is planned."""
    node_type: NodeType = NodeType.EVENT
    event_date: datetime | None = None
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    event_type: str = ""
    duration: str = ""
    sentiment: str = ""
    recurring: bool = False

class PersonNode(BaseNode):
    """A person in the user's life."""
    node_type: NodeType = NodeType.PERSON
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    role: str = ""
    relationship_to_user: str = ""
    contact_info: dict[str, str] = Field(default_factory=dict)
    organization: str = ""
    last_interaction: datetime | None = None

class CommitmentNode(BaseNode):
    """A promise or obligation."""
    node_type: NodeType = NodeType.COMMITMENT
    due_date: datetime | None = None
    status: CommitmentStatus = CommitmentStatus.OPEN
    committed_by: str = ""
    committed_to: str = ""
    priority: Priority = Priority.MEDIUM
    description: str = ""

class GoalNode(BaseNode):
    """A goal being pursued."""
    node_type: NodeType = NodeType.GOAL
    target_date: datetime | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    status: GoalStatus = GoalStatus.ACTIVE
    priority: Priority = Priority.MEDIUM
    success_criteria: str = ""

class IdeaNode(BaseNode):
    """An idea at some stage of development."""
    node_type: NodeType = NodeType.IDEA
    maturity: IdeaMaturity = IdeaMaturity.SEED
    domain: str = ""
    potential_impact: str = ""
```

There are also `DecisionNode`, `FinancialItemNode`, `NoteNode`, `ProjectNode`, `ConceptNode`, `ReferenceNode`, and `InsightNode` — twelve specialized types in total.

> **CSC148 Connection:** This is **polymorphism** in action. You can write a function that accepts `BaseNode` and it works on any of the 12 types. The `NODE_TYPE_MODEL_MAP` dictionary maps `NodeType` enum values to their corresponding Python classes — this is the **factory pattern** you see in CSC148 when you dispatch on a type tag.

```python
NODE_TYPE_MODEL_MAP: dict[NodeType, type[BaseNode]] = {
    NodeType.EVENT: EventNode,
    NodeType.PERSON: PersonNode,
    NodeType.COMMITMENT: CommitmentNode,
    # ... all 12 types
}
```

### Student Examples

Here is what real nodes look like for a UTM student:

| Node Type | Example Title | Example Content | Networks |
|---|---|---|---|
| EVENT | "Coffee with Sam at Tim Hortons" | "Discussed A2 approach for CSC148, Sam suggested using BFS" | ACADEMIC, SOCIAL |
| PERSON | "Sam Chen" | "Study group partner, CSC148 lab section 102" | ACADEMIC, SOCIAL |
| COMMITMENT | "Review Sam's A2 code" | "Promised to review by Friday 3pm" | ACADEMIC |
| DECISION | "Skip campus hackathon" | "Chose to focus on midterms instead" | ACADEMIC, SOCIAL |
| GOAL | "Get 85+ in CSC148" | "Target: A- or higher, focus on graph algorithms" | ACADEMIC |
| IDEA | "Graph visualization tool for study notes" | "Use networkx to visualize course concept maps" | ACADEMIC, VENTURES |
| CONCEPT | "Breadth-First Search" | "Level-by-level graph traversal, O(V+E)" | ACADEMIC |

### The Edge Model

Edges connect nodes with typed, weighted relationships:

```python
class Edge(BaseModel):
    """A typed relationship between two nodes."""
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    edge_type: EdgeType
    edge_category: EdgeCategory
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    weight: float = 1.0
    bidirectional: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### 29 Edge Types in 7 Categories

Memora defines 29 edge types organized into 7 categories:

**Structural** (hierarchy):
- `PART_OF`, `CONTAINS`, `SUBTASK_OF`

**Associative** (semantic):
- `RELATED_TO`, `INSPIRED_BY`, `CONTRADICTS`, `SIMILAR_TO`, `COMPLEMENTS`

**Provenance** (origin tracking):
- `DERIVED_FROM`, `VERIFIED_BY`, `SOURCE_OF`, `EXTRACTED_FROM`

**Temporal** (time relationships):
- `PRECEDED_BY`, `EVOLVED_INTO`, `TRIGGERED`, `CONCURRENT_WITH`

**Personal** (user-centric):
- `COMMITTED_TO`, `DECIDED`, `FELT_ABOUT`, `RESPONSIBLE_FOR`

**Social** (person-to-person):
- `KNOWS`, `INTRODUCED_BY`, `OWES_FAVOR`, `COLLABORATES_WITH`, `REPORTS_TO`

**Network** (cross-network):
- `BRIDGES`, `MEMBER_OF`, `IMPACTS`, `CORRELATES_WITH`

> **CSC148 Connection:** The edge type system is an **ADT with invariants**. Each edge type has constraints on what node types can be its source and target. For example, `KNOWS` can only connect `PERSON` to `PERSON`, while `COMMITTED_TO` can only go from `PERSON` to `COMMITMENT`. These constraints are enforced by the ontology validation layer.

### Ontology Constraints

The `EDGE_CONSTRAINTS` dictionary enforces what connections are valid:

```python
EDGE_CONSTRAINTS: dict[EdgeType, tuple[set[NodeType] | None, set[NodeType] | None]] = {
    # Social edges: PERSON -> PERSON only
    EdgeType.KNOWS: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.COLLABORATES_WITH: ({NodeType.PERSON}, {NodeType.PERSON}),
    EdgeType.REPORTS_TO: ({NodeType.PERSON}, {NodeType.PERSON}),

    # Personal edges: PERSON -> specific types
    EdgeType.COMMITTED_TO: ({NodeType.PERSON}, {NodeType.COMMITMENT}),
    EdgeType.DECIDED: ({NodeType.PERSON}, {NodeType.DECISION}),

    # Structural: limited to actionable types
    EdgeType.SUBTASK_OF: (
        {NodeType.COMMITMENT, NodeType.GOAL, NodeType.PROJECT},
        {NodeType.COMMITMENT, NodeType.GOAL, NodeType.PROJECT},
    ),

    # Associative: anything can relate to anything
    EdgeType.RELATED_TO: (None, None),  # None means "any node type"
    EdgeType.SIMILAR_TO: (None, None),
    # ... and so on for all 29 types
}

def validate_edge(source_type: NodeType, target_type: NodeType, edge_type: EdgeType) -> bool:
    """Check if an edge type is valid between the given node types."""
    constraints = EDGE_CONSTRAINTS.get(edge_type)
    if constraints is None:
        return False
    allowed_sources, allowed_targets = constraints
    if allowed_sources is not None and source_type not in allowed_sources:
        return False
    if allowed_targets is not None and target_type not in allowed_targets:
        return False
    return True
```

> **CSC148 Connection:** The `validate_edge` function is a **precondition check** — the same concept as checking `is_empty()` before calling `dequeue()` on a queue. It ensures the graph maintains its structural invariants. The `None` sentinel for "any type allowed" is a common pattern in ADT design.

### The Central "You" Node

Every graph has exactly one special node — the "You" node — with a fixed UUID:

```python
YOU_NODE_ID = "00000000-0000-0000-0000-000000000001"
```

This is the ego node. Every other node in the graph is connected to You either directly or through a chain of edges. The pipeline enforces this connectivity: after every commit, orphan nodes are automatically linked to the You node via similarity-based bridges or direct fallback edges. This makes the graph a **connected component** centered on you — like a hub-and-spoke topology in a network.

---

## Part 4: Network Classification

### 7 Context Networks

Every node in Memora belongs to one or more **context networks** — domains of your life:

```python
class NetworkType(str, Enum):
    ACADEMIC = "ACADEMIC"
    PROFESSIONAL = "PROFESSIONAL"
    FINANCIAL = "FINANCIAL"
    HEALTH = "HEALTH"
    PERSONAL_GROWTH = "PERSONAL_GROWTH"
    SOCIAL = "SOCIAL"
    VENTURES = "VENTURES"
```

Student examples:

| Network | What It Contains | Student Example |
|---|---|---|
| ACADEMIC | Courses, professors, assignments, grades | "CSC148 A2 submission", "Prof. Liu's office hours" |
| PROFESSIONAL | Job, internship, career | "Part-time dev job at startup", "Resume update" |
| FINANCIAL | Money, expenses, budget | "Textbook purchase $85", "Part-time paycheck" |
| HEALTH | Exercise, sleep, mental health | "Gym session", "Midterm stress management" |
| PERSONAL_GROWTH | Skills, learning, habits | "Learning React tutorial", "Daily journaling" |
| SOCIAL | Friends, family, gatherings | "Birthday party for Alex", "Study group hangout" |
| VENTURES | Side projects, startups, ideas | "Study tool MVP", "Hackathon app idea" |

### Keyword-Based Network Suggestion

The `suggest_networks()` function uses keyword matching to automatically classify text into networks:

```python
NETWORK_KEYWORDS: dict[str, list[str]] = {
    "ACADEMIC": [
        "course", "class", "professor", "grade", "exam", "study", "research",
        "paper", "thesis", "lecture", "assignment", "university", "college",
        "semester", "GPA", "curriculum", "syllabus", "academic",
    ],
    "PROFESSIONAL": [
        "work", "job", "client", "meeting", "project", "deadline", "colleague",
        "manager", "deliverable", "sprint", "standup", "promotion", "salary",
        "office", "career", "resume", "interview", "company",
    ],
    "SOCIAL": [
        "friend", "family", "party", "dinner", "birthday", "relationship",
        "hangout", "call", "catch up", "wedding", "reunion", "favor",
        "gift", "social", "gathering",
    ],
    # ... FINANCIAL, HEALTH, PERSONAL_GROWTH, VENTURES similarly defined
}

def suggest_networks(text: str) -> list[tuple[str, float]]:
    """Suggest networks based on keyword matching in text."""
    text_lower = text.lower()
    scores: list[tuple[str, float]] = []

    for network, keywords in NETWORK_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        if matches > 0:
            confidence = min(0.95, 0.3 + (matches * 0.15))
            scores.append((network, confidence))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
```

> **CSC148 Connection:** This is a scoring algorithm with **linear scan** — O(K * W) where K is the number of keywords and W is proportional to text length. The `min(0.95, 0.3 + matches * 0.15)` formula is a **clamped linear function** that maps match count to confidence. With 1 match: 0.45 confidence. With 4 matches: 0.90. Never exceeds 0.95, because keyword matching alone should not yield absolute certainty.

---

## Part 5: The 9-Stage Extraction Pipeline

### Overview

When you type "Had coffee with Sam, discussed BFS for A2, promised to review his code by Friday" into Memora, it passes through a 9-stage async pipeline that transforms raw text into structured graph data:

```
Stage 1: Raw Input Capture
    |
Stage 2: Preprocessing (normalize dates, currency, detect language, compute hash)
    |
Stage 3: Archivist Extraction (LLM -> GraphProposal)
    |
Stage 4: Entity Resolution (match against existing nodes)
    |
Stage 5: Proposal Assembly (apply merge decisions)
    |
Stage 6: Validation Gate (route: auto/digest/explicit)
    |
Stage 7: Review (store proposal, auto-approve if qualified)
    |
Stage 8: Graph Commit (atomic DuckDB transaction)
    |
Stage 9: Post-Commit (embeddings, edge weights, bridges, health, truth layer)
```

### Pipeline State

State flows through the pipeline via a `PipelineState` dataclass:

```python
from dataclasses import dataclass
from enum import IntEnum

class PipelineStage(IntEnum):
    RAW_INPUT = 1
    PREPROCESSING = 2
    EXTRACTION = 3
    ENTITY_RESOLUTION = 4
    PROPOSAL_ASSEMBLY = 5
    VALIDATION_GATE = 6
    REVIEW = 7
    GRAPH_COMMIT = 8
    POST_COMMIT = 9

@dataclass
class PipelineState:
    """Mutable state carried through the pipeline."""
    capture_id: str
    raw_content: str
    processed_content: str = ""
    content_hash: str = ""
    language: str = "en"
    is_duplicate: bool = False
    proposal: GraphProposal | None = None
    resolutions: list[ResolutionResult] | None = None
    proposal_id: str | None = None
    route: ProposalRoute = ProposalRoute.AUTO
    stage: PipelineStage = PipelineStage.RAW_INPUT
    status: str = "processing"
    error: str | None = None
    clarification_needed: bool = False
    clarification_message: str = ""
```

> **CSC148 Connection:** This is a **state machine**. Each stage is a state, and the pipeline transitions from one state to the next. The `PipelineState` object is carried through like a token being processed. If any stage sets `error`, the pipeline halts — just like an exception unwinding a call stack. If `clarification_needed` is set, the pipeline pauses for human input, similar to how a generator yields.

### The Pipeline Runner

The `ExtractionPipeline.run()` method orchestrates all 9 stages:

```python
class ExtractionPipeline:
    """9-stage async pipeline from raw text to graph commit."""

    async def run(self, capture_id: str, raw_content: str,
                  on_stage: Callable | None = None) -> PipelineState:
        state = PipelineState(capture_id=capture_id, raw_content=raw_content)

        stages = [
            (PipelineStage.PREPROCESSING, self._preprocess),
            (PipelineStage.EXTRACTION, self._extract),
            (PipelineStage.ENTITY_RESOLUTION, self._resolve_entities),
            (PipelineStage.PROPOSAL_ASSEMBLY, self._assemble_proposal),
            (PipelineStage.VALIDATION_GATE, self._validation_gate),
            (PipelineStage.REVIEW, self._review),
            (PipelineStage.GRAPH_COMMIT, self._commit),
            (PipelineStage.POST_COMMIT, self._post_commit),
        ]

        for stage_enum, handler in stages:
            state.stage = stage_enum
            if on_stage:
                on_stage(stage_enum, "running")
            try:
                state = await handler(state)
                if state.error:
                    break
                if state.clarification_needed:
                    break
                if on_stage:
                    on_stage(stage_enum, "done")
            except Exception as e:
                state.error = f"Stage {stage_enum.name} failed: {str(e)}"
                break

        return state
```

> **CSC148 Connection:** The pipeline runner is essentially a **for-loop over a list of (stage, handler) tuples** — a dispatch table. Each handler takes state in and produces state out. This is the **pipe-and-filter** pattern: each stage is a filter that transforms the data. The `on_stage` callback is the **observer pattern**, allowing the CLI tracker to display real-time progress.

### Stage-by-Stage Walkthrough: Coffee with Sam

Let us trace our running example through all 9 stages.

**Input:** "Had coffee with Sam, discussed BFS for A2, promised to review his code by Friday"

#### Stage 2: Preprocessing

```python
async def _preprocess(self, state: PipelineState) -> PipelineState:
    text = state.raw_content.strip()
    text = self._normalize_dates(text)    # "Friday" -> "2026-03-06"
    text = self._normalize_currency(text)  # "$50k" -> "$50,000.00"
    state.language = self._detect_language(text)  # "en"
    state.content_hash = hashlib.sha256(state.raw_content.encode()).hexdigest()
    state.processed_content = text
    return state
```

The date normalizer converts "Friday" to the next Friday's ISO date. The currency normalizer converts "$50k" to "$50,000.00". Language detection uses ASCII ratio heuristics (>90% ASCII = English).

**After Stage 2:** `processed_content` = "Had coffee with Sam, discussed BFS for A2, promised to review his code by 2026-03-06"

#### Stage 3: Archivist Extraction

The Archivist agent (LLM-powered) receives the preprocessed text plus RAG context from existing nodes, and produces a `GraphProposal`:

```python
async def _extract(self, state: PipelineState) -> PipelineState:
    result = await self._archivist.extract(state.processed_content, state.capture_id)
    if result.clarification_needed:
        state.clarification_needed = True
        return state
    state.proposal = result.proposal
    return state
```

The Archivist uses the OpenAI Responses API with `json_schema` structured output to guarantee a valid JSON response matching the `GraphProposal` schema. The proposal might contain:

- **Nodes to create:** EventNode("Coffee with Sam"), PersonNode("Sam"), CommitmentNode("Review Sam's A2 code"), ConceptNode("BFS")
- **Edges to create:** You --KNOWS--> Sam, You --COMMITTED_TO--> "Review code", Event --RELATED_TO--> "BFS"
- **Network assignments:** Event -> [ACADEMIC, SOCIAL], Commitment -> [ACADEMIC]

#### Stage 4: Entity Resolution

Each proposed node is compared against existing graph nodes to avoid duplicates. This is covered in detail in Part 6.

#### Stage 5: Proposal Assembly

Merge decisions from entity resolution are applied: if "Sam" already exists in the graph, the new PersonNode proposal is converted to an update on the existing Sam node, and all edge references are rewritten.

#### Stage 6: Validation Gate

The gate routes the proposal based on confidence and merge decisions:

```python
async def _validation_gate(self, state: PipelineState) -> PipelineState:
    confidence = state.proposal.confidence
    threshold = self._settings.auto_approve_threshold  # default 0.85

    has_merges = any(r.outcome == ResolutionOutcome.MERGE for r in (state.resolutions or []))
    has_deferred = any(r.outcome == ResolutionOutcome.DEFER for r in (state.resolutions or []))

    if has_merges or has_deferred:
        state.route = ProposalRoute.EXPLICIT  # human review required
    elif confidence >= threshold:
        state.route = ProposalRoute.AUTO       # auto-approve
    else:
        state.route = ProposalRoute.DIGEST     # batch review later
    return state
```

#### Stage 7: Review

The proposal is stored in DuckDB. If routed AUTO, it proceeds to commit immediately.

#### Stage 8: Graph Commit

An atomic DuckDB transaction creates all nodes and edges in a single commit:

```python
async def _commit(self, state: PipelineState) -> PipelineState:
    if state.route != ProposalRoute.AUTO:
        return state  # skip commit for non-auto proposals
    success = self._repo.commit_proposal(UUID(state.proposal_id))
    if not success:
        state.error = "Graph commit failed"
    return state
```

#### Stage 9: Post-Commit Processing

This is where the graph comes alive. Five substages run, some sequentially, some in parallel:

```python
async def _post_commit(self, state: PipelineState) -> PipelineState:
    # Sequential: embeddings must complete before edge weights
    await self._generate_embeddings(state)
    await self._compute_edge_weights(state)

    # Ensure every node connects to the central You node
    await self._ensure_graph_connectivity(state)

    # Parallel: independent substages
    await asyncio.gather(
        self._detect_bridges(state),
        self._recalculate_health(state),
        self._check_notification_triggers(state),
        self._cross_reference_truth_layer(state),
        return_exceptions=True,
    )
    return state
```

The embedding generation uses the `all-mpnet-base-v2` model to create 768-dimensional vectors for each new node, which are stored in Weaviate for future semantic search. Edge weights are computed from cosine similarity between source and target node embeddings. Bridge discovery finds cross-network connections. Health scoring updates affected network scores. The truth layer cross-references new claims against verified facts.

> **CSC148 Connection:** The post-commit stage demonstrates **parallelism** — `asyncio.gather()` runs four independent tasks concurrently, just like how you might parallelize independent operations in a divide-and-conquer algorithm. The sequential embedding -> edge weight dependency is like a **topological sort** constraint: you cannot compute edge weights until embeddings exist.

---

## Part 6: Entity Resolution

### The Deduplication Problem

When you say "Met with Sam today," does "Sam" refer to Sam Chen from your study group who already exists in the graph? Or is this a new Sam? Entity resolution answers this question using 6 weighted signals.

### The EntityResolver Class

```python
class EntityResolver:
    """Multi-signal entity resolution engine."""

    WEIGHTS = {
        "exact_name": 0.95,
        "embedding_similarity": 0.80,
        "same_network": 0.15,
        "temporal_proximity": 0.10,
        "shared_relationships": 0.20,
        "llm_adjudication": 0.90,
    }

    EMBEDDING_THRESHOLD = 0.92
    MERGE_THRESHOLD = 0.85
    CREATE_THRESHOLD = 0.40
    TEMPORAL_WINDOW_DAYS = 7
```

### The 6 Signals

**Signal 1: Exact Name Match (weight: 0.95)**

The strongest non-LLM signal. Exact match scores 1.0. Substring match (e.g., "Sam" in "Sam Chen") scores 0.7+. Token overlap ("Carlos Rivera" vs "Carlos") uses Jaccard similarity.

```python
def _score_exact_name(self, candidate, node):
    proposed = node.title.lower().strip()
    existing = candidate.existing_title.lower().strip()

    if proposed == existing:
        candidate.signals["exact_name"] = 1.0
    elif proposed in existing or existing in proposed:
        shorter = min(len(proposed), len(existing))
        longer = max(len(proposed), len(existing))
        candidate.signals["exact_name"] = max(0.7, shorter / longer)
    else:
        # Token overlap
        proposed_tokens = set(proposed.split())
        existing_tokens = set(existing.split())
        overlap = proposed_tokens & existing_tokens
        if overlap:
            union = proposed_tokens | existing_tokens
            candidate.signals["exact_name"] = 0.6 * len(overlap) / len(union)
        else:
            candidate.signals["exact_name"] = 0.0
```

**Signal 2: Embedding Similarity (weight: 0.80)**

Semantic similarity in 768-dimensional vector space. Searches Weaviate for the 5 most similar existing nodes of the same type.

**Signal 3: Same Network (weight: 0.15)**

Do the proposed and existing nodes share context networks? If both are in ACADEMIC, that is evidence they refer to the same entity.

**Signal 4: Temporal Proximity (weight: 0.10)**

Were both nodes created within a 7-day window? Recent mentions of similar entities are more likely to refer to the same real-world entity.

```python
def _score_temporal(self, candidate, node, created_at=None):
    delta = abs((proposed_time - existing_time).days)
    if delta <= self.TEMPORAL_WINDOW_DAYS:
        candidate.signals["temporal_proximity"] = 1.0 - (delta / self.TEMPORAL_WINDOW_DAYS)
```

**Signal 5: Shared Relationships (weight: 0.20)**

Do the proposed and existing nodes connect to the same other nodes? If both "Sam" nodes connect to nodes like "CSC148" and "Study Group," they are likely the same person.

**Signal 6: LLM Adjudication (weight: 0.90)**

For ambiguous cases (combined score between 0.40 and 0.90), the LLM is asked directly: "Are these two entries referring to the same entity?" Returns a 0.0-1.0 confidence score.

### Weighted Scoring Formula

The combined score is a **weighted average** of all available signals:

```python
def _weighted_sum(self, signals: dict[str, float]) -> float:
    """Compute weighted average of available signals."""
    total_weight = sum(self.WEIGHTS[k] for k in signals if k in self.WEIGHTS)
    if total_weight == 0:
        return 0.0
    weighted = sum(signals[k] * self.WEIGHTS[k] for k in signals if k in self.WEIGHTS)
    return weighted / total_weight
```

> **CSC148 Connection:** This is a **hash table lookup** combined with a **weighted average**. The `WEIGHTS` dictionary provides O(1) lookup for each signal's weight. The weighted average formula is:
>
> `score = (sum of signal_i * weight_i) / (sum of weight_i for available signals)`
>
> This "only average over available signals" design means missing signals do not penalize the score — the same principle behind handling missing data in any scoring system.

### Resolution Outcomes

Based on the combined score, each proposed node gets one of four outcomes:

| Score Range | Outcome | What Happens |
|---|---|---|
| >= 0.85 | MERGE | Proposed node merges with existing node |
| 0.40 - 0.85 | DEFER | Needs human review |
| < 0.40 | CREATE | Create as a new node |
| Exact name match = 1.0 | MERGE (forced) | Perfect name match always merges |

```python
@dataclass
class ResolutionResult:
    proposed_temp_id: str
    proposed_title: str
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    chosen: ResolutionCandidate | None = None
    outcome: ResolutionOutcome = ResolutionOutcome.CREATE
    audit_log: list[str] = field(default_factory=list)
```

The `audit_log` is a list of human-readable strings documenting every decision, enabling full transparency:

```
["Exact name search: 1 matches for 'Sam'",
 "Embedding search: 3 similar nodes",
 "MERGE (exact name): 'Sam' -> 'Sam Chen' (exact_name=1.0, forced merge)"]
```

---

## Part 7: The AI Council

### Three Specialized Agents + Orchestrator

Memora's AI council consists of three specialized agents coordinated by an orchestrator:

1. **Archivist** — Extracts structured data from unstructured text
2. **Strategist** — Analyzes graph data and provides strategic insights
3. **Researcher** — Gathers external information with PII anonymization
4. **Orchestrator** — Routes queries and synthesizes multi-agent outputs

### The Archivist Agent

The Archivist converts natural language into `GraphProposal` objects using the OpenAI Responses API with `json_schema` structured output:

```python
class ArchivistAgent:
    def __init__(self, api_key, vector_store=None, embedding_engine=None,
                 model="gpt-5-nano", you_node_id=None):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._system_prompt = self._load_system_prompt()  # from prompts/archivist_system.md

    async def extract(self, text: str, capture_id: str) -> ArchivistResult:
        # 1. Retrieve similar existing nodes for RAG context
        rag_nodes = await self._retrieve_rag_context(text)

        # 2. Build static + dynamic prompt (static is cacheable by OpenAI)
        system_prompt = self._get_static_system_prompt()
        dynamic_context = self._build_dynamic_context(context, capture_id)

        # 3. Call OpenAI Responses API with json_schema format
        response = await self._client.responses.create(
            model=self._model,
            instructions=system_prompt,
            input=f"{dynamic_context}\n\n---\n\nText:\n{text}",
            text={"format": {"type": "json_schema", "name": "graph_proposal",
                             "schema": GRAPH_PROPOSAL_SCHEMA}},
            reasoning={"effort": "low"},
            max_output_tokens=16384,
        )

        # 4. Parse JSON into validated GraphProposal
        proposal = GraphProposal(**json.loads(response.output_text))
        return ArchivistResult(proposal=proposal)
```

Key design decisions:
- The `json_schema` response format guarantees valid JSON matching the Pydantic-generated schema
- The system prompt is static (cacheable by OpenAI for cost savings), while capture-specific context is injected via the input message
- RAG context from existing nodes helps the LLM avoid creating duplicates
- `reasoning={"effort": "low"}` keeps costs down for extraction tasks

> **CSC148 Connection:** The Archivist uses the **template method pattern**: the `extract()` method defines the algorithm skeleton (retrieve context, build prompt, call API, parse response), while the individual steps can be customized. The RAG context retrieval is essentially a **priority queue** pattern — retrieve the top-K most relevant existing nodes to inject into the prompt.

### The Strategist Agent

The Strategist analyzes graph data and provides insights. It has three modes:

1. **Analyze** — Strategic analysis of a query using graph context
2. **Generate Briefing** — Daily briefing from collected data
3. **Critique** — Challenge a statement using graph evidence (adversarial mode)

```python
class StrategistAgent:
    async def analyze(self, query: str, graph_context: dict | None = None) -> StrategistResult:
        """Strategic analysis with graph context."""
        if graph_context is None:
            graph_context = self._build_graph_context(query)  # hybrid search + entity lookup
        # ... LLM call with context injection

    async def generate_briefing(self, briefing_data: dict) -> DailyBriefing:
        """Generate daily briefing with typed sections."""
        # Returns: summary, mood, urgent items, upcoming, people followup,
        #          patterns, wins, stalled items, review queue

    async def critique(self, statement: str, graph_context: dict | None = None) -> CritiqueResult:
        """CRITIC MODE: challenge a statement using graph evidence."""
        # Returns: counter_evidence, blind_spots, confidence
```

The Strategist builds **entity-aware graph context** by extracting capitalized words (proper nouns) from the query, searching the graph by title, and expanding their 1-hop neighborhoods. This ensures the LLM has concrete data about every named entity mentioned.

### The Researcher Agent

The Researcher gathers external information with **PII anonymization**:

```python
class ResearcherAgent:
    def _anonymize_query(self, query: str, graph_context: dict | None = None) -> str:
        """Strip PII from the query before external searches."""
        text = query
        text = _EMAIL_PATTERN.sub("[email]", text)    # regex: email addresses
        text = _PHONE_PATTERN.sub("[phone]", text)    # regex: phone numbers
        text = _SSN_PATTERN.sub("[id-number]", text)  # regex: SSN patterns
        text = _DOLLAR_PATTERN.sub("a sum of money", text)  # dollar amounts

        # Replace names found in graph context
        if graph_context:
            names = self._extract_names_from_context(graph_context)
            for name in names:
                text = text.replace(name, "someone")
        return text
```

The Researcher has access to MCP (Model Context Protocol) tool servers:
- **GoogleSearchMCP** — Google web search
- **BraveSearchMCP** — Brave web search
- **SemanticScholarMCP** — Academic paper search
- **PlaywrightScraperMCP** — Web scraping via httpx
- **GitHubMCP** — Repository and code search

Research findings are deposited as verified facts in the Truth Layer with source URLs for traceability.

### The Orchestrator (LangGraph State Machine)

The Orchestrator coordinates all three agents using a LangGraph state machine:

```python
class Orchestrator:
    def _build_graph(self) -> StateGraph:
        graph = StateGraph(CouncilState)

        # Add nodes (processing steps)
        graph.add_node("classify", self._classify_node)
        graph.add_node("archivist", self._archivist_node)
        graph.add_node("strategist", self._strategist_node)
        graph.add_node("researcher", self._researcher_node)
        graph.add_node("council_all", self._council_all_agents_node)
        graph.add_node("synthesize", self._synthesize_node)
        graph.add_node("deliberate", self._deliberation_node)

        # Set entry point
        graph.set_entry_point("classify")

        # Conditional routing after classification
        graph.add_conditional_edges("classify", self._route_after_classify, {
            "archivist": "archivist",
            "strategist": "strategist",
            "researcher": "researcher",
            "council_all": "council_all",
        })

        # All paths converge at synthesis
        graph.add_edge("archivist", "synthesize")
        graph.add_edge("strategist", "synthesize")
        graph.add_edge("researcher", "synthesize")
        graph.add_edge("council_all", "synthesize")

        # Deliberation loop for high-disagreement council queries
        graph.add_conditional_edges("synthesize", self._route_after_synthesize, {
            "deliberate": "deliberate",
            "end": END,
        })
        graph.add_edge("deliberate", "synthesize")

        return graph.compile()
```

> **CSC148 Connection:** This is a **directed graph used as a state machine**. Each node in the LangGraph is a processing step. Conditional edges are like `if/elif` branches — the `_route_after_classify` function returns a string indicating which node to visit next. The deliberation loop creates a **cycle** in the graph, bounded by `max_deliberation_rounds` to prevent infinite loops. This is exactly the kind of graph structure you study in CSC148: nodes, directed edges, cycles, and traversal.

### Query Classification

The classifier uses weighted keyword scoring to route queries:

```python
class QueryType(str, Enum):
    CAPTURE = "capture"     # "I met Sam today..."
    ANALYSIS = "analysis"   # "How am I doing on my goals?"
    RESEARCH = "research"   # "What is the latest on graph databases?"
    COUNCIL = "council"     # "Help me make a comprehensive decision about..."
```

Capture signals ("I did", "I met", "I promised") route to the Archivist. Analysis signals ("analyze", "should I", "status") route to the Strategist. Research signals ("how does", "look up", "fact check") route to the Researcher. Council signals ("complex decision", "comprehensive analysis") invoke all three agents.

### Confidence-Weighted Synthesis

When multiple agents contribute, the synthesizer produces a coherent response:

```python
def _synthesize_node(self, state: CouncilState) -> CouncilState:
    # Collect outputs and detect disagreement
    confidences = [o.get("confidence", 0.5) for o in outputs]
    spread = max(confidences) - min(confidences)
    state["high_disagreement"] = spread > 0.3

    # If single agent, use its output directly
    # If multiple agents, use LLM to produce coherent synthesis
    if len(outputs) > 1:
        state["synthesis"] = self._llm_synthesize(query, raw_synthesis, outputs)

    # Apply truth layer fact-check gate
    if self._truth_layer:
        fact_check = self._fact_check_synthesis(raw_synthesis)
        if fact_check:
            raw_synthesis += f"\n\n[fact_check] {fact_check}"
```

---

## Part 8: The Living Graph Engine

The graph is not static. It is a living system maintained by 10 scheduled background jobs that run automatically. These jobs implement the "Living Graph Engine" — the subsystem that keeps the graph accurate, relevant, and insightful.

### Job 1: Decay Scoring (runs 2:00 AM daily)

Every node has a `decay_score` between 0.0 and 1.0 that represents its current relevance. The score decays exponentially over time:

```
decay_score = e^(-effective_lambda * delta_days)
```

Where:
- `delta_days` = days since the node's most recent meaningful timestamp
- `effective_lambda` = lambda / (1 + ln(1 + access_count))
- Access count **slows** decay (logarithmic damping)

```python
class DecayScoring:
    def compute_decay(self, t_anchor: datetime, lambda_val: float,
                      access_count: int = 0) -> float:
        delta_days = max(0.0, (now - t_anchor).total_seconds() / 86400.0)
        effective_lambda = lambda_val / (1 + log(1 + access_count))
        return exp(-effective_lambda * delta_days)
```

Each network decays at a different rate:

| Network | Lambda | Half-Life (days) | Rationale |
|---|---|---|---|
| SOCIAL | 0.07 | ~10 | Social interactions fade fast |
| ACADEMIC | 0.05 | ~14 | Course material cycles each semester |
| HEALTH | 0.05 | ~14 | Health habits need regular reinforcement |
| PERSONAL_GROWTH | 0.04 | ~17 | Skills take time to build |
| PROFESSIONAL | 0.03 | ~23 | Work relationships are more stable |
| VENTURES | 0.03 | ~23 | Side projects evolve slowly |
| FINANCIAL | 0.02 | ~35 | Financial decisions have long-term impact |

Active items (open commitments, active goals, active projects) are **pinned at 1.0** — they never decay until their status changes. Future-dated items also stay at 1.0 until their date passes.

> **CSC148 Connection:** The decay function is a composition of **exponential decay** (e^-x) with **logarithmic damping** (ln(1+x)). The logarithmic damping on access count means the first few accesses dramatically slow decay, but additional accesses have diminishing returns. This is exactly the kind of mathematical analysis you do in CSC148's Big-O discussions — logarithmic growth is slower than linear, which is slower than exponential.

### Job 2: Bridge Discovery (runs 3:00 AM daily)

Bridges are cross-network connections — nodes in different networks that are semantically similar. The bridge discovery algorithm:

1. For each recently modified node, embed it into the 768-dimensional vector space
2. Search for similar nodes in **different** networks
3. If cosine similarity exceeds the threshold (default 0.75), create a bridge record
4. Batch-validate bridges with the LLM to check if the connection is meaningful

Example: Your "Graph visualization tool" idea (VENTURES) might bridge to your "BFS concepts" note (ACADEMIC) — the AI helps you see that your coursework directly feeds your side project.

### Job 3: Network Health Scoring (runs every 6 hours)

For each of the 7 networks, compute a health snapshot with three metrics:

- **Commitment completion rate** — what fraction of commitments in this network are completed?
- **Alert ratio** — what fraction of nodes are flagged (overdue, decayed, stale)?
- **Staleness flags** — how many nodes have decay scores below 0.3?

```python
# Thresholds for status determination
FALLING_BEHIND_COMPLETION = 0.4     # < 40% completion = falling behind
NEEDS_ATTENTION_COMPLETION = 0.7    # < 70% completion = needs attention
FALLING_BEHIND_ALERT_RATIO = 0.3   # > 30% alerts = falling behind
STALENESS_DECAY_THRESHOLD = 0.3    # nodes below this are "stale"
```

Status is determined as: `ON_TRACK`, `NEEDS_ATTENTION`, or `FALLING_BEHIND`. Momentum is computed by comparing with the previous snapshot: `UP`, `STABLE`, or `DOWN`.

### Job 4: Commitment Scanning (runs 6:00 AM daily)

Scans all open commitments for approaching deadlines and overdue items. Generates notifications for commitments due within 48 hours and marks past-due commitments as overdue.

### Job 5: Relationship Decay Detection (runs weekly, Sundays)

Detects relationships that are growing stale based on tiered thresholds:

```python
# Relationship tiers and their staleness thresholds (days)
relationship_decay_thresholds = {
    "close": 7,        # Close contacts: no interaction in 7 days = decay alert
    "regular": 14,     # Regular contacts: 14 days
    "acquaintance": 30, # Acquaintances: 30 days
}
```

### Job 6: Spaced Repetition (runs 5:00 AM daily)

Implements the **SM-2 algorithm** (SuperMemo 2) for scheduling knowledge review:

```python
# SM-2 parameters per node
sm2_params = {
    "easiness_factor": 2.5,    # starts at 2.5, adjusted per review
    "repetition_number": 0,     # count of successful reviews
    "interval": 0,              # days until next review
    "review_date": "2026-03-02",
}
```

After each review, the quality score (0-5) adjusts the easiness factor:
- Quality 0 (complete blackout): reset interval to 0
- Quality 5 (perfect recall): extend interval by easiness factor

> **CSC148 Connection:** SM-2 is a **state machine** with five parameters. Each review transitions the state based on the quality score. The interval growth follows a recurrence relation: `interval(n) = interval(n-1) * easiness_factor`. This is exactly the kind of recurrence you analyze in CSC148: each step depends on the previous step's output.

### Job 7: Gap Detection (runs weekly, Sundays 1:00 AM)

Identifies 5 types of gaps in the knowledge graph:

1. **Orphaned nodes** — nodes with zero edges (isolated vertices)
2. **Stalled goals** — goals with no recent activity or progress
3. **Dead-end projects** — projects with no active subtasks or next steps
4. **Isolated concepts** — concepts not linked to any actionable nodes
5. **Unresolved decisions** — decisions still pending without resolution

### Job 8: Daily Briefing (runs 7:00 AM daily)

The `BriefingCollector` aggregates data from all subsystems, then the Strategist agent generates a structured daily briefing with sections for urgent items, recent activity, upcoming commitments, people to follow up with, detected patterns, wins, stalled items, and review queue.

### Job 9: Pattern Detection (runs 4:00 AM daily)

The PatternEngine runs 11 behavioral detectors (covered in Part 11).

### Job 10: Outcome Review (runs 6:30 AM daily)

Reviews decisions and goals whose outcomes can now be evaluated, prompting the user to record actual outcomes for feedback loop analysis.

---

## Part 9: Truth Layer and Verified Facts

### The Problem: Not All Information is Equal

When the Archivist extracts "Sam said the midterm is on March 15th," is that a verified fact? It is a claim extracted from user input, attributed to Sam, with no external verification. The Truth Layer provides a system for tracking fact confidence, lifecycle, and verification status.

### Fact Model

```python
class FactStatus(str, Enum):
    ACTIVE = "active"          # Currently believed to be true
    STALE = "stale"            # Past recheck date, needs verification
    CONTRADICTED = "contradicted"  # Conflicting evidence found
    RETIRED = "retired"        # No longer relevant

class FactLifecycle(str, Enum):
    STATIC = "static"    # Facts that don't change (e.g., "Paris is the capital of France")
    DYNAMIC = "dynamic"  # Facts that may change (e.g., "Midterm is March 15th")
```

### Core Operations

**Deposit a fact:**
```python
def deposit_fact(self, node_id, statement, confidence=0.8,
                 lifecycle=FactLifecycle.DYNAMIC, verified_by="archivist",
                 recheck_interval_days=90):
    # Create fact with status=ACTIVE
    # Set next_check = now + recheck_interval for DYNAMIC facts
    # STATIC facts never need rechecking
```

**Check for contradictions:**
```python
def check_contradiction(self, statement: str, node_id: str) -> list[dict]:
    """Find existing active facts that might contradict the new statement."""
    existing = self.query_facts(node_id=node_id, status="active")
    new_words = set(statement.lower().split())
    contradictions = []
    for fact in existing:
        existing_words = set(fact["statement"].lower().split())
        overlap = new_words & existing_words
        # High word overlap + different statement = potential contradiction
        if len(overlap) >= 3 and fact["statement"].lower() != statement.lower():
            contradictions.append(fact)
    return contradictions
```

**Record a fact check:**
```python
def record_check(self, fact_id, check_type, result, evidence="", checked_by="system"):
    # result can be "confirmed" or "contradicted"
    # If confirmed: reset next_check timer for dynamic facts
    # If contradicted: set status to CONTRADICTED
```

> **CSC148 Connection:** The contradiction detector uses **set intersection** — converting statements into sets of words and checking overlap. This is O(n) for set construction and O(min(m,n)) for intersection, where n and m are the word counts. The 3-word overlap threshold is a heuristic, not a formal proof, but it avoids false positives from generic words while catching genuine conflicts. This is the kind of practical algorithmic reasoning CSC148 teaches.

### Integration with Pipeline

During Stage 9 (Post-Commit), the pipeline automatically:
1. Cross-references new claims against existing verified facts
2. If no contradiction is found, auto-deposits the claim as a verified fact with confidence 0.7
3. If a contradiction is found, creates a high-priority notification

---

## Part 10: Adaptive RAG Pipeline

### What is RAG?

RAG (Retrieval-Augmented Generation) is a technique where you **retrieve** relevant documents before **generating** an LLM response. Instead of relying solely on the LLM's training data, you inject specific, current information from your knowledge graph.

### Memora's RAG Flow

When you ask Memora a question like "What is my progress on CSC148 goals?", the Orchestrator:

1. **Embeds** the query into a 768-dimensional vector using all-mpnet-base-v2
2. **Hybrid searches** Weaviate (dense vector search + BM25 keyword search with RRF fusion)
3. **Expands** the top-5 results' 1-hop neighborhoods in the graph
4. **Entity-aware lookup**: extracts capitalized words (proper nouns) from the query, searches graph by title, expands their neighborhoods
5. **Assesses retrieval quality** (CRAG gate)
6. **Injects** the gathered context into the LLM prompt

### CRAG: Corrective RAG

CRAG (Corrective Retrieval-Augmented Generation) adds a quality gate on retrieval results:

```python
def _assess_retrieval_quality(self, query: str, results: list) -> str:
    """Returns 'sufficient' or 'poor' based on three checks."""

    # Check 1: Minimum number of results (default: 3)
    if len(results) < self._settings.crag_min_results:
        return "poor"

    # Check 2: Top result relevance score (default threshold: 0.5)
    if results[0].score < self._settings.crag_relevance_threshold:
        return "poor"

    # Check 3: Query term coverage (default: 30%)
    query_terms = {t.lower() for t in query.split() if len(t) > 2}
    all_content = " ".join(r.content.lower() for r in results)
    covered = sum(1 for t in query_terms if t in all_content)
    if covered / len(query_terms) < self._settings.crag_term_coverage_threshold:
        return "poor"

    return "sufficient"
```

If retrieval quality is "poor," the Orchestrator escalates from a single-agent strategist call to the full council (all three agents), allowing the Researcher to supplement with external web search.

### Hybrid Search in Weaviate

Weaviate provides both dense vector search and BM25 keyword search. Memora combines them with **Reciprocal Rank Fusion (RRF)**:

```
hybrid_score = alpha * dense_rank_score + (1 - alpha) * bm25_rank_score
```

Dense search is good at finding semantically similar content ("BFS algorithm" matches "breadth-first traversal"). BM25 is good at exact keyword matches ("CSC148" matches "CSC148"). The hybrid approach captures both.

> **CSC148 Connection:** Vector search is essentially a **nearest neighbor search** in 768-dimensional space. Weaviate uses HNSW (Hierarchical Navigable Small World) graphs internally — a graph data structure where nodes are vectors and edges connect nearby vectors, enabling approximate nearest neighbor search in O(log n) time instead of O(n) brute force. BM25 is based on **inverted indexes** — hash tables that map each word to the list of documents containing it.

---

## Part 11: Action Engine, Outcomes, and Patterns

### The Action Engine

The Action Engine provides 6 typed operations that modify the knowledge graph with precondition checks and cascading side effects:

```python
class ActionEngine:
    def __init__(self, repo, truth_layer=None, health_scoring=None,
                 notification_manager=None):
        self._registry = {
            ActionType.COMPLETE_COMMITMENT: {
                "label": "Complete Commitment",
                "node_types": [NodeType.COMMITMENT],
                "handler": self._complete_commitment,
            },
            ActionType.PROMOTE_IDEA: {
                "label": "Promote Idea to Project",
                "node_types": [NodeType.IDEA],
                "handler": self._promote_idea,
            },
            ActionType.ARCHIVE_GOAL: {
                "label": "Archive Goal",
                "node_types": [NodeType.GOAL],
                "handler": self._archive_goal,
            },
            ActionType.ADVANCE_GOAL: {
                "label": "Advance Goal",
                "node_types": [NodeType.GOAL],
                "handler": self._advance_goal,
            },
            ActionType.RECORD_OUTCOME: {
                "label": "Record Outcome",
                "node_types": [NodeType.DECISION, NodeType.GOAL, NodeType.COMMITMENT],
                "handler": self._record_outcome,
            },
            ActionType.LINK_ENTITIES: {
                "label": "Link Entities",
                "node_types": list(NodeType),  # any type
                "handler": self._link_entities,
            },
        }
```

> **CSC148 Connection:** The `_registry` is a **dispatch table** — a dictionary mapping action types to handler functions. This is the same pattern as a command dispatch in a REPL: instead of a long `if/elif` chain, you look up the handler in O(1) time. The `get_available_actions()` method filters the registry by checking preconditions against the node's current state, demonstrating **runtime polymorphism**.

### Precondition Checks

Each action has preconditions that must be satisfied:

```python
def _check_precondition(self, action_type, node) -> bool:
    if action_type == ActionType.COMPLETE_COMMITMENT:
        return node.status == CommitmentStatus.OPEN  # Can only complete open commitments
    elif action_type == ActionType.PROMOTE_IDEA:
        return node.maturity != IdeaMaturity.ARCHIVED  # Can't promote archived ideas
    elif action_type == ActionType.ARCHIVE_GOAL:
        return node.status == GoalStatus.ACTIVE  # Can only archive active goals
    # ...
```

### Side Effects

After a successful action, side effects cascade:

- **COMPLETE_COMMITMENT**: Recalculates network health, sends "COMMITMENT_COMPLETED" notification
- **RECORD_OUTCOME**: Deposits outcome as a verified fact in the Truth Layer
- **PROMOTE_IDEA**: Creates a new ProjectNode, creates EVOLVED_INTO edge from idea to project, archives the idea, triggers bridge discovery on the new project, sends notification
- **ARCHIVE_GOAL**: Creates an InsightNode with the archival reason, recalculates network health, sends "GOAL_DRIFT" notification

Every action is recorded in the `actions` table with full audit trail: action type, status, parameters, result, and timestamp.

### The Outcome Tracker

Outcomes provide feedback loops by recording the actual results of decisions, goals, and commitments:

```python
class Outcome(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    node_id: str
    node_type: str
    outcome_text: str
    rating: OutcomeRating  # POSITIVE, NEUTRAL, NEGATIVE, MIXED
    evidence: list[str] = Field(default_factory=list)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

When you record an outcome for a decision ("Skipping the hackathon turned out well — I got 92% on the midterm"), the system updates the decision node's confidence and deposits the outcome as a verified fact. This creates a **feedback loop**: future analysis by the Strategist can reference past outcomes to improve recommendations.

### Pattern Detection Engine

The PatternEngine runs 11 behavioral detectors that scan the entire knowledge graph:

```python
class PatternEngine:
    def detect_all(self) -> list[dict]:
        detectors = [
            self.detect_commitment_patterns,        # Overcommitting? Completion rate?
            self.detect_goal_lifecycle_patterns,     # Goals stalling? Abandonment rate?
            self.detect_temporal_patterns,           # Activity spikes? Dead zones?
            self.detect_cross_network_correlations,  # Which networks co-activate?
            self.detect_relationship_patterns,       # Neglected relationships?
            self.detect_outcome_patterns,            # Mostly positive? Negative?
            self.detect_decision_quality_patterns,   # Good decisions? Bad patterns?
            self.detect_goal_alignment_patterns,     # Goals aligned across networks?
            self.detect_commitment_scope_patterns,   # Scope creep? Over-promising?
            self.detect_idea_maturity_patterns,      # Ideas stuck as seeds?
            self.detect_network_balance_patterns,    # Lopsided attention?
        ]
        for detector in detectors:
            results = detector()
            patterns.extend(results)
        return patterns
```

Each pattern has a type, description, confidence score, severity (INFO/WARNING/CRITICAL), and a suggested action.

The confidence formula balances data volume with signal strength:

```python
def _compute_confidence(data_points: int, signal_strength: float) -> float:
    volume_ratio = min(data_points / 20, 1.0)  # 20 data points = max base
    base = 0.25 + 0.30 * volume_ratio           # base range: 0.25-0.55
    return min(0.95, base + signal_strength * 0.4)  # signal adds up to 0.4
```

Example patterns:
- **commitment_pattern** (WARNING): "Commitment completion rate is 35% (7/20). Consider reducing new commitments."
- **network_balance** (INFO): "ACADEMIC network has 45% of all nodes. Consider diversifying attention."
- **idea_maturity** (INFO): "8 ideas are still at SEED stage after 30+ days. Consider developing or archiving them."
- **relationship_pattern** (WARNING): "3 close contacts have not been interacted with in 14+ days."

> **CSC148 Connection:** Pattern detection is **graph-wide analysis** — iterating over all nodes and edges to compute aggregate statistics. This is O(V + E) for most detectors. The confidence model is a **bounded function** that maps inputs to [0.15, 0.95], similar to how you analyze function ranges in CSC148. The stale pattern lifecycle (auto-resolve after TTL) is a **garbage collection** mechanism.

---

## Part 12: Investigation, Timeline, and People Intel

### Investigation Engine

The Investigation Engine provides interactive deep-link analysis:

#### Expand: Filtered Neighborhood Traversal

```python
def expand(self, node_id, hops=1, node_types=None, edge_types=None, networks=None):
    """Get filtered neighborhood around a node, enriched with context."""
    result = self.repo.get_filtered_neighborhood(
        node_id=node_id, hops=hops,
        node_types=node_types, edge_types=edge_types, networks=networks,
    )
    # Enrich each node with decay score, health context, outcome status
    for node_data in result["nodes"]:
        enrichment = {
            "decay_score": node_data.get("decay_score", 1.0),
            "network_health": health_status,
            "has_outcomes": len(outcomes) > 0,
        }
        node_data["enrichment"] = enrichment
    return result
```

#### Find Path: BFS Shortest Path

```python
def find_path(self, source_id: str, target_id: str, max_depth: int = 6) -> dict:
    """Find shortest path between two nodes, enriched with edge semantics."""
    path = self.repo.find_shortest_path(source_id, target_id, max_depth=max_depth)

    if path is None:
        return {"found": False, "path": [], "nodes": [], "hops": []}

    # Fetch node details and edge information for each hop
    nodes_map = self.repo.get_nodes_batch(path)
    hops = []
    for i in range(len(path) - 1):
        edges = self.repo.get_edges_between(path[i], path[i + 1])
        hops.append({
            "from": {"id": path[i], "title": nodes_map[path[i]].title},
            "to": {"id": path[i+1], "title": nodes_map[path[i+1]].title},
            "edge": {"edge_type": edges[0].edge_type.value, ...} if edges else None,
        })

    return {"found": True, "path": path, "nodes": nodes, "hops": hops}
```

> **CSC148 Connection:** `find_path` uses **BFS** — the same algorithm you implement in CSC148 labs. BFS guarantees the shortest path in an unweighted graph. The `max_depth` parameter bounds the search space, preventing exploration of the entire graph for disconnected nodes. The `repo.find_shortest_path()` implementation uses a queue-based BFS traversal — you could implement this yourself with a `deque` from the `collections` module.

#### Find Common: Shared Connections

```python
def find_common(self, node_ids: list[str]) -> list[dict]:
    """Find entities connected to ALL specified nodes."""
    return self.repo.get_shared_connections(node_ids)
```

This finds nodes that are in the intersection of all specified nodes' neighborhoods — for example, finding shared contacts between two people.

### Timeline Engine

#### Causal Chain Tracing (BFS Along Temporal Edges)

The Timeline Engine traces causal chains by performing BFS specifically along temporal edge types:

```python
def trace_causal_chain(self, node_id, direction="both", max_depth=5):
    """BFS along temporal edges to reconstruct causal chains."""
    forward_types = ["EVOLVED_INTO", "TRIGGERED"]
    backward_types = ["PRECEDED_BY"]

    visited = {node_id}
    queue = deque([(node_id, 0)])
    chain_nodes = [node_id]
    chain_edges = []

    while queue:
        current_id, depth = queue.popleft()
        if depth >= max_depth:
            continue

        neighbors = []
        if direction in ("forward", "both"):
            neighbors.extend(
                self.repo.get_temporal_neighbors_directed(
                    current_id, direction="forward", edge_types=forward_types
                )
            )
        if direction in ("backward", "both"):
            neighbors.extend(
                self.repo.get_temporal_neighbors_directed(
                    current_id, direction="backward", edge_types=backward_types
                )
            )

        for neighbor in neighbors:
            nid = neighbor["node_id"]
            if nid not in visited:
                visited.add(nid)
                chain_nodes.append(nid)
                chain_edges.append({...})
                queue.append((nid, depth + 1))

    return {"nodes": nodes, "edges": chain_edges}
```

> **CSC148 Connection:** This is a **textbook BFS implementation** from CSC148. The `deque` acts as a FIFO queue. The `visited` set prevents revisiting nodes (avoiding infinite loops in cyclic graphs). The `depth` counter limits traversal depth. The key insight: by filtering edges to only temporal types (EVOLVED_INTO, TRIGGERED, PRECEDED_BY), we turn a general graph traversal into a **causal chain reconstruction** — following the chain of events through time.

#### Activity Burst Detection

```python
def detect_activity_bursts(self, window_days=7, threshold=2.0):
    """Find periods with above-average node creation."""
    # Bucket nodes by day
    daily_counts: dict[str, int] = defaultdict(int)
    for n in nodes:
        day = n["created_at"][:10]
        daily_counts[day] += 1

    avg = sum(daily_counts.values()) / max(len(daily_counts), 1)
    burst_threshold = avg * threshold  # 2x average = burst

    # Sliding window detection
    bursts = []
    for i in range(len(sorted_days)):
        window_count = sum(daily_counts[sorted_days[j]] for j in range(i, i + window_days))
        if window_count / window_days > burst_threshold / window_days:
            bursts.append({"start": sorted_days[i], "node_count": window_count, ...})
```

This detects periods when you were unusually active — for example, a burst of 15 captures during midterm week when your average is 3 per week.

### People Intelligence Engine

The People Intel Engine computes **relationship strength** using 5 weighted signals:

```python
SIGNAL_WEIGHTS = {
    "edge_weight": 0.25,           # Cosine similarity between node embeddings
    "edge_confidence": 0.15,       # How confident is the relationship?
    "edge_type_importance": 0.20,  # COLLABORATES_WITH = 1.0, KNOWS = 0.6
    "recency": 0.25,               # Exponential decay with 35-day half-life
    "shared_connections": 0.15,    # Log-scaled count of mutual connections
}
```

The recency signal uses exponential decay:

```python
def _compute_recency(updated_at):
    days_ago = (now - updated_at).total_seconds() / 86400
    return math.exp(-0.693 * days_ago / 35.0)  # 35-day half-life
```

The shared connections signal uses logarithmic scaling:

```python
def _compute_shared_connections_score(count):
    capped = min(count, 5)
    return math.log(1 + capped) / math.log(6)  # normalized to ~1.0
```

> **CSC148 Connection:** The relationship strength formula is a **weighted sum with heterogeneous signals** — the same concept behind any scoring or ranking algorithm. The logarithmic scaling of shared connections prevents one popular node from dominating the score (diminishing returns). The exponential recency decay is the same formula from the decay scoring engine but with a different half-life. These mathematical functions are the building blocks you analyze in CSC148's complexity discussions.

---

## Part 13: The CLI Interface

### Architecture: REPL Pattern

Memora uses a terminal-only CLI built with ANSI escape codes — no web frontend, no React, no browser. The interface follows the classic **Read-Eval-Print Loop (REPL)** pattern:

```python
class MemoraApp:
    """Main CLI application."""

    def __init__(self):
        self.settings: Settings | None = None
        self.repo: GraphRepository | None = None
        self._pipeline = None
        self._orchestrator = None
        self._strategist = None

    def boot(self):
        """Initialize settings & repo with staged boot sequence."""
        self.settings = load_settings()
        self.repo = GraphRepository(db_path=self.settings.db_path)
        # ... check subsystem status, display boot sequence

    def run(self):
        self.boot()
        while True:                              # LOOP
            telemetry = self._gather_telemetry()
            command_deck(**telemetry)             # PRINT (display dashboard)
            choice = prompt("memora > ")         # READ

            if choice in ("q", "quit", "exit"):
                break
            elif choice == "c":                  # EVAL (dispatch)
                from cli.commands.capture import cmd_capture
                cmd_capture(self)
            elif choice == "d":
                from cli.commands.dossier import cmd_dossier
                cmd_dossier(self)
            # ... 20 subcommands total
```

> **CSC148 Connection:** This is the **REPL pattern** — Read-Eval-Print-Loop — the same pattern as the Python interpreter itself. The command dispatch uses **lazy imports** (`from cli.commands.capture import cmd_capture` inside the branch) to avoid loading all 20 command modules at startup. This is an optimization pattern: load code only when needed, reducing startup time.

### Lazy Subsystem Initialization

Subsystems are initialized on first use, not at boot:

```python
def _get_embedding_engine(self):
    """Lazily initialize the embedding engine."""
    if not hasattr(self, '_embedding_engine') or self._embedding_engine is None:
        from memora.vector.embeddings import EmbeddingEngine
        self._embedding_engine = EmbeddingEngine(
            model_name=self.settings.embedding_model,
            cache_dir=self.settings.models_dir,
        )
    return self._embedding_engine

def _get_vector_store(self):
    """Lazily initialize the vector store."""
    if not hasattr(self, '_vector_store') or self._vector_store is None:
        from memora.vector.store import VectorStore
        self._vector_store = VectorStore(db_path=self.settings.vector_dir)
    return self._vector_store
```

The embedding model (all-mpnet-base-v2) takes several seconds to load. By deferring initialization to first use, the CLI boots instantly and only loads the model when you first invoke a command that needs embeddings.

> **CSC148 Connection:** This is the **lazy initialization** pattern — a form of **memoization**. The first call to `_get_embedding_engine()` does the expensive work; subsequent calls return the cached object in O(1). The `hasattr` check handles both the "never initialized" and "initialized to None" cases.

### The 20 Subcommands

| Key | Command | Description |
|---|---|---|
| c | capture | Capture new text, run 9-stage pipeline |
| p | profile | Set/view your profile (the You node) |
| r | proposals | Review pending graph proposals |
| d | dossier | Search nodes, view details |
| i | investigate | Deep link analysis, path finding |
| w | browse | Browse graph by type or network |
| s | search | Search (routes to dossier) |
| b | briefing | Generate daily briefing |
| k | critique | Challenge a statement (Strategist critic mode) |
| u | council | Full AI council deliberation |
| t | timeline | Chronological view, causal chains |
| o | outcomes | Record and view outcomes |
| a | patterns | View detected behavioral patterns |
| g | stats | Graph statistics and metrics |
| n | networks | Network health overview |
| e | people | People directory and relationship strength |
| j | actions | Execute typed graph actions |
| 0 | settings | View current configuration |
| x | clear | Clear all data (destructive) |
| q | quit | Exit Memora |

### Palantir-Inspired Terminal Rendering

The rendering module provides a Palantir Gotham-inspired visual design using ANSI 256-color escape codes:

```python
class C:
    """ANSI color codes -- Palantir-inspired 256-color palette."""
    BASE    = "\033[38;5;253m"   # Light silver text
    FRAME   = "\033[38;5;240m"   # Dim borders
    ACCENT  = "\033[38;5;39m"    # Primary cyan -- active UI
    SIGNAL  = "\033[38;5;214m"   # Amber gold -- alerts
    CONFIRM = "\033[38;5;84m"    # Green -- healthy
    DANGER  = "\033[38;5;196m"   # Red -- critical
    INTEL   = "\033[38;5;183m"   # Soft violet -- AI outputs
    DIM     = "\033[38;5;243m"   # Descriptions, metadata
```

The rendering module provides:
- **Box drawing** with Unicode characters for clean layouts
- **Tables** with aligned columns
- **Progress bars** for pipeline tracking
- **Sparklines** for compact data visualization
- **Health bars** with color-coded status
- **ASCII graph visualization** for showing node neighborhoods

### Pipeline Progress Tracker

The CLI tracker provides live visualization of the 9-stage pipeline:

```
  Pipeline Progress:
  [1] Raw Input         done
  [2] Preprocessing     done
  [3] Extraction        running...
  [4] Entity Resolution pending
  ...
```

The `on_stage` callback from the pipeline runner feeds into the tracker, updating the display in real-time as each stage completes.

---

## Part 14: Putting It All Together — Full Walkthrough

### Scenario: Monday Morning

It is 7:30 AM on a Monday. You open your terminal and type `python cli.py`.

**Step 1: Boot Sequence**

The MemoraApp boots with a staged initialization:

```
  +==========================================+
  |           M E M O R A                     |
  |     Personal Knowledge Graph Engine       |
  +==========================================+

  Subsystem Status:
    [ONLINE]   Graph Engine (DuckDB)
    [ONLINE]   Vector Store (Weaviate)
    [STANDBY]  Embedding Engine (loads on first use)
    [ONLINE]   AI Council (OpenAI configured)
    [ONLINE]   Scheduler (10 jobs registered)
```

**Step 2: Command Deck**

The main screen displays live telemetry:

```
  ===================================================
  Graph: 847 nodes | 1,923 edges | density: 0.0054

  Network Health:
    ACADEMIC        ========.. ON_TRACK (UP)
    PROFESSIONAL    ======.... NEEDS_ATTENTION (STABLE)
    SOCIAL          ========.. ON_TRACK (DOWN)

  Pending: 2 proposals | 1 alert
  ===================================================
```

**Step 3: Check Your Briefing (press `b`)**

The BriefingCollector aggregates from all subsystems. The Strategist generates:

```
  Summary: A mixed start to the week. You have 3 overdue commitments
  and 2 approaching deadlines, but your ACADEMIC network shows upward
  momentum with strong goal progress.

  Urgent:
  - Commitment "Review Sam's A2 code" was due Friday -- now 3 days overdue
  - Midterm prep goal at 65% with exam in 5 days

  People Follow-up:
  - Sam Chen: last interaction 4 days ago (close contact threshold: 7 days)
  - Prof. Liu: mentioned office hours opportunity 2 weeks ago, no follow-up

  Patterns:
  - Commitment completion rate is 58% in ACADEMIC (below 70% threshold)
  - Activity burst detected last week: 23 nodes created (avg: 8/week)
```

**Step 4: Capture New Information (press `c`)**

You type: "Just finished reviewing Sam's A2 code. His BFS implementation was clean but the DFS had a bug in the visited set logic. Promised to pair program with him Wednesday to fix it."

The 9-stage pipeline runs:

1. **Preprocessing**: "Wednesday" normalizes to "2026-03-04"
2. **Extraction**: Archivist produces a GraphProposal with:
   - EventNode: "Reviewed Sam's A2 code"
   - CommitmentNode: "Pair program with Sam" (due: 2026-03-04)
   - NoteNode: "Sam's DFS had visited set bug"
   - ConceptNode: "DFS visited set logic"
   - Edges: You --COMMITTED_TO--> "Pair program", Event --RELATED_TO--> "BFS", Event --RELATED_TO--> "DFS"
3. **Entity Resolution**: "Sam" matches existing PersonNode "Sam Chen" (exact name match, score 1.0 -> forced MERGE). "BFS" matches existing ConceptNode (embedding similarity 0.97 -> MERGE).
4. **Proposal Assembly**: Merge decisions applied. Sam's node gets updated with new interaction timestamp. BFS concept node updated.
5. **Validation Gate**: Confidence 0.88 >= 0.85 threshold, with merges -> route EXPLICIT (human review for merge safety)
6. **Review**: Proposal stored, you confirm the merges
7. **Graph Commit**: Atomic DuckDB transaction creates 3 new nodes, 5 new edges, updates 2 existing nodes
8. **Post-Commit**:
   - Embeddings generated for 3 new nodes
   - Edge weights computed from cosine similarity
   - Bridge discovery: "DFS visited set logic" (ACADEMIC) bridges to your "Debugging techniques" note (PROFESSIONAL)
   - Health recalculated: ACADEMIC network completion rate improves (you completed a commitment)
   - Truth layer: "Sam's DFS had a bug in visited set logic" deposited as fact
   - Overdue commitment "Review Sam's A2 code" can now be completed

**Step 5: Complete the Overdue Commitment (press `j`)**

You select "Review Sam's A2 code" and choose COMPLETE_COMMITMENT:

```python
# Action execution:
# 1. Precondition check: status == OPEN? Yes
# 2. Update node properties: status -> COMPLETED, completed_at -> now
# 3. Record action in audit trail
# 4. Side effects:
#    - Recalculate ACADEMIC network health (completion rate increases)
#    - Send COMMITMENT_COMPLETED notification
```

**Step 6: Investigate Connections (press `i`)**

You investigate the path between "Sam Chen" and "Debugging techniques":

```
  Path found (3 hops):

  Sam Chen --[KNOWS]--> You --[RELATED_TO]--> DFS visited set logic
           --[BRIDGES]--> Debugging techniques

  This cross-network bridge connects ACADEMIC and PROFESSIONAL:
  Your CSC148 debugging experience directly applies to work projects.
```

This demonstrates BFS shortest path finding across the knowledge graph — the exact algorithm from your CSC148 course, applied to navigating your own life.

### The Feedback Loop

Over time, the system builds increasingly accurate models:

1. **More data** -> Better entity resolution (more signals to match against)
2. **More outcomes recorded** -> Better pattern detection
3. **More interactions** -> More accurate relationship strength scores
4. **More verified facts** -> Better contradiction detection
5. **More bridges discovered** -> Richer cross-network insights

Each piece of information you capture makes the entire system smarter. The knowledge graph is not just storing data — it is learning the structure of your life.

---

## Summary: CSC148 in Production

Every concept from CSC148 appears in Memora:

| CSC148 Concept | Where It Appears |
|---|---|
| **Classes and OOP** | BaseNode hierarchy, 12 specialized node types, Pydantic models |
| **Inheritance** | EventNode(BaseNode), PersonNode(BaseNode), etc. |
| **Composition** | MemoraApp has-a Repository, Pipeline, Orchestrator |
| **Abstract Data Types** | NodeFilter, Subgraph, GraphProposal with invariants |
| **Hash Tables** | Entity resolution WEIGHTS dict, command dispatch, NODE_TYPE_MODEL_MAP |
| **Trees** | LangGraph state machine (tree of processing paths) |
| **Graphs** | The entire knowledge graph: 12 node types, 29 edge types, 7 categories |
| **BFS** | Shortest path finding, causal chain tracing, graph connectivity |
| **DFS** | Neighborhood expansion (recursive exploration of connected nodes) |
| **Stacks** | Exception handling chain in pipeline (errors unwind to caller) |
| **Queues** | BFS implementation uses `deque` as FIFO queue |
| **Recursion** | Neighborhood hops, decay computation, graph traversal |
| **Big-O Analysis** | Vector search O(log n), keyword matching O(K*W), BFS O(V+E) |
| **Enums** | NodeType, EdgeType, NetworkType, CommitmentStatus, etc. |
| **State Machines** | Pipeline stages, SM-2 repetition, LangGraph orchestration |
| **Sorting** | Entity resolution candidates sorted by score, timeline ordering |
| **Linked Structures** | Edge list representation of the graph in DuckDB |

The difference between a toy CSC148 assignment and a production system like Memora is not the algorithms — it is the **composition** of algorithms into a coherent system, the **error handling** at every boundary, the **validation** of inputs and outputs, and the **thoughtful design** of data models that support long-term evolution.

Every class, every function, every data structure in Memora exists because a CSC148 concept made it possible.

---

*This lecture reflects the actual implemented Memora codebase as of March 2026. All code examples are drawn from the real source files, not design documents.*
