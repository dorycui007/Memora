# Memora — Exhaustive Implementation Plan

> **Version:** 1.0
> **Date:** February 27, 2026
> **Derived from:** ARCHITECTURE.md v1.0
> **Total Estimated Duration:** 16 weeks (solo developer)

---

## Table of Contents

- [Phase 0: Project Bootstrap](#phase-0-project-bootstrap)
- [Phase 1: Foundation — Data Layer & Core Models (Weeks 1–2)](#phase-1-foundation--data-layer--core-models-weeks-12)
- [Phase 2: Extraction Pipeline — Archivist & Entity Resolution (Weeks 3–4)](#phase-2-extraction-pipeline--archivist--entity-resolution-weeks-34)
- [Phase 3: Graph Commit & Truth Layer (Weeks 4–5)](#phase-3-graph-commit--truth-layer-weeks-45)
- [Phase 4: Intelligence Layer — Orchestrator, Strategist, Researcher (Weeks 6–7)](#phase-4-intelligence-layer--orchestrator-strategist-researcher-weeks-67)
- [Phase 5: Background Mechanics — The Living Graph Engine (Weeks 8–9)](#phase-5-background-mechanics--the-living-graph-engine-weeks-89)
- [Phase 6: Frontend Foundation (Weeks 10–11)](#phase-6-frontend-foundation-weeks-1011)
- [Phase 7: Frontend Intelligence Views (Weeks 12–13)](#phase-7-frontend-intelligence-views-weeks-1213)
- [Phase 8: Frontend Polish & Integration (Weeks 14–16)](#phase-8-frontend-polish--integration-weeks-1416)
- [Cross-Cutting Concerns](#cross-cutting-concerns)
- [Dependency Graph](#dependency-graph)
- [Risk Checkpoints](#risk-checkpoints)

---

## Phase 0: Project Bootstrap

**Goal:** Development environment fully operational, dependencies locked, CI skeleton ready.

### 0.1 Backend Setup
- [x] **`backend/pyproject.toml`** — Define project metadata, Python 3.12+ requirement
- [x] **`backend/requirements.txt`** — Pin all dependencies:
  - `fastapi>=0.115`, `uvicorn[standard]`, `websockets`
  - `pydantic>=2.0`, `pydantic-settings`
  - `duckdb>=1.0` (primary graph DB, RyuGraph/Kuzu as optional)
  - `lancedb>=0.6`
  - `sentence-transformers` (for BGE-M3 local embeddings)
  - `anthropic>=0.40` (Claude API SDK)
  - `langgraph>=0.2` (orchestrator)
  - `apscheduler>=3.10` (background jobs)
  - `python-multipart` (file uploads)
  - `httpx` (async HTTP for MCP)
  - `pytest`, `pytest-asyncio`, `pytest-cov`
- [x] **`backend/memora/config.py`** — Configuration management:
  - Load from `~/.memora/config.yaml` and environment variables
  - Settings: `claude_api_key`, `db_path`, `vector_path`, `embedding_model`, `auto_approve_threshold` (default 0.85), `decay_lambda` per network, `log_level`
  - Pydantic Settings model with validation
- [x] **`.env.example`** — Template with `ANTHROPIC_API_KEY`, `MEMORA_DATA_DIR`

### 0.2 Frontend Setup
- [x] **`frontend/package.json`** — Dependencies:
  - `react`, `react-dom`, `typescript`
  - `@sigmajs/react`, `graphology` (graph viz)
  - `@tiptap/react`, `@tiptap/starter-kit` (rich text editor)
  - `tailwindcss`, `postcss`, `autoprefixer`
  - `zustand` (state management)
  - `axios` or native fetch wrapper (API client)
- [x] **`frontend/vite.config.ts`** — Vite config with React plugin, proxy to `localhost:8000`
- [x] **`frontend/tailwind.config.ts`** — Tailwind setup with custom theme colors for 7 networks
- [x] **`frontend/tsconfig.json`** — Strict TypeScript config with path aliases

### 0.3 Docker (Optional)
- [x] **`docker-compose.yml`** — Services: `backend` (Python), `frontend` (Node), shared volume for `~/.memora`

### 0.4 Data Directory Initialization
- [x] Create `~/.memora/` structure on first run:
  ```
  ~/.memora/
  ├── config.yaml
  ├── graph/
  ├── vectors/
  ├── models/
  ├── captures/audio/
  ├── captures/images/
  ├── backups/
  └── logs/
  ```

---

## Phase 1: Foundation — Data Layer & Core Models (Weeks 1–2)

**Goal:** Graph DB, Vector DB, and all Pydantic domain models operational. Basic capture ingestion (text only).

### 1.1 Pydantic Domain Models (`backend/memora/graph/models.py`)
- [x] **Enums:**
  - `NodeType` — 12 types: EVENT, PERSON, COMMITMENT, DECISION, GOAL, FINANCIAL_ITEM, NOTE, IDEA, PROJECT, CONCEPT, REFERENCE, INSIGHT
  - `EdgeCategory` — 7 categories: STRUCTURAL, ASSOCIATIVE, PROVENANCE, TEMPORAL, PERSONAL, SOCIAL, NETWORK
  - `EdgeType` — 30+ subtypes (PART_OF, CONTAINS, SUBTASK_OF, RELATED_TO, INSPIRED_BY, CONTRADICTS, SIMILAR_TO, COMPLEMENTS, DERIVED_FROM, VERIFIED_BY, SOURCE_OF, EXTRACTED_FROM, PRECEDED_BY, EVOLVED_INTO, TRIGGERED, CONCURRENT_WITH, COMMITTED_TO, DECIDED, FELT_ABOUT, RESPONSIBLE_FOR, KNOWS, INTRODUCED_BY, OWES_FAVOR, COLLABORATES_WITH, REPORTS_TO, BRIDGES, MEMBER_OF, IMPACTS, CORRELATES_WITH)
  - `NetworkType` — 7 networks: ACADEMIC, PROFESSIONAL, FINANCIAL, HEALTH, PERSONAL_GROWTH, SOCIAL, VENTURES
  - `CommitmentStatus` — open, completed, overdue, cancelled
  - `GoalStatus` — active, paused, achieved, abandoned
  - `ProjectStatus` — active, paused, completed, abandoned
  - `IdeaMaturity` — seed, developing, mature, archived
  - `NoteType` — observation, reflection, summary, quote
  - `ComplexityLevel` — basic, intermediate, advanced
  - `Priority` — low, medium, high, critical
  - `FinancialDirection` — inflow, outflow
  - `HealthStatus` — on_track, needs_attention, falling_behind
  - `Momentum` — up, stable, down
  - `ProposalStatus` — pending, approved, rejected
  - `ProposalRoute` — auto, digest, explicit

- [x] **Node Models (Pydantic):**
  - `BaseNode` — shared properties: id (UUID), content_hash (SHA-256), created_at, updated_at, embedding (optional), confidence (0–1), networks (list[NetworkType]), human_approved (bool), proposed_by, source_capture_id, access_count, last_accessed, decay_score, review_date, tags
  - `EventNode(BaseNode)` — event_date, location, participants, event_type, duration, sentiment, recurring
  - `PersonNode(BaseNode)` — name, aliases, role, relationship_to_user, contact_info, organization, last_interaction
  - `CommitmentNode(BaseNode)` — due_date, status, committed_by, committed_to, priority, description
  - `DecisionNode(BaseNode)` — decision_date, options_considered, chosen_option, rationale, outcome, reversible
  - `GoalNode(BaseNode)` — target_date, progress (0–1), milestones, status, priority, success_criteria
  - `FinancialItemNode(BaseNode)` — amount, currency, direction, category, recurring, frequency, counterparty
  - `NoteNode(BaseNode)` — source_context, note_type
  - `IdeaNode(BaseNode)` — maturity, domain, potential_impact
  - `ProjectNode(BaseNode)` — status, start_date, target_date, team, deliverables, repository_url
  - `ConceptNode(BaseNode)` — definition, domain, related_concepts, complexity_level
  - `ReferenceNode(BaseNode)` — url, author, publication_date, source_type, citation, archived
  - `InsightNode(BaseNode)` — derived_from, actionable, cross_network, strength

- [x] **Edge Models (Pydantic):**
  - `Edge` — id, source_id, target_id, edge_type, edge_category, confidence, weight, bidirectional, properties, created_at, updated_at

- [x] **Pipeline Models (Pydantic):**
  - `TemporalAnchor` — occurred_at, due_at, temporal_type
  - `NodeProposal` — temp_id, node_type, title, content, properties, confidence, networks, temporal
  - `NodeUpdate` — node_id, updates, confidence, reason
  - `EdgeProposal` — source_id, target_id, edge_type, edge_category, properties, confidence, bidirectional
  - `EdgeUpdate` — edge_id, updates, confidence
  - `NetworkAssignment` — node_id, network, confidence
  - `GraphProposal` — source_capture_id, timestamp, confidence, nodes_to_create, nodes_to_update, edges_to_create, edges_to_update, network_assignments

- [x] **Capture Model:**
  - `Capture` — id, modality (text/voice/image), raw_content, processed_content, content_hash, language, metadata, created_at

### 1.2 Graph Ontology (`backend/memora/graph/ontology.py`)
- [x] Valid edge type → node type mapping (which edge types connect which node types)
- [x] Validation functions: `validate_edge(source_type, target_type, edge_type) -> bool`
- [x] Network classification rules and examples

### 1.3 Graph Database Setup (`backend/memora/graph/repository.py`)
- [x] **DuckDB initialization** — Create all tables from Section 4.1:
  - `captures` table with SHA-256 dedup
  - `nodes` table with all shared properties + JSON properties column
  - `edges` table with foreign keys, cascade deletes
  - `proposals` table with status tracking
  - `network_health` table
  - `bridges` table
  - All indexes (type, networks, content_hash, decay, review_date, etc.)
- [x] **CRUD operations:**
  - `create_node(node: BaseNode) -> UUID`
  - `get_node(node_id: UUID) -> BaseNode`
  - `update_node(node_id: UUID, updates: dict) -> BaseNode`
  - `delete_node(node_id: UUID) -> bool` (soft delete)
  - `query_nodes(filters: NodeFilter) -> list[BaseNode]` — filter by type, network, tags, date range, decay score
  - `create_edge(edge: Edge) -> UUID`
  - `get_edges(node_id: UUID, direction: str) -> list[Edge]`
  - `get_neighborhood(node_id: UUID, hops: int) -> Subgraph` — 1-2 hop subgraph
  - `create_capture(capture: Capture) -> UUID`
  - `create_proposal(proposal: GraphProposal) -> UUID`
  - `update_proposal_status(proposal_id: UUID, status: str) -> None`
  - `commit_proposal(proposal_id: UUID) -> bool` — atomic transaction
  - `get_graph_stats() -> dict` — node count, edge count, per-type breakdown
- [x] **Transaction support** — All-or-nothing commit for graph proposals
- [x] **Migration utilities** (`backend/memora/graph/migrations.py`) — Schema versioning

### 1.4 Vector Database Setup (`backend/memora/vector/store.py`)
- [x] **LanceDB initialization:**
  - Connect to `~/.memora/vectors`
  - Create `node_embeddings` table with schema: node_id, content, node_type, networks, dense (Vector[1024]), created_at
  - Create HNSW index (IVF_HNSW_SQ, cosine metric, 4 partitions, 16 sub-vectors)
- [x] **CRUD + Search operations:**
  - `upsert_embedding(node_id: str, content: str, node_type: str, networks: list, vector: list[float])`
  - `delete_embedding(node_id: str)`
  - `dense_search(query_vector: list[float], top_k: int, filters: dict) -> list[SearchResult]`
  - `hybrid_search(query_vector: list[float], query_text: str, top_k: int, filters: dict) -> list[SearchResult]` — reciprocal rank fusion of dense + sparse
  - `filtered_search(query_vector, node_type: str, networks: list[str]) -> list[SearchResult]`

### 1.5 Embedding Engine (`backend/memora/vector/embeddings.py`)
- [x] **BGE-M3 wrapper:**
  - Lazy-load BGE-M3 model (download on first use to `~/.memora/models/bge-m3/`)
  - `embed_text(text: str) -> dict` — returns `{"dense": float[1024], "sparse": dict}`
  - `embed_batch(texts: list[str]) -> list[dict]` — batch embedding for efficiency
  - CPU/GPU detection and fallback

### 1.6 Basic Capture Ingestion (Text Only)
- [x] **`POST /captures`** endpoint — accept text input, compute SHA-256 hash, check dedup, store raw capture
- [x] Return capture ID and status `"processing"`

### 1.7 API Foundation (`backend/memora/api/app.py`)
- [x] FastAPI app factory with CORS middleware (localhost origins)
- [x] Health check endpoint (`GET /api/v1/health`)
- [x] Include all route routers (captures, graph, proposals, council, networks, facts)
- [x] Uvicorn runner configuration
- [x] Lifespan handler for DB connections and model loading

### 1.8 Unit Tests — Phase 1
- [x] `test_models.py` — Validate all Pydantic models serialize/deserialize correctly
- [x] `test_repository.py` — CRUD operations on in-memory DuckDB
- [x] `test_vector_store.py` — Embedding upsert and search
- [x] `test_ontology.py` — Edge validation rules

---

## Phase 2: Extraction Pipeline — Archivist & Entity Resolution (Weeks 3–4)

**Goal:** Text capture → Archivist LLM extraction → Pydantic-validated GraphProposal → entity resolution.

### 2.1 Preprocessing Stage (`backend/memora/core/pipeline.py`)
- [x] **Text normalization:**
  - Date parsing ("next Tuesday" → ISO timestamp, "March 5" → `2026-03-05`)
  - Currency normalization ("5 bucks" → `$5.00`, "50k" → `$50,000`)
  - Name normalization ("Dr. Smith" → canonical form)
- [x] **Language detection** using BGE-M3 tokenizer or langdetect
- [x] **Content hash computation** (SHA-256) for deduplication
- [x] **Dedup check** against recent captures table

### 2.2 Archivist Agent (`backend/memora/agents/archivist.py`)
- [x] **System prompt construction** (5 components):
  1. Graph schema (static, cacheable) — all 12 node types with properties, all 30+ edge types with valid source/target constraints
  2. Network definitions (static, cacheable) — 7 networks with descriptions and classification examples
  3. Extraction rules (static, cacheable) — entity reference rules, confidence scoring guide, clarification protocol
  4. Output format (static, cacheable) — Pydantic GraphProposal JSON schema
  5. Dynamic context (variable) — RAG-retrieved recent nodes + user's capture text
- [x] **Prompt caching** — Use Anthropic API `cache_control` on static components (60–70% cost reduction)
- [x] **LLM invocation:**
  - Call Claude Haiku with structured output
  - Parse response into `GraphProposal` Pydantic model
  - Validate all node types, edge types, and property schemas
  - Handle malformed responses gracefully (retry with feedback)
- [x] **RAG context retrieval:**
  - Before calling LLM, query LanceDB for top-K similar existing nodes
  - Format existing nodes as context to prevent duplicate creation
- [x] **Clarification protocol:**
  - If Archivist sets `clarification_needed=true`, return clarification request to user instead of proposal

### 2.3 Archivist System Prompt (`backend/memora/agents/prompts/archivist_system.md`)
- [x] Write complete system prompt with all 5 components
- [x] Include edge type → node type constraint matrix
- [x] Include confidence scoring guidelines (0.9+ for explicit, 0.6–0.8 for inferences, <0.6 flag for review)
- [x] Include network classification examples for each of 7 networks
- [x] Include output JSON schema with examples

### 2.4 Entity Resolution (`backend/memora/core/entity_resolution.py`)
- [x] **Multi-signal resolution engine** with 6 weighted signals:
  1. **Exact name match** (weight 0.95) — normalized canonical name comparison
  2. **Embedding similarity** (weight 0.80, threshold >0.92) — BGE-M3 cosine similarity via LanceDB
  3. **Same context network** (weight 0.15) — bonus if overlapping networks
  4. **Temporal proximity** (weight 0.10) — mentioned within 7-day window
  5. **Shared relationships** (weight 0.20) — connected to same PERSON/EVENT nodes
  6. **LLM adjudication** (weight 0.90) — ask Archivist "same entity?" for ambiguous cases
- [x] **Weighted score computation** — combine signals into single confidence score
- [x] **Resolution outcomes:**
  - `MERGE` (confidence >= 0.85) — merge properties, keep all edges, log merge event
  - `CREATE` (confidence < 0.6) — create new node with full provenance
  - `LINK` (related but distinct) — create edge between entities
  - `DEFER` (confidence 0.6–0.85) — flag for human review with both candidates
- [x] **Merge logic:**
  - Property conflict resolution (keep most recent, flag conflicts)
  - Edge re-pointing (all edges from merged node → surviving node)
  - Audit log entry for merge event

### 2.5 Pipeline Orchestration (`backend/memora/core/pipeline.py`)
- [x] **9-stage pipeline implementation:**
  - Stage 1: Raw input capture (receive + timestamp + hash)
  - Stage 2: Preprocessing (normalize, detect language, dedup)
  - Stage 3: Archivist extraction (LLM → GraphProposal)
  - Stage 4: Entity resolution (multi-signal matching)
  - Stage 5: Graph proposal assembly (structured diff)
  - Stage 6: Validation gate (confidence routing)
  - Stage 7: Human review / auto-approve
  - Stage 8: Graph commit (atomic transaction)
  - Stage 9: Post-commit processing (embeddings, bridges, health)
- [x] **Pipeline status tracking** — each capture has a status (stage 1–9, completed, failed)
- [x] **Error handling** — retry logic, dead-letter queue for failed extractions
- [x] **Async execution** — pipeline runs asynchronously after capture is received

### 2.6 Validation Gate (`backend/memora/core/pipeline.py`)
- [x] **Confidence-based routing:**
  - `confidence >= 0.85` → auto-approve route
  - `confidence < 0.85` but no high-impact changes → digest route (batched for daily review)
  - High-impact changes (deletes, merges, contradictions) → explicit confirm route
- [x] **Impact assessment:**
  - Node deletion = always explicit
  - Node merge = always explicit
  - Contradiction with existing node = always explicit
  - New node creation = confidence-based
  - Property update = confidence-based

### 2.7 API Schemas (`backend/memora/api/schemas/`)
- [x] **`capture_schemas.py`:**
  - `CaptureCreate` — modality, content, metadata
  - `CaptureResponse` — id, status, pipeline_stage, created_at
  - `CaptureDetail` — full capture with linked proposals
- [x] **`proposal_schemas.py`:**
  - `ProposalResponse` — id, status, route, confidence, human_summary, created_at
  - `ProposalDetail` — full proposal data with diff visualization
  - `ProposalAction` — approve/reject with optional reason

### 2.8 Unit Tests — Phase 2
- [x] `test_pipeline.py` — Test all 9 stages with mock LLM responses
- [x] `test_entity_resolution.py` — Test all 6 signals individually and combined; test all 4 outcomes (MERGE, CREATE, LINK, DEFER)
- [x] `test_archivist.py` (integration) — Test with mock Claude API call using sample captures

---

## Phase 3: Graph Commit & Truth Layer (Weeks 4–5)

**Goal:** Proposals commit atomically to graph. Truth Layer stores verified facts. Post-commit processing generates embeddings and detects bridges.

### 3.1 Graph Commit (`backend/memora/graph/repository.py`)
- [x] **Atomic transaction:**
  - Begin transaction
  - Create all new nodes from proposal
  - Update all existing nodes from proposal
  - Create all new edges (validate against ontology)
  - Update all existing edges
  - Log provenance (which capture, which agent, approval status)
  - Commit or rollback on failure
- [x] **Proposal status update** — pending → approved/rejected with reviewer info

### 3.2 Proposal Review Endpoints (`backend/memora/api/routes/proposals.py`)
- [x] `GET /proposals` — List pending proposals with pagination, filter by route
- [x] `GET /proposals/{id}` — Full proposal detail with diff
- [x] `POST /proposals/{id}/approve` — Approve → trigger graph commit
- [x] `POST /proposals/{id}/reject` — Reject with optional reason
- [x] `PATCH /proposals/{id}` — Edit proposal before approving

### 3.3 Truth Layer (`backend/memora/core/truth_layer.py`)
- [x] **Schema:**
  - `verified_facts` table — claim, source_type (PRIMARY/SECONDARY/SELF_REPORTED), source_url, source_title, source_author, verified_at, expiry_type (STATIC/DYNAMIC), next_check_date, confidence, related_node_ids, created_by
  - `fact_checks` table — fact_id, check_type, result (confirmed/contradicted/inconclusive), source_url, evidence, checked_by, checked_at
- [x] **Fact CRUD:**
  - `deposit_fact(fact: VerifiedFact) -> UUID`
  - `get_fact(fact_id: UUID) -> VerifiedFact`
  - `query_facts(filters: dict) -> list[VerifiedFact]`
  - `get_stale_facts() -> list[VerifiedFact]` — DYNAMIC facts past next_check_date
  - `check_contradiction(claim: str, node_ids: list[UUID]) -> list[Contradiction]`
- [x] **Fact lifecycle management:**
  - STATIC facts never expire
  - DYNAMIC facts have configurable recheck intervals
  - Stale facts flagged for Researcher re-verification
- [x] **Fact-check gate:**
  - Extract factual claims from agent output
  - Cross-reference against Truth Layer
  - Attach verification status to each claim (verified, contradicted, unverified)

### 3.4 Truth Layer API (`backend/memora/api/routes/facts.py`)
- [x] `GET /facts` — Query verified facts with filters (source_type, related nodes)
- [x] `GET /facts/{id}` — Fact with full provenance chain
- [x] `GET /facts/stale` — Facts due for rechecking

### 3.5 Post-Commit Processing (`backend/memora/core/pipeline.py`)
- [x] **Embedding generation** — After commit, generate BGE-M3 embeddings for all new/updated nodes → upsert to LanceDB
- [x] **Incremental bridge detection** — New node's embedding compared against nodes in OTHER networks via HNSW (O(log N))
- [x] **Network health recalculation** — If new data affects commitment rates or alerts
- [x] **Notification trigger check** — Deadline approaching? Relationship decay? Goal drift?
- [x] **Truth Layer cross-reference** — Check new claims against verified facts

### 3.6 Graph API Endpoints (`backend/memora/api/routes/graph.py`)
- [x] `GET /graph/nodes` — Query nodes with filters (type, network, tags, date range)
- [x] `GET /graph/nodes/{id}` — Node with all properties and edges
- [x] `GET /graph/nodes/{id}/neighborhood` — 1–2 hop subgraph
- [x] `PATCH /graph/nodes/{id}` — Update node properties
- [x] `DELETE /graph/nodes/{id}` — Soft delete (generates explicit-confirm proposal)
- [x] `GET /graph/edges` — Query edges with filters (category, type)
- [x] `GET /graph/search` — Hybrid search (BM25 + dense vector fusion)
- [x] `GET /graph/stats` — Node count, edge count, per-type breakdown

### 3.7 Unit Tests — Phase 3
- [x] `test_graph_commit.py` — Atomic commit, rollback on failure, provenance logging
- [x] `test_truth_layer.py` — Fact CRUD, contradiction detection, staleness check

---

## Phase 4: Intelligence Layer — Orchestrator, Strategist, Researcher (Weeks 6–7)

**Goal:** Full AI Council operational with LangGraph orchestrator, Strategist analysis, and Researcher with MCP servers.

### 4.1 LangGraph Orchestrator (`backend/memora/agents/orchestrator.py`)
- [x] **Query classification:**
  - Capture input → route to Archivist
  - Analysis/decision query → route to Strategist
  - Needs external data → route to Researcher
  - Complex decision → council pattern (all 3 agents)
- [x] **LangGraph state graph:**
  - Define state schema (query, agent_outputs, confidence_scores, citations)
  - Define nodes: classify, archivist, strategist, researcher, synthesize
  - Define edges with conditional routing
- [x] **Multi-agent coordination:**
  - Parallel execution when agents are independent
  - Sequential when one agent depends on another's output
  - Deliberation rounds (max 2–3) for high-stakes queries
- [x] **Synthesis node:**
  - Confidence-weighted merging of agent outputs
  - Flag high disagreement for human review
  - Format final response with citations (graph nodes + verified facts)

### 4.2 Strategist Agent (`backend/memora/agents/strategist.py`)
- [x] **Tools available:**
  - Graph query (read nodes, edges, neighborhoods)
  - Network health scores
  - Bridge discovery results
  - Truth Layer lookup
- [x] **Capabilities:**
  - Cross-network bridge analysis — interpret bridge discovery results, identify patterns
  - Network health assessment — read computed health, momentum, alerts
  - Decision recommendations — graph context + Truth Layer → actionable recommendations
  - Priority ranking — order tasks by urgency, importance, cross-network impact
  - Temporal pattern detection — identify trends over time
  - Critic mode — challenge user assumptions and decisions using graph evidence
- [x] **Daily briefing generation:**
  - Input: network health scores, open alerts, bridge discoveries, commitment scan, SM-2 due items, gap detection
  - Output: structured briefing with 6 sections (network status, alerts, bridges, decision prompts, recommended actions, review items)
- [x] **System prompt** (`backend/memora/agents/prompts/strategist_system.md`)

### 4.3 Researcher Agent (`backend/memora/agents/researcher.py`)
- [x] **Query anonymization:**
  - Strip PII from graph context before external queries
  - Replace names with abstract patterns ("a colleague" instead of "Sam Chen")
  - Remove dates, locations, financial amounts from search queries
- [x] **MCP server integration** — tool definitions for each server
- [x] **Fact deposition:**
  - Parse research results into structured VerifiedFact objects
  - Source type classification (PRIMARY/SECONDARY)
  - Confidence assignment based on source quality
  - Deposit to Truth Layer
- [x] **System prompt** (`backend/memora/agents/prompts/researcher_system.md`)

### 4.4 MCP Server Configurations (`backend/memora/mcp/`)
- [x] **`google_search.py`** — Google Search MCP server wrapper (100 free/day)
- [x] **`brave_search.py`** — Brave Search fallback (2,000 free/month)
- [x] **`playwright_scraper.py`** — Full web scraping for deep research
- [x] **`semantic_scholar.py`** — Academic paper search + arXiv integration
- [x] **`github_mcp.py`** — Code and repository search
- [x] **`graph_mcp.py`** — Internal graph + vector DB as MCP tool (agent queries own graph)

### 4.5 Council Decision Pattern
- [x] **Implementation of the multi-agent deliberation flow:**
  1. User submits complex query
  2. Orchestrator decomposes into sub-queries
  3. Independent analysis: Archivist (context), Strategist (analysis), Researcher (external data) — run in parallel
  4. Optional deliberation rounds (Strategist reviews all findings, Archivist reviews analysis)
  5. Confidence-weighted synthesis
  6. Flag high disagreement for human review
  7. Return final recommendation with citations

### 4.6 Council API (`backend/memora/api/routes/council.py`)
- [x] `POST /council/query` — Submit query, streams response via WebSocket
- [x] `GET /council/briefing` — Get today's daily briefing (cached, regenerated daily)
- [x] `POST /council/critique` — Invoke critic mode on a decision/assumption

### 4.7 WebSocket Handler (`backend/memora/api/websocket.py`)
- [x] **WebSocket endpoint** `WS /api/v1/ws/stream`
- [x] Token-by-token streaming of agent responses
- [x] Metadata per token: agent name, confidence, citing nodes
- [x] Agent state updates: which agent is active, thinking, done
- [x] Error handling and connection management

### 4.8 SSE Handler
- [x] **SSE endpoint** `GET /api/v1/events`
- [x] Background event types: proposal_created, health_changed, bridge_discovered, briefing_ready
- [x] Client subscription management

### 4.9 Adaptive RAG Pipeline
- [x] **Query classifier:**
  - Simple factual → vector search only
  - Relationship → graph traversal + vector merge
  - Cross-network → multi-network graph walk
  - Complex decision → multi-step agentic RAG
- [x] **Hybrid search:**
  - Dense search (cosine similarity on BGE-M3 vectors)
  - Sparse search (BM25-compatible)
  - Reciprocal rank fusion of dense + sparse results
- [x] **CRAG (Corrective RAG):**
  - Quality assessment: top result relevance, result count, query term coverage
  - If poor quality → fall back to Researcher agent for web search
- [x] **Graph-augmented context expansion:**
  - Retrieve top-K nodes via hybrid search
  - 1-hop neighborhood expansion (connected nodes + edges)
  - Deduplicate expanded context
  - Rank by relevance to original query
- [x] **Truth Layer fact-check gate** before final response generation

### 4.10 Integration Tests — Phase 4
- [x] `test_council.py` — Full council query with mocked LLM responses
- [x] `test_rag_pipeline.py` — All 4 query types, CRAG fallback, context expansion

---

## Phase 5: Background Mechanics — The Living Graph Engine (Weeks 8–9)

**Goal:** All deterministic background jobs running on schedule. The graph is now a living, self-maintaining system.

### 5.1 APScheduler Setup (`backend/memora/scheduler/scheduler.py`)
- [x] Initialize APScheduler with job store (SQLite or in-memory)
- [x] Register all background jobs with their schedules
- [x] Graceful shutdown handling
- [x] Job execution logging

### 5.2 Job Registry (`backend/memora/scheduler/jobs.py`)
- [x] Register all jobs with schedules:
  - Decay scoring: daily (e.g., 2:00 AM)
  - Bridge discovery batch: daily (e.g., 3:00 AM)
  - Network health: every 6 hours
  - Commitment scan: daily (e.g., 6:00 AM)
  - Relationship decay: weekly (Sunday)
  - Spaced repetition: daily (e.g., 5:00 AM)
  - Gap detection: weekly (Sunday)
  - Daily briefing: daily (e.g., 7:00 AM)

### 5.3 Decay Scoring (`backend/memora/core/decay.py`)
- [x] **Exponential decay function:**
  ```
  decay_score(t) = e^(-λ · (t_now - t_last_access))
  ```
- [x] Configurable λ per network (default values: Academic=0.05, Professional=0.03, Financial=0.02, Health=0.05, Personal_Growth=0.04, Social=0.07, Ventures=0.03)
- [x] Batch update all node decay scores
- [x] Flag nodes below threshold for resurfacing
- [x] Update `decay_score` and trigger notifications for very decayed nodes

### 5.4 Bridge Discovery (`backend/memora/core/bridge_discovery.py`)
- [x] **Incremental mode** (per-capture):
  - New node's embedding → HNSW search against nodes in OTHER networks
  - Threshold: cosine similarity > 0.75 (configurable)
  - Store potential bridges in `bridges` table
- [x] **Daily batch mode:**
  - Nodes modified in last 24 hours → batch scan for cross-network bridges
  - Collect all high-similarity cross-network pairs
  - Single LLM call: "Here are N potential connections — which are meaningful?"
  - Update `bridges` table with LLM assessment (meaningful: bool, description: text)
- [x] **Bridge filtering:**
  - Remove duplicates (same pair in reverse)
  - Remove already-known bridges
  - Rank by similarity score

### 5.5 Network Health Scoring (`backend/memora/core/health_scoring.py`)
- [x] **Health computation per network:**
  - Commitment completion rate = completed / (completed + open + overdue)
  - Alert ratio = active alerts / total nodes in network
  - Staleness flags = commitments with no update in X days (only when commitments exist)
- [x] **Status determination:**
  - On Track: completion rate > 0.7, alert ratio < 0.1, no staleness
  - Needs Attention: completion rate 0.4–0.7, OR alert ratio 0.1–0.3
  - Falling Behind: completion rate < 0.4, OR alert ratio > 0.3, OR multiple staleness flags
- [x] **Momentum calculation:**
  - Compare current health to previous snapshot
  - Up: improved in last period
  - Stable: no significant change
  - Down: declined in last period
- [x] Store health snapshot in `network_health` table

### 5.6 Commitment Scan (`backend/memora/core/commitment_scan.py`)
- [x] Query all COMMITMENT nodes with status = "open"
- [x] Compare due_date against current date
- [x] Flag overdue commitments (due_date < now, status still "open")
- [x] Flag approaching deadlines (due within configurable window: 1, 3, 7 days)
- [x] Generate notification triggers

### 5.7 Relationship Decay (`backend/memora/core/relationship_decay.py`)
- [x] Query all PERSON nodes
- [x] Calculate days since `last_interaction`
- [x] Flag relationships beyond decay threshold (configurable per relationship type):
  - Close contacts: 7 days
  - Regular contacts: 14 days
  - Acquaintances: 30 days
- [x] Generate "You haven't mentioned X in Y days" notifications
- [x] Check for outstanding commitments to decaying contacts

### 5.8 Spaced Repetition — SM-2 (`backend/memora/core/spaced_repetition.py`)
- [x] **SM-2 algorithm implementation:**
  - Parameters per node: easiness_factor (default 2.5, min 1.3), repetition_number, interval, review_date
  - After review with quality rating (0–5):
    - Quality < 3 → reset interval to 1 day, restart repetition
    - Quality >= 3 → new_interval = old_interval * easiness_factor
    - Update easiness_factor: EF' = EF + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    - Clamp EF to minimum 1.3
  - First review: interval = 1 day
  - Second review: interval = 6 days
  - Subsequent: interval = previous_interval * easiness_factor
- [x] **Daily review queue:**
  - Query nodes where review_date <= today
  - Rank by priority (overdue first, then by easiness_factor ascending)
- [x] **Review API:**
  - `POST /api/v1/review/{node_id}` — submit quality rating, update SM-2 parameters

### 5.9 Gap Detection (`backend/memora/core/gap_detection.py`)
- [x] **Orphaned nodes** — nodes with zero edges
- [x] **Stalled goals** — GOAL nodes with status="active" but no PROGRESS edges in X days
- [x] **Dead-end projects** — PROJECT nodes with status="active" but no recent activity
- [x] **Isolated concepts** — CONCEPT nodes not linked to any practical application (EVENT, PROJECT, COMMITMENT)
- [x] **Unresolved decisions** — DECISION nodes with no `outcome` filled
- [x] Generate structured gap report

### 5.10 Network API (`backend/memora/api/routes/networks.py`)
- [x] `GET /networks` — All 7 networks with current health status, momentum
- [x] `GET /networks/{name}` — Network detail (nodes, health history, alerts, commitment stats)
- [x] `GET /networks/bridges` — Cross-network bridge discoveries

### 5.11 Notification System
- [x] **Notification model:** type, trigger_condition, message, related_node_ids, priority, created_at, read
- [x] **Trigger conditions:**
  - Deadline approaching (1, 3, 7 days)
  - Decaying relationships (threshold exceeded)
  - Stale commitments (overdue, open)
  - Network health drop
  - Cross-network alerts (new meaningful bridge)
  - Goal drift (progress stalled, timeline at risk)
  - Review queue (SM-2 items due)
- [x] **Notification delivery:** stored in DB, pushed via SSE

### 5.12 Unit Tests — Phase 5
- [x] `test_decay.py` — Exponential decay curves, batch updates, threshold flagging
- [x] `test_bridge_discovery.py` — Incremental and batch modes, duplicate filtering
- [x] `test_health_scoring.py` — All 3 statuses, momentum calculation, edge cases
- [x] `test_spaced_repetition.py` — SM-2 algorithm correctness, interval progression, edge cases (quality 0, quality 5, EF clamp)
- [x] `test_commitment_scan.py` — Overdue detection, approaching deadline detection
- [x] `test_gap_detection.py` — All gap types, empty graph case

---

## Phase 6: Frontend Foundation (Weeks 10–11)

**Goal:** Capture UI, proposal review, basic graph visualization working.

### 6.1 Frontend Types (`frontend/src/lib/types.ts`)
- [x] TypeScript interfaces mirroring all backend Pydantic models:
  - `GraphNode`, `GraphEdge`, `Capture`, `Proposal`, `NetworkHealth`, `Bridge`, `Notification`, `VerifiedFact`
  - All enums: `NodeType`, `EdgeCategory`, `NetworkType`, `CommitmentStatus`, etc.
  - `StreamToken` — agent streaming token with metadata
  - `Briefing` — daily briefing structure

### 6.2 API Client (`frontend/src/lib/api.ts`)
- [x] Axios/fetch wrapper with base URL `http://localhost:8000/api/v1`
- [x] All endpoint methods:
  - Captures: create, list, get, delete
  - Graph: queryNodes, getNode, getNeighborhood, updateNode, deleteNode, searchGraph, getStats
  - Proposals: list, get, approve, reject, edit
  - Council: query, getBriefing, critique
  - Networks: list, get, getBridges
  - Facts: list, get, getStale
- [x] WebSocket connection manager (connect, disconnect, message handler)
- [x] SSE connection manager (EventSource wrapper)
- [x] Error handling and retry logic

### 6.3 Zustand Stores (`frontend/src/stores/`)
- [x] **`graphStore.ts`:**
  - State: nodes Map, edges Map, selectedNodeId, viewMode (local/network/global)
  - Actions: fetchNodes, fetchNeighborhood, selectNode, setViewMode, updateNode
- [x] **`captureStore.ts`:**
  - State: isCapturing, currentModality, pendingCaptures
  - Actions: createCapture, setModality, clearPending
- [x] **`councilStore.ts`:**
  - State: isQuerying, activeAgents, streamTokens, currentBriefing
  - Actions: submitQuery, appendToken, fetchBriefing, clearStream
- [x] **`notificationStore.ts`:**
  - State: unread notifications, pendingProposals count, alerts
  - Actions: fetchNotifications, markRead, dismissAlert
- [x] **`networkStore.ts`:**
  - State: health (per-network), bridges
  - Actions: fetchHealth, fetchBridges

### 6.4 Capture UI (`frontend/src/components/capture/`)
- [x] **CaptureBar** — Always-visible capture input area
  - TipTap rich text editor for text input
  - Modality selector (text, voice, image)
  - Submit button with keyboard shortcut (Ctrl/Cmd+Enter)
  - Processing indicator (shows pipeline stage)
- [x] **VoiceCapture** — Audio recording component
  - Record/stop button with waveform visualization
  - Upload audio file alternative
  - Transcription preview (when backend supports Whisper)
- [x] **ImageCapture** — Image upload/screenshot component
  - Drag-and-drop zone
  - Paste from clipboard
  - Camera capture (if available)
  - Preview with OCR text overlay (when backend supports)

### 6.5 Proposal Review (`frontend/src/components/proposals/`)
- [x] **ReviewQueue** — List of pending proposals
  - Filter by route (auto/digest/explicit)
  - Sort by confidence, date, impact
  - Batch approve/reject
- [x] **ProposalCard** — Individual proposal summary
  - Human-readable summary
  - Confidence badge
  - Route indicator
  - Quick approve/reject buttons
- [x] **ProposalDetail** — Full proposal diff view
  - Nodes to create (green)
  - Nodes to update (yellow)
  - Edges to create (blue)
  - Network assignments
  - Edit before approving

### 6.6 Graph Visualization (`frontend/src/components/graph/`)
- [x] **GraphCanvas** — Sigma.js wrapper
  - WebGL-powered rendering (handles 10K+ nodes)
  - Node coloring by type (12 colors for 12 node types)
  - Edge coloring by category (7 colors for 7 categories)
  - Node sizing by access_count or decay_score
  - Default view: local neighborhood of selected node
- [x] **GraphControls** — Zoom, pan, reset, layout toggle
- [x] **NodeTooltip** — Hover preview (title, type, confidence, networks)
- [x] **GraphLayout** — Force-directed layout with network clustering

### 6.7 Views (`frontend/src/views/`)
- [x] **CaptureView** — Capture bar + recent captures list
- [x] **GraphView** — Graph canvas + node detail panel
- [x] **ReviewView** — Review queue with proposal cards
- [x] **Layout** — App shell with sidebar navigation, top bar, main content area

### 6.8 App Shell
- [x] Sidebar navigation (Capture, Graph, Networks, Briefing, Review, Council)
- [x] Top bar with notification badge + command palette trigger
- [x] Responsive layout

---

## Phase 7: Frontend Intelligence Views (Weeks 12–13)

**Goal:** Network dashboard, council chat with streaming, daily briefing view.

### 7.1 Network Dashboard (`frontend/src/components/network/`)
- [x] **NetworkGrid** — 7 network cards in responsive grid
- [x] **NetworkCard** — Per-network display:
  - Network name and icon
  - Health status badge (On Track / Needs Attention / Falling Behind) with color coding
  - Momentum arrow (up/stable/down)
  - Key metrics: commitment completion rate, alert count
  - Sparkline chart showing health over time
  - Click to drill into network detail
- [x] **NetworkDetail** — Full network view:
  - Node list filtered to this network
  - Health history chart
  - Active alerts
  - Commitments by status
  - Bridge connections to other networks

### 7.2 Council Chat (`frontend/src/components/council/`)
- [x] **CouncilChat** — Conversational AI interface
  - Message input with Cmd+Enter submit
  - Query mode selector (simple, council, critique)
  - Streaming response display (token-by-token)
- [x] **AgentResponse** — Individual agent contribution
  - Agent name and icon (Archivist, Strategist, Researcher)
  - Response text with citations
  - Confidence indicator
  - Collapsible reasoning section
- [x] **CitationLink** — Clickable reference to graph node or verified fact
  - Inline citation marker [1], [2]
  - Hover preview of cited node
  - Click to navigate to node detail
- [x] **StreamingIndicator** — Shows which agent is currently generating
- [x] **WebSocket integration** — connect, receive tokens, display progressively

### 7.3 Daily Briefing (`frontend/src/components/briefing/`)
- [x] **BriefingView** — Morning intelligence report
  - 6 collapsible sections:
    1. Network Status — per-network health cards with momentum
    2. Open Alerts — ranked by urgency
    3. Cross-Network Bridges — new discoveries in last 24h
    4. Decision Prompts — questions to answer today
    5. Recommended Actions — people to contact, deadlines to renegotiate
    6. Spaced Repetition — knowledge nodes due for review
  - Mark sections as read/done
  - Quick actions (snooze alert, approve action, start review)
- [x] **AlertCard** — Individual alert display
  - Icon by type (deadline, relationship, commitment, health, bridge, goal, review)
  - Message with relevant node links
  - Dismiss / snooze actions
- [x] **BridgeCard** — Cross-network bridge discovery
  - Source and target nodes with network badges
  - Similarity score
  - LLM description of why this connection matters
  - Confirm/dismiss bridge

### 7.4 Views
- [x] **NetworkDashboardView** — Network grid + selected network detail
- [x] **CouncilView** — Council chat full page
- [x] **BriefingView** — Daily briefing full page

---

## Phase 8: Frontend Polish & Integration (Weeks 14–16)

**Goal:** Command palette, keyboard-first UX, node detail, search, performance optimization, integration testing.

### 8.1 Command Palette (`frontend/src/components/common/`)
- [x] **CommandPalette** — Cmd+K modal overlay
  - Fuzzy search across nodes, captures, actions
  - Recent items section
  - Action categories: Navigate, Create, Search, Agent
  - Keyboard navigation (arrow keys, enter to select, esc to close)
- [x] **Command types:**
  - Navigate to node/view
  - Create new capture
  - Search graph
  - Query AI Council
  - Open network dashboard
  - View daily briefing

### 8.2 Node Detail (`frontend/src/components/graph/`)
- [x] **NodeDetailPanel** — Full node view
  - Title, type badge, confidence score
  - All type-specific properties displayed appropriately
  - Network membership badges
  - Decay score indicator
  - Provenance: source capture, proposed by agent, approval status
  - Tags with add/remove
  - Timestamps: created, updated, last accessed
- [x] **NodeEdges** — Connected edges list
  - Grouped by edge category
  - Edge type, target node, confidence, weight
  - Click to navigate to connected node
- [x] **NodeTimeline** — Temporal view of node's history
  - Creation, updates, access events
  - Related captures over time
- [x] **NodeActions** — Edit, delete, review, mark as reviewed (SM-2)

### 8.3 Search Integration
- [x] **SearchBar** — Global search component
  - Hybrid search (text + semantic)
  - Filter by node type, network
  - Results with relevance scores
  - Keyboard shortcut (Cmd+K → type to search)
- [x] **SearchResults** — Result list with node cards
  - Highlight matching text
  - Show node type, networks, confidence
  - Click to navigate

### 8.4 Keyboard-First UX
- [x] Global keyboard shortcuts:
  - `Cmd+K` — Command palette
  - `Cmd+N` — New capture
  - `Cmd+Enter` — Submit capture/query
  - `Cmd+B` — View daily briefing
  - `Cmd+/` — Toggle sidebar
  - Arrow keys — Navigate lists
  - `Esc` — Close modals, deselect
- [x] Focus management — logical tab order, focus rings

### 8.5 Real-Time Updates
- [x] SSE integration — listen for background events
  - New proposal notification badge
  - Health status changes update network cards
  - Bridge discoveries show toast notification
  - Briefing ready notification
- [x] Optimistic updates — show captures as processing immediately

### 8.6 Performance Optimization
- [x] React.memo on expensive components (GraphCanvas, NetworkGrid)
- [x] Virtual scrolling for long lists (node lists, proposal lists)
- [x] Debounced search input
- [x] Lazy loading for graph neighborhoods (load on demand)
- [x] WebSocket reconnection logic with exponential backoff

### 8.7 Integration Testing
- [x] End-to-end: text capture → pipeline → proposal → review → commit → graph update
- [x] Council query → streaming response → citations clickable
- [x] Network health updates reflected in dashboard
- [x] Bridge discovery notification → briefing section
- [x] SM-2 review flow → interval update → next review scheduled
- [x] Command palette search → navigate to result

### 8.8 Error Handling & Edge Cases
- [x] Empty states — "No captures yet", "No pending proposals", "No bridges found"
- [x] Loading states — skeleton loaders for all async operations
- [x] Error states — connection lost, API errors, LLM failures
- [x] Offline handling — queue captures when backend is unreachable

---

## Cross-Cutting Concerns

### Logging & Observability
- [x] Structured logging (JSON format) to `~/.memora/logs/`
- [x] Log levels: DEBUG, INFO, WARNING, ERROR
- [x] Pipeline stage logging with timing metrics
- [x] LLM call logging (prompt tokens, completion tokens, cost)
- [x] Background job execution logging

### Security
- [x] No auth for local-only MVP (localhost binding)
- [x] Claude API key stored in `~/.memora/config.yaml` (not in code)
- [x] Query anonymization before external API calls (Researcher agent)
- [x] No PII in logs sent to external services
- [x] CORS restricted to localhost origins

### Configuration
- [x] `~/.memora/config.yaml` schema:
  ```yaml
  claude_api_key: "sk-ant-..."
  auto_approve_threshold: 0.85
  decay_lambda:
    academic: 0.05
    professional: 0.03
    financial: 0.02
    health: 0.05
    personal_growth: 0.04
    social: 0.07
    ventures: 0.03
  relationship_decay_thresholds:
    close: 7
    regular: 14
    acquaintance: 30
  sm2_default_easiness: 2.5
  bridge_similarity_threshold: 0.75
  embedding_model: "BAAI/bge-m3"
  data_dir: "~/.memora"
  log_level: "INFO"
  ```

### Backup & Recovery
- [x] Periodic graph snapshots to `~/.memora/backups/`
- [x] Proposal audit trail enables replay
- [x] DuckDB WAL for crash recovery

---

## Dependency Graph

```
Phase 0 (Bootstrap)
    └── Phase 1 (Data Layer + Models)
        ├── Phase 2 (Archivist + Entity Resolution)
        │   └── Phase 3 (Graph Commit + Truth Layer)
        │       └── Phase 4 (Orchestrator + Strategist + Researcher)
        │           └── Phase 5 (Background Mechanics)
        │               └── Phase 6 (Frontend Foundation)
        │                   └── Phase 7 (Frontend Intelligence)
        │                       └── Phase 8 (Polish + Integration)
        └── Phase 1.5 (Vector DB + Embeddings) [parallel with Phase 2]
```

**Key parallel opportunities:**
- Vector DB setup (1.4–1.5) can run parallel with graph DB setup (1.3)
- Frontend types (6.1) can start as soon as backend models (1.1) are stable
- MCP servers (4.4) can be developed independently from agent logic (4.2–4.3)
- Background jobs (5.3–5.9) are independent of each other

---

## Risk Checkpoints

| Checkpoint | When | What to Validate | Go/No-Go Criteria |
|---|---|---|---|
| **RC1** | End of Week 2 | DuckDB + LanceDB operational, models serializing | Can create/read/search nodes |
| **RC2** | End of Week 3 | Archivist produces valid GraphProposal from text | >80% of test captures yield valid proposals |
| **RC3** | End of Week 4 | Entity resolution correctly merges/creates | <10% false merge rate on synthetic data |
| **RC4** | End of Week 5 | Full pipeline text→graph working end-to-end | Single capture flows through all 9 stages |
| **RC5** | End of Week 7 | Council query produces cited response | Strategist cites graph nodes in analysis |
| **RC6** | End of Week 9 | Background jobs running, briefing generated | Health scores computed, bridges found |
| **RC7** | End of Week 11 | Capture → graph visible in Sigma.js | User can capture text and see it in graph |
| **RC8** | End of Week 16 | Full MVP functional | All views working, <2s capture latency |

---

## File-to-Task Mapping

| File | Phase | Primary Responsibility |
|---|---|---|
| `backend/memora/graph/models.py` | 1.1 | All Pydantic domain models |
| `backend/memora/graph/ontology.py` | 1.2 | Edge-node validation rules |
| `backend/memora/graph/repository.py` | 1.3 | DuckDB CRUD + transactions |
| `backend/memora/graph/migrations.py` | 1.3 | Schema versioning |
| `backend/memora/vector/store.py` | 1.4 | LanceDB search interface |
| `backend/memora/vector/embeddings.py` | 1.5 | BGE-M3 embedding wrapper |
| `backend/memora/config.py` | 0.1 | Configuration management |
| `backend/memora/api/app.py` | 1.7 | FastAPI app factory |
| `backend/memora/api/websocket.py` | 4.7 | WebSocket streaming |
| `backend/memora/api/routes/captures.py` | 1.6, 3.6 | Capture endpoints |
| `backend/memora/api/routes/graph.py` | 3.6 | Graph CRUD endpoints |
| `backend/memora/api/routes/proposals.py` | 3.2 | Proposal review endpoints |
| `backend/memora/api/routes/council.py` | 4.6 | AI Council endpoints |
| `backend/memora/api/routes/networks.py` | 5.10 | Network health endpoints |
| `backend/memora/api/routes/facts.py` | 3.4 | Truth Layer endpoints |
| `backend/memora/api/schemas/*.py` | 2.7 | Request/response schemas |
| `backend/memora/core/pipeline.py` | 2.1, 2.5, 2.6, 3.5 | 9-stage pipeline |
| `backend/memora/core/entity_resolution.py` | 2.4 | Multi-signal matching |
| `backend/memora/core/decay.py` | 5.3 | Exponential decay |
| `backend/memora/core/bridge_discovery.py` | 5.4 | Cross-network bridges |
| `backend/memora/core/health_scoring.py` | 5.5 | Network health |
| `backend/memora/core/spaced_repetition.py` | 5.8 | SM-2 algorithm |
| `backend/memora/core/gap_detection.py` | 5.9 | Graph structural analysis |
| `backend/memora/core/commitment_scan.py` | 5.6 | Deadline monitoring |
| `backend/memora/core/relationship_decay.py` | 5.7 | Interaction analysis |
| `backend/memora/core/truth_layer.py` | 3.3 | Fact verification |
| `backend/memora/agents/archivist.py` | 2.2 | Graph writer agent |
| `backend/memora/agents/strategist.py` | 4.2 | Analysis agent |
| `backend/memora/agents/researcher.py` | 4.3 | Internet bridge agent |
| `backend/memora/agents/orchestrator.py` | 4.1 | LangGraph coordinator |
| `backend/memora/mcp/*.py` | 4.4 | MCP server wrappers |
| `backend/memora/scheduler/*.py` | 5.1–5.2 | Background job system |
| `frontend/src/lib/types.ts` | 6.1 | TypeScript type definitions |
| `frontend/src/lib/api.ts` | 6.2 | API client |
| `frontend/src/stores/*.ts` | 6.3 | Zustand state management |
| `frontend/src/components/capture/*` | 6.4 | Capture input UI |
| `frontend/src/components/proposals/*` | 6.5 | Review queue UI |
| `frontend/src/components/graph/*` | 6.6, 8.2 | Graph visualization |
| `frontend/src/components/network/*` | 7.1 | Network dashboard |
| `frontend/src/components/council/*` | 7.2 | AI chat interface |
| `frontend/src/components/briefing/*` | 7.3 | Daily briefing |
| `frontend/src/components/common/*` | 8.1 | Command palette, shared |

---

*End of Implementation Plan — Memora v1.0*
