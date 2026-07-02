# The New Memora

## What Memora Is

Memora is an intelligence analyst for your life.

You tell it what's happening — text, notes, observations, files. You are the field agent reporting in. Memora is the analyst that never sleeps. It extracts the entities and relationships buried in everything you give it, connects them into a living knowledge graph, and then runs continuous intelligence on that graph — decay scoring, bridge discovery, pattern detection, commitment tracking, relationship health — so that when you sit down at the terminal, everything you've fed it has already been analyzed, correlated, and cross-referenced against everything else.

This is not a note-taking app. This is not a second brain. Those are filing cabinets with a search bar. Memora is a situation room. The difference: a filing cabinet waits for you to open a drawer. A situation room tells you the building is on fire.

## The Principle

The value is in the overlay.

Individual texts, files, and calendar entries are commodity. You already have them scattered across apps, folders, and formats. What you don't have — what no tool gives you — is the layer that shows how they all connect.

Your meeting with a collaborator next Tuesday exists in your calendar. The deliverable you owe them exists in a note somewhere. The fact that the deliverable is overdue exists nowhere — until Memora correlates the commitment node with the calendar event, checks the deadline, and pushes an alert: *"Meeting with X in 2 hours, but deliverable to them is 3 days overdue."*

That's the overlay. Bloomberg charges $32,000/year to provide it over financial data. OSINT dashboards prove you don't need classified access to achieve it — you need aggregation, correlation, and a good interface. Memora provides it over the most valuable dataset that exists: your own life. Locally, privately, for free.

## Data Sources

You are the primary sensor. Memora ingests through a pluggable connector framework, but the highest-value input is you typing what you know:

**Direct capture — the primary source.** Type what happened, what you're thinking, what you decided. Raw text — the fastest path from thought to graph. *"Had lunch with Sara, she's leaving her job at Meridian next month. She mentioned a contract opportunity worth $40K."* That single sentence produces a Person node, an Event, a Financial Item, a Career transition, three relationships, and a deadline — all automatically. This is how most knowledge enters the graph, and it's the most powerful input because human observations carry context no file parser can match.

**Connectors extend your reach.** File-based sources amplify what you capture directly:

- **Markdown files and Obsidian vaults.** Point Memora at a directory. New notes, edited notes, journal entries — ingested, extracted, correlated with everything else in the graph. Frontmatter metadata is preserved.
- **Calendar files.** iCal `.ics` exports from any calendar app. Events become nodes. Attendees become people. Deadlines become commitments.
- **Plain text, CSVs, structured documents.** Any text-based format. The `BaseConnector` interface — `connect()`, `get_items()`, `transform()`, `sync()` — makes new data sources a matter of implementing four methods.

**File watchers (optional).** Configured directories can be monitored for changes, triggering automatic ingestion. This is an amplifier — it saves you from manually re-importing files you're already working with.

**People as implicit data sources.** Every Person node in the graph is also a data source. The watchlist turns your network into a live feed — Memora periodically checks for professional updates, role changes, and company moves for everyone you've mentioned. The graph doesn't just store people. It actively tracks them.

## The Intelligence Layer

Raw data becomes intelligence through a 9-stage extraction pipeline:

1. **Raw Input** — Text arrives, unprocessed.
2. **Preprocessing** — Metadata extraction, date resolution (*"next Monday"* becomes an actual date), currency normalization (*"50K"* becomes $50,000), language detection, content hashing for deduplication.
3. **Archivist Extraction** — The AI reads your text and proposes a graph structure: nodes to create, edges to draw, existing nodes to update. RAG context from the vector store ensures it knows what's already in the graph.
4. **Entity Resolution** — Six weighted signals determine whether a mentioned entity is someone new or someone you already know:
   - *Exact name matching* (weight 0.95) — title and alias comparison
   - *Embedding similarity* (weight 0.80) — semantic closeness in vector space
   - *Shared relationships* (weight 0.20) — common neighbors in the graph
   - *Same network* (weight 0.15) — overlapping domain membership
   - *Temporal proximity* (weight 0.10) — mentioned within a 7-day window
   - *LLM adjudication* (weight 0.90) — AI tiebreaker for ambiguous cases
