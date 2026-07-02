# Extraction Pipeline

The 9-stage pipeline transforms raw text captures into structured graph data.

## Stages

### Stage 1: Raw Capture
Accept user input text and create a `PipelineState` with unique capture ID and content hash (SHA-256 dedup).

### Stage 2: Preprocessing
- Strip whitespace
- Resolve relative date references ("next Tuesday" -> ISO date)
- Detect and normalize currency amounts
- Compute content hash for deduplication

### Stage 3: Archivist Extraction
LLM-powered extraction via OpenAI Responses API with structured JSON schema output:
- RAG context: embed input text, search vector store for similar existing nodes
- Static system prompt (cacheable) + dynamic context in user message
- Returns a `GraphProposal` with nodes, edges, and network assignments

### Stage 4: Entity Resolution
6-signal weighted matching to prevent duplicate nodes:
1. **Name similarity** (fuzzy string matching)
2. **Embedding similarity** (cosine distance)
3. **Network overlap** (shared context networks)
4. **Temporal proximity** (creation timestamps)
5. **Relationship overlap** (shared edges)
6. **LLM confirmation** (tie-breaker for ambiguous cases)

Outcomes: MERGE (deduplicate) or CREATE (new node).

### Stage 5: Proposal Assembly
Merge entity resolution results into the final proposal, resolving ID conflicts.

### Stage 6: Validation Gate
Route proposals by confidence:
- **AUTO** (>= threshold): auto-approve
- **DIGEST**: batch for periodic review
- **EXPLICIT**: require immediate human review

### Stage 7: Human Review
For DIGEST/EXPLICIT routes, present proposal for user approval.

### Stage 8: Graph Commit
Atomic DuckDB transaction:
- Insert new nodes and edges
- Update existing nodes/edges
- Apply network assignments
- Store proposal record

### Stage 9: Post-Commit
Sequential dependencies first, then parallel:
1. **Embedding generation** (sequential - must complete first)
2. **Edge weight computation** (sequential - depends on embeddings)
3. **Graph connectivity check** (sequential - ensure You-node links)
4. **Bridge detection** (parallel)
5. **Health scoring** (parallel)
6. **Notifications** (parallel)
7. **Truth layer** (parallel)

## Error Handling

- Each stage catches failures independently
- Pipeline continues with warnings on non-critical failures
- Clarification protocol: if Archivist is uncertain, returns `clarification_needed=True`
- `PipelineState.validate()` checks invariants between stages