5. **Proposal Assembly** — Merge decisions applied, temporary IDs resolved to real UUIDs.
6. **Validation Gate** — Confidence routing: high confidence (≥0.85) auto-approves, medium goes to digest, low requires explicit review.
7. **Review** — Auto-approved proposals commit immediately. Everything else enters the review queue.
8. **Graph Commit** — Atomic DuckDB transaction. The graph changes completely or not at all.
9. **Post-Commit Processing** — In parallel: embedding generation, edge weight computation, connectivity analysis (BFS reachability, orphan fixing, bridge detection), health scoring, notification triggers, truth layer cross-referencing for contradiction detection.

The result: a knowledge graph with 12 node types and 29 edge types, organized across 7 context networks.

**12 node types:** Event, Person, Commitment, Decision, Goal, Financial Item, Note, Idea, Project, Concept, Reference, Insight.

**29 edge types across 7 categories:**
- *Structural* — part_of, contains, subtask_of
- *Associative* — related_to, inspired_by, contradicts, similar_to, complements
- *Provenance* — derived_from, verified_by, source_of, extracted_from
- *Temporal* — preceded_by, evolved_into, triggered, concurrent_with
- *Personal* — committed_to, decided, felt_about, responsible_for
- *Social* — knows, introduced_by, owes_favor, collaborates_with, reports_to
- *Network* — bridges, member_of, impacts, correlates_with

**7 context networks:** Academic, Professional, Financial, Health, Personal Growth, Social, Ventures. Every node belongs to one or more. Health scores, decay, gaps, and bridges are computed per-network.

**Truth Layer.** Factual nodes above 0.8 confidence are automatically deposited as verified facts. The truth layer performs contradiction detection — if new information conflicts with established facts, you get an alert. Facts past their recheck date decay in confidence and are marked stale.

## Always-On Intelligence

The data collection is mostly you. The intelligence processing is always on.

Once knowledge is in the graph, thirteen background jobs continuously analyze, evolve, and surface insights from it — without new input required:

1. **Decay Scoring** — Every node decays over time. Recent, frequently-referenced knowledge stays strong. Old, isolated knowledge fades. This is how the graph stays alive instead of becoming a graveyard.
2. **Bridge Discovery** — Finds cross-network connections via embedding similarity, then validates them with AI. *"Your venture idea and your academic research share an underlying concept."*
3. **Network Health** — Computes health scores for all seven networks. Notifies on drops.
4. **Commitment Scanning** — Finds overdue and approaching commitments. Generates alerts.
5. **Relationship Decay** — Detects decaying relationships. Close relationships have stricter thresholds than casual ones.
6. **Spaced Repetition** — SM-2 algorithm computes a daily review queue of knowledge worth revisiting.
7. **Gap Detection** — Identifies knowledge gaps across all networks.
8. **Daily Briefing** — The Strategist agent synthesizes everything into a morning briefing.
9. **Outcome Review** — Finds decisions and goals that need outcome recording after 14 days.
10. **Confidence Decay** — Auto-reduces confidence for facts past their recheck date.
11. **Pattern Detection** — Runs all pattern detectors, surfaces significant findings.
12. **Connector Sync** — Periodically syncs configured data sources and processes new captures.
13. **Watchlist Scan** — Searches external sources for updates on people in the graph. Tiered frequency: close contacts weekly, regular biweekly, acquaintances monthly.

This is what "always-on" means: the graph evolves even when you're not adding to it. Decay shifts. Bridges emerge. Health scores change. Commitments go overdue. The intelligence layer runs on what you've already given it — and it never stops.

Every job run can trigger notifications — 14 distinct types:

- Deadline approaching, stale commitment, overdue items
- Relationship decay warnings
- Network health drops
- Bridge discoveries
- Goal drift and knowledge gaps
- Review queue readiness
- Outcome recording reminders
- Fact confidence decay
- Pattern detection results
- Connector sync summaries
- Truth contradictions
- Synthesized daily briefings
- Watchlist alerts (role changes, company changes, new activity)

The graph is never static. It breathes.

## The Watchlist

Every person in the graph is on the watchlist.

Memora doesn't just remember the people you tell it about — it watches them. The same Person nodes that drive relationship decay and commitment tracking become targets for periodic external intelligence. Memora constructs search queries from what it already knows — name, organization, role — and scans for changes. When someone in your graph changes jobs, takes a new role, or moves companies, Memora detects it before you hear about it.

**Tiered frequency, driven by relationship decay thresholds.** The closer the relationship, the more frequently Memora checks:

- **Close contacts** (partner, family, best friend) — weekly scans. These are the people whose changes matter most and fastest.
- **Regular contacts** (friends, colleagues, mentors) — biweekly scans. Professional and social connections worth tracking at moderate cadence.
- **Acquaintances** — monthly scans. Low-priority but still watched. A dormant contact's job change might be the trigger to reconnect.

**How it works.** LinkedIn is the primary source, accessed through existing MCP infrastructure — no API keys, no platform dependencies:

1. Constructs targeted search queries from Person node data — `"Sara Chen" + "Meridian Partners" + "Senior Analyst"` — using web search MCP tools (Google/Brave).
2. Discovers LinkedIn profiles and professional updates from search results.
3. Uses the Playwright scraper to extract profile details from discovered URLs.
4. Compares findings against stored facts in the Truth Layer — the system isn't looking for profiles, it's looking for *changes*.
5. Deposits new facts with source traceability and recheck intervals that match the scan tier.

Profile URLs, once discovered, are stored in the Person node's `contact_info` field. Subsequent scans skip the discovery step and scrape directly — faster, more reliable, less noise.

**Change detection and downstream effects:**

- **Role change detected** — notification fired, Person node properties updated, linked commitments and projects flagged for review (your deliverable to Sara might now route through someone else).
- **Company change** — notification fired, organization relationships updated, potential impact on projects and financial items linked to that person.
- **New public activity** (posts, publications, announcements) — deposited as linked Reference nodes with full provenance. The Truth Layer tracks when each fact was last verified.

**Privacy model.** Unlike the Researcher agent, which anonymizes all external queries to protect your data, the watchlist intentionally uses real names — that's the point. You told Memora about these people. Watching them is the job. But the privacy guarantees still hold where they matter:

- All searches and scraping happen locally. Results stay on your machine.
- No data about *you* leaves the machine — only queries about watched people.
- No accounts, no logins, no API keys. Public information only, accessed through web search and scraping.
- You control who's in the graph. The watchlist is exactly as broad as the people you've mentioned.

**The Palantir parallel.** Palantir gives intelligence analysts a unified picture of entities across data sources — every person, organization, and event cross-referenced into a single operational view. Memora does the same for your personal network. Every person, their current status, their trajectory, cross-referenced against your commitments, projects, and history with them. The difference: Palantir costs millions and requires a data team. Memora runs on your laptop.

## Situational Awareness

When you open Memora, the BriefingCollector has already assembled your situation across 13 dimensions:

**Health** — Current scores for every network. Professional thriving, health neglected, ventures stalling — at a glance.

**Urgent** — Overdue commitments. Decaying close relationships. Stale facts. The things that need attention now.

**Since Last Session** — New nodes, completed actions, discovered bridges since you last checked in.

**Upcoming** — Approaching deadlines, pending outcomes, items in the review queue.

**People** — Relationship decay status, interaction statistics. Who you're neglecting. Who you're over-indexing on.

**Patterns** — Active patterns the system has detected across your behavior and data.

**Wins** — Completed items, positive momentum. What's going right.

**Stalled** — Dead-end projects, stalled goals, identified gaps. What's stuck.

**Review Queue** — Knowledge due for spaced repetition today.

**Truth Alerts** — Facts that need re-verification.

**Data Sources** — Which connectors contributed data and when.

**Watchlist** — Recent changes detected in your network. Job moves, role changes, new activity from people you're tracking.

You didn't query for any of this. The background jobs ran on what's already in the graph and assembled the picture. Cross-domain alerts emerge naturally: the commitment scanner finds an overdue deliverable, a calendar event shows a meeting with the same person tomorrow, and the briefing connects them — because you captured both pieces at some point.

## The Dashboard

The default experience is a real-time TUI dashboard built with Textual — keyboard-driven, information-dense, expert-optimized. Not a pretty GUI that hides information behind clicks. A situation room that shows everything.

**Panels:** Situation overview, active alerts, commitment status, relationship health, activity feed, network map, detected patterns, quick capture input.

**Design philosophy:** Bloomberg-inspired. Every pixel earns its place. Keyboard shortcuts build muscle memory. Power users get faster over time, not frustrated by menus. Information density over whitespace.

**Widget system.** Composable panels — rearrange, resize, show, hide. Layout presets for different contexts: Overview (the morning check-in), People (relationship focus), Networks (domain health), Analysis (deep investigation).

**Real-time updates.** The event bus pushes changes to the dashboard as background jobs complete. A bridge gets discovered — the network map updates. A commitment goes overdue — the alert panel fires. You don't refresh. The situation room stays current with the intelligence layer's latest analysis of what you've fed it.

## The AI Council

Four specialized agents provide intelligence at different levels:

**Archivist.** The extractor. Reads your raw text and proposes graph structure — nodes, edges, updates. Uses RAG context to avoid duplicates. Handles ambiguity through a clarification protocol. When extraction confidence is zero, it asks before guessing.

**Strategist.** The analyst. Interprets graph data, identifies patterns, assesses network health, provides recommendations with citations. Generates the daily briefing. Can critique your decisions with counter-evidence from your own history. Expands entity neighborhoods for context — one hop out from any node to see its full local graph.

**Researcher.** The external eye. Searches the web, academic databases (Semantic Scholar), and code repositories (GitHub) via MCP tool servers. Critically: all queries are PII-anonymized before leaving the machine. Emails, phone numbers, names, dollar amounts — stripped or replaced. Results get deposited as verified facts in the truth layer with full source traceability.

**Orchestrator.** The coordinator. Classifies every query into one of four types — Capture, Analysis, Research, or Council — and routes to the right agent. For complex queries, it runs all agents in parallel, performs confidence-weighted synthesis, and triggers deliberation rounds when agents disagree (disagreement spread > 0.3). A CRAG fallback escalates to the full council when retrieval quality is poor. A fact-check gate validates the final synthesis against the truth layer.

The council runs on LangGraph as a multi-agent state machine: classify → route → execute → synthesize → (deliberate if needed) → respond.

## Architecture

**Local-first.** DuckDB for graph storage (embedded, zero infrastructure). Weaviate for vector storage (embedded, HNSW indexing). all-mpnet-base-v2 for embeddings (768-dimensional, computed on-device). Your data never leaves your machine unless you explicitly ask the Researcher to look something up — and even then, the query is anonymized.

**The LLM is replaceable.** Remove OpenAI entirely and the intelligence layer still works. Decay scoring, health computation, bridge detection, spaced repetition, commitment tracking, pattern detection, gap analysis — all algorithmic. The LLM enhances extraction and synthesis. It doesn't gatekeep functionality.

**Atomic commits.** Every graph mutation runs inside a DuckDB transaction. The graph changes completely or not at all. No partial states, no corruption.

**Async-first.** The pipeline is async with `asyncio.to_thread` for CPU-bound work. Post-commit processing runs seven parallel tasks. Entity resolution runs LLM adjudication via ThreadPoolExecutor.

**Event-driven.** Background jobs generate notifications. The event bus pushes updates to the dashboard. Optional file watchers can trigger ingestion for monitored directories. The system is reactive, not polling.

**Connector framework.** Four methods — `connect()`, `get_items()`, `transform()`, `sync()` — and a registry that manages instances. Adding a new data source is implementing an interface, not forking the codebase.

**MCP tool servers.** Google Search, Brave Search, Semantic Scholar, Playwright, GitHub, and a Graph Query server. The Researcher agent uses these. They're the external sensory organs — carefully anonymized, carefully controlled.

## What Makes This Different

Most personal knowledge tools are filing cabinets. You put things in, you search to get things out. The graph they build (if they build one at all) is static — a snapshot of what you told it.

Memora is a living system. The graph evolves without you touching it. Decay scores shift. Bridges emerge between networks you never consciously connected. Relationship health degrades as interaction gaps widen. Patterns surface from the aggregate of hundreds of small observations. Commitments go overdue and the system notices before you do.

The difference is the same difference between a Bloomberg terminal and a spreadsheet. The spreadsheet has the data. The terminal has the *intelligence* — real-time, cross-referenced, alert-driven, expert-optimized. Bloomberg charges $32,000/year because coherence over scattered financial data is worth that much to professionals who live in it.

Memora provides coherence over your scattered life. Every project, every person, every commitment, every decision, every idea — connected, decaying, evolving, alerting. It doesn't just remember the people in your life — it watches them, detecting changes before you hear about them through the grapevine. Not in a cloud service that mines your data. On your machine, in your terminal, under your control.

The graph is the product, not the AI.
