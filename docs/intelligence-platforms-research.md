# Intelligence Platforms Research Report

> How the world's best situational-awareness and financial-intelligence tools work — and what Memora can learn from them.

---

## Table of Contents

1. [Monitor the Situation](#1-monitor-the-situation)
2. [World Monitor & Variants](#2-world-monitor--variants)
3. [Situation Deck](#3-situation-deck)
4. [God's Eye Concept](#4-gods-eye-concept)
5. [Bloomberg Terminal](#5-bloomberg-terminal)
6. [Synthesis for Memora](#6-synthesis-for-memora)

---

## 1. Monitor the Situation

**URL:** [monitorthesituation.live](https://monitorthesituation.live) | [monitorthesituation.org](https://www.monitorthesituation.org/)
**Creators:** Ryan McEntush (Partner, a16z) and collaborators
**Type:** Closed-source, free real-time OSINT dashboard

### What It Is

Monitor the Situation is a polished, map-centric OSINT dashboard designed for real-time global event tracking. It rose to prominence during geopolitical crises (e.g., the US-Israel-Iran strikes) as a one-stop situational awareness tool. Ryan McEntush described it as a way to "track it all 24/7 — live TV, OSINT, planes, ships, and much more."

### Core Features

| Category | Details |
|----------|---------|
| **Live Map** | Interactive global map with toggleable layers for aircraft (ADS-B), ships (AIS), weather radar, event markers, and map style switching |
| **News Feeds** | 40+ curated news sources, filterable by 6-hour and 48-hour windows |
| **Live TV** | 50+ live TV and webcam feeds embedded directly in the interface |
| **Aircraft Tracking** | Military and civilian aircraft monitoring via ADS-B transponder data |
| **Maritime Tracking** | Ship positions and movement via AIS data |
| **Prediction Markets** | Kalshi prediction-market prices displayed as a running scroll with live odds |
| **World Leader Tracking** | Tracks positions and movements of world leaders |
| **AI Analysis** | Automated analysis and summarization of incoming data |

### Data Sources

- **Geospatial:** ADS-B (air traffic), AIS (maritime movement), infrastructure maps, power grids, undersea cables, military bases
- **Environmental:** Weather radar, day/night cycle overlays, VIIRS satellite imagery
- **News:** 40+ RSS/live feeds from news outlets and reliable OSINT sources
- **Markets:** Kalshi prediction market data, stock market quotes
- **Social:** OSINT-relevant social media feeds

### Design Philosophy

Monitor the Situation prioritizes **visual density without chaos**. The map is the primary interface — every data layer is spatial. Users toggle layers on and off to build their own picture of the situation. The design is polished and consumer-friendly despite the professional-grade data underneath, making OSINT accessible to non-specialists.

### Key Insight for Memora

> The power is in the **overlay**. Individual data sources are commodity; the value is showing how multiple variables intersect at a specific location or moment. Monitor the Situation doesn't generate data — it spatializes and correlates it.

---

## 2. World Monitor & Variants

**URL:** [worldmonitor.app](https://www.worldmonitor.app/)
**GitHub:** [koala73/worldmonitor](https://github.com/koala73/worldmonitor)
**License:** AGPL-3.0 (fully open-source)
**Type:** Real-time global intelligence dashboard

### What It Is

World Monitor is an open-source intelligence dashboard that aggregates global news, geopolitical signals, infrastructure data, and financial markets into a unified situational awareness interface. It runs from a single codebase with four switchable variants.

### The Four Variants

| Variant | Focus | Key Data |
|---------|-------|----------|
| **Geopolitical** | Primary variant — conflicts, hotspots, military tracking | Conflicts, protests, sanctions, cyber IOCs, GPS jamming |
| **Finance** | Markets, central banks, trade policy | 92 stock exchanges, 19 financial centers, 13 central banks, BIS data, WTO trade policy, Gulf FDI tracking |
| **Infrastructure** | Critical infrastructure monitoring | Undersea cables, pipelines, 111 AI datacenters, strategic ports, airports |
| **Military & Strategic** | Defense intelligence | 210+ military bases, live flights, naval vessels, nuclear facilities |

All four variants are switchable with one click via the header bar.

### Technical Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | Vanilla TypeScript (no UI framework) |
| **Maps** | MapLibre GL + deck.gl (dual map engine) |
| **API** | Sebuf — custom proto-first RPC framework |
| **Desktop** | Tauri (native desktop app) |
| **Serverless** | 60+ Supabase edge functions |
| **Localization** | 21 languages |

### Data Scale

- **435+ RSS feeds** across all 4 variants
- **45 toggleable data layers** (conflicts, bases, cables, pipelines, flights, vessels, protests, fires, earthquakes, datacenters)
- **30+ live video streams**
- **26 Telegram OSINT channels**
- **8 regional presets** with time filtering (1h-7d)
- **CII choropleth heatmap** painting every country by instability score

### AI Features

- AI-powered summarization of news feeds
- Local LLM support for offline analysis
- Deduction engine for pattern identification
- RAG (Retrieval-Augmented Generation) for contextual queries
- Cross-stream correlation across data sources

### Key Insight for Memora

> World Monitor proves that a **single codebase can serve multiple intelligence domains** through variant switching. The proto-first API design and edge function architecture show how to build a modular intelligence platform that scales without framework bloat. The CII instability scoring is analogous to Memora's entity decay and relevance scoring.

---

## 3. Situation Deck

**URL:** [sitdeck.com](https://sitdeck.com/) | [app.sitdeck.com](https://app.sitdeck.com/)
**Creator:** Dan Ushman (built as a personal side project, released as a product)
**Type:** Free, browser-based OSINT dashboard

### What It Is

Situation Deck (SitDeck) is the most feature-rich of the "monitor the situation" class of tools. It aggregates 184 live data providers into a customizable workspace with drag-and-drop widgets, an interactive multi-layer map, AI-powered analysis, and real-time alerting.

### Core Capabilities

| Feature | Scale |
|---------|-------|
| **Live Data Providers** | 184 sources across 26 categories |
| **Widgets** | 55 drag-and-drop widgets |
| **Map Overlay Layers** | 66 overlay layers |
| **Base Map Types** | 12 styles |
| **Pre-built Decks** | 6 intelligence configurations |

### Data Categories (26 total)

Seismic, weather, financial markets, cyber threats, military, aviation, maritime, nuclear, humanitarian, elections, space, social media OSINT, and more.

### AI Features

- **AI Analyst Chat:** Ask questions in plain English across all live data feeds and get sourced, cross-referenced intelligence answers
- **Situation Reports:** Auto-generated intelligence summaries
- **Daily Intelligence Briefings:** Scheduled digests
- **Custom Alerts:** Configurable notifications based on data thresholds

### Key Insight for Memora

> SitDeck's "AI Analyst Chat" is the most compelling feature — natural language querying across all live data. This is exactly what Memora's Researcher agent should feel like, but over personal knowledge instead of global OSINT feeds.

---

## 4. God's Eye Concept

### Origins

The "God's Eye" concept in intelligence refers to the aspiration of **total situational awareness** — the ability to see everything, everywhere, in real-time, and to correlate any piece of information with any other. The term gained mainstream recognition from the movie *Furious 7* (2015), where it was depicted as a surveillance tool that could find anyone by tapping into every camera and phone on Earth.

### Real-World Manifestations

| Implementation | Description |
|----------------|-------------|
| **Persistent Surveillance Systems (PSS)** | Super-high-resolution cameras aboard aircraft capturing 25-square-mile segments of Earth continuously for up to 6 hours |
| **Eye of God (Telegram bot)** | One of the most popular OSINT/Probiv bots, capable of searching emails, names, phone numbers, IP addresses, aliases, and license plates |
| **God's Eye (GitHub)** | Open-source email, IP, and nickname OSINT & password breach hunting tool with GUI |
| **Total Information Awareness (TIA)** | DARPA program (2002-2003) that aimed to achieve "total information awareness" by mining vast datasets for terrorist activity patterns |

### The OSINT Dashboard Connection

The platforms analyzed in this report — Monitor the Situation, World Monitor, and Situation Deck — are **civilian approximations of the God's Eye concept**, applied to open-source data. They don't tap into classified surveillance systems, but they achieve a remarkable degree of situational awareness by aggregating and correlating publicly available data:

- **ADS-B** gives you aircraft positions in real-time
- **AIS** gives you ship positions globally
- **VIIRS** gives you satellite-detected fire and light data
- **Seismic networks** give you earthquakes as they happen
- **RSS/social feeds** give you human narratives layered on top

The insight is that you don't need classified access to build a powerful intelligence picture — you need **aggregation, correlation, and a good interface**.

### Key Insight for Memora

> The God's Eye concept at a personal level is not surveillance — it's **self-awareness**. Memora's vision is a "God's Eye for your own life": total awareness of your knowledge, relationships, commitments, and patterns. The same principles apply — aggregation of scattered data sources, correlation across domains, and an interface that makes the invisible visible.

---

## 5. Bloomberg Terminal

**URL:** [bloomberg.com/professional](https://www.bloomberg.com/professional/products/bloomberg-terminal/)
**Founded:** 1981 by Michael Bloomberg
**Type:** Proprietary financial data terminal
**Pricing:** ~$31,980/year per seat (2026), ~$28,320/year for multi-seat
**Subscribers:** ~355,000 financial professionals globally
**Revenue:** ~$10-13B annually from Terminal alone (~$15B total Bloomberg LP revenue)

### Why Bloomberg Is the Gold Standard

Bloomberg Terminal isn't just a product — it's a **platform monopoly** that has maintained dominance for over 40 years. Understanding why requires analyzing it through multiple lenses.

### The 7 Powers Analysis (Hamilton Helmer Framework)

| Power | How Bloomberg Exhibits It |
|-------|---------------------------|
| **Scale Economies** | 355,000 terminals mean every new data product, feature, or technology investment is instantly amortized across a massive base. Competitors can't match R&D spend per-feature. |
| **Switching Costs** | The Terminal is mission-critical infrastructure. Traders' muscle memory is built around Bloomberg commands. Workflows, compliance systems, and communication all flow through it. Switching is operationally dangerous. |
| **Cornered Resource** | Bloomberg cornered the bonds market early — providing real-time pricing and analytics for increasingly complex fixed-income instruments when no one else could. Bloomberg News drives prices, and the Terminal delivers both the news and the prices it moves. |
| **Network Effects** | Bloomberg Messaging (IB chat) connects 355,000 professionals. The more people on Bloomberg, the more valuable the network. Deals get done on IB chat. If you're not on Bloomberg, you're out of the loop. |
| **Counter-Positioning** | Bloomberg's vertically integrated model (hardware + software + data + news + messaging) was initially dismissed by incumbents like Reuters who couldn't adopt it without cannibalizing their own businesses. |
| **Process Power** | Bloomberg's Ticker Plant ingests and processes millions of market updates per second with 24/7 uptime and fewer outages than AWS. This engineering excellence is built over decades and can't be replicated quickly. |
| **Branding** | "Bloomberg Terminal" is synonymous with professional finance. It signals competence, seriousness, and access. Firms pay for Bloomberg partly because clients expect them to have it. |

Bloomberg is one of very few products that exhibits **all seven powers simultaneously**.

### Data Scale

| Metric | Scale |
|--------|-------|
| **Daily data points processed** | 60 billion pieces of market information per day |
| **Ticker Plant throughput** | Millions of updates per second |
| **Asset classes covered** | Every major asset class globally — equities, fixed income, commodities, FX, derivatives |
| **News** | Bloomberg News (2,700+ journalists in 120 countries) + 1,000+ third-party news sources |
| **Company data** | Financials, filings, estimates, ownership, ESG for virtually every public company |
| **Pricing history** | Decades of historical pricing data across all asset classes |
| **Alternative data** | Satellite imagery, web scraping, supply chain, patent filings, sentiment |

### Architecture

| Layer | Details |
|-------|---------|
| **Server** | Multiprocessor Unix platform, originally Fortran/C, now C++/embedded JavaScript |
| **Client** | Windows application connecting via Bloomberg-provided router installed on-site |
| **Frontend (modern)** | Embedded Chromium powering the UI — HTML5, CSS3, JavaScript with hardware graphics acceleration |
| **Network** | Private global network with dedicated infrastructure, not reliant on public internet |
| **Data Pipeline** | The Ticker Plant — a massive, proprietary data ingestion and distribution system |
| **Uptime** | 24/7 with fewer outages than major cloud providers |

### UX Philosophy

Bloomberg's UX is deliberately **expert-optimized, not beginner-friendly**:

- **Command-line first:** Everything is accessed via typed commands followed by `<GO>`. E.g., `TOP <GO>` for top news, `DES <GO>` for security description.
- **Color-coded keyboard:** Physical Bloomberg keyboard with colored keys — yellow market sector keys, green action keys, red cancel/stop keys. Designed for traders with no prior computer experience.
- **Information density:** Multiple screens (typically 4 monitors) with user-configured panels showing diverse real-time data simultaneously.
- **Muscle memory over discoverability:** The interface rewards expertise. Power users navigate at extreme speed. The learning curve is a feature, not a bug — it creates switching costs.
- **Careful evolution:** Even moving a button or changing a font is treated as a potentially disruptive event. UX changes are rolled out with extreme caution because users depend on spatial memory.

> "Computers for Virgins" — a chapter in Michael Bloomberg's 1997 autobiography — explains why the Terminal keyboard was designed differently from standard PC keyboards: it was built for traders who had never used computers, not for people who already knew DOS.

### The Bloomberg Ecosystem

Bloomberg's true moat is not any single feature but the **ecosystem lock-in**:

1. **Bloomberg News** breaks stories that move markets
2. **Terminal** delivers the news alongside the pricing data it affects
3. **Bloomberg Messaging (IB)** is where deals are discussed
4. **Bloomberg Indices** are benchmarks that funds track
5. **Bloomberg Data License** feeds analytics systems
6. **BVAL** provides bond valuations used for compliance
7. **PORT** provides portfolio analytics
8. **AIM/EMSX** provides order management and execution

Each piece reinforces the others. You can't unbundle Bloomberg without losing the value of the connections.

### Key Insight for Memora

> Bloomberg's power comes from being the **single pane of glass** for an entire professional domain. It's not the best at any one thing — better charting exists, better news exists, better messaging exists. But nothing else connects all of them into one coherent workspace where data flows between functions. That integration IS the product.

---

## 6. Synthesis for Memora

### The Pattern Across All Platforms

Every platform analyzed shares a common architecture, regardless of domain:

```
[Many Scattered Sources] --> [Aggregation Engine] --> [Correlation Layer] --> [Unified Interface]
```

| Platform | Sources | Correlation | Interface |
|----------|---------|-------------|-----------|
| Monitor the Situation | ADS-B, AIS, news, prediction markets | Geospatial overlay | Interactive map |
| World Monitor | 435+ RSS, SIGINT, financial feeds | CII scoring, cross-stream correlation | Variant dashboards |
| Situation Deck | 184 providers, 26 categories | AI Analyst Chat | Drag-and-drop widgets |
| Bloomberg Terminal | 60B data points/day, proprietary data | Ticker Plant + analytics | Command-line + multi-monitor |

### Memora as a Personal Intelligence Terminal

Memora applies the same pattern to **personal knowledge**:

```
[Your Scattered Data] --> [Ingestion Pipeline] --> [Knowledge Graph + Entity Resolution] --> [CLI Terminal]
```

#### Source Mapping

| Intelligence Platform Concept | Memora Equivalent |
|-------------------------------|-------------------|
| RSS feeds, ADS-B, AIS data | Markdown files, calendar events, browsing history, notes |
| Real-time data ingestion | Async pipeline with `asyncio.to_thread` for CPU-bound work |
| Geospatial overlay / cross-stream correlation | **Entity resolution** — connecting mentions across sources to unified entities |
| CII instability scoring | **Decay engine** — entity relevance scores that change over time |
| AI Analyst Chat | **Researcher agent** — natural language queries over your knowledge graph |
| Ticker Plant (data processing) | **DuckDB graph repository** — atomic commits, parameterized queries |
| Bloomberg command line (`TOP <GO>`) | **CLI with ANSI rendering** — keyboard-driven, information-dense |
| Bloomberg Messaging (IB chat) | **Entity 360 view** — complete dossier on any person, project, or concept |
| Variant dashboards | **Ontology-driven views** — 12 node types, 29 edge types, multiple projections |

#### Principle Mapping

| Bloomberg/OSINT Principle | Memora Application |
|---------------------------|-------------------|
| **Single pane of glass** | One CLI that surfaces everything you know about any entity |
| **Expert-optimized UX** | CLI-first interface that rewards power users with speed |
| **Ecosystem lock-in** | Knowledge graph that becomes more valuable the more you use it (network effects with yourself) |
| **Cornered resource** | Your personal data — no one else has it, no one else can build this graph |
| **Switching costs** | The more knowledge in the graph, the harder it is to leave |
| **Process power** | Local-first architecture means your data never leaves your machine |
| **Information density** | ANSI terminal rendering for dense, scannable output |
| **Careful UX evolution** | Stable CLI commands that build muscle memory |

#### The Vision

Bloomberg proves that a **domain-specific terminal** — ugly, dense, command-line-driven — can become the most valuable software product in its category ($31,980/year, 355,000 subscribers, $13B revenue) if it achieves three things:

1. **Aggregation completeness** — Everything you need is here, so you never have to leave
2. **Correlation depth** — Data connects to other data automatically, revealing insights you'd miss in siloed tools
3. **Expert ergonomics** — The interface is fast for experts, even if it's intimidating for beginners

Memora's bet is that these same principles apply at the personal level:

1. **Your notes, calendar, contacts, bookmarks, and browsing history** aggregated into one knowledge graph
2. **Entity resolution and relationship inference** connecting the dots across all your data automatically
3. **A CLI terminal** that lets you query, explore, and act on your knowledge with the speed of a Bloomberg power user

> The Bloomberg Terminal costs $32,000/year because it makes a financial professional's scattered information coherent. Memora aims to do the same for a knowledge worker's scattered life — locally, privately, and for free.

---

## Sources

- [Monitor the Situation](https://monitorthesituation.live)
- [Monitor the Situation - Military Aircraft Monitor](https://www.monitorthesituation.org/)
- [Ryan McEntush on X — announcing Monitor the Situation](https://x.com/rmcentush/status/2027658407193248042)
- [Monitor the Situation: An Alternative to GEOSINT Monitoring (Medium)](https://medium.com/@tohkaaryani/monitor-the-situation-an-alternative-to-geosint-monitoring-65837c550c7d)
- [World Monitor GitHub (koala73/worldmonitor)](https://github.com/koala73/worldmonitor)
- [World Monitor App](https://www.worldmonitor.app/)
- [World Monitor Documentation](https://github.com/koala73/worldmonitor/blob/main/docs/DOCUMENTATION.md)
- [Situation Deck (SitDeck)](https://sitdeck.com/)
- [Dan Ushman announcing SitDeck on X](https://x.com/danushman/status/2028007602391540026)
- [SitDeck Product Page](https://sitdeck.com/product)
- [Show HN: Customizable OSINT dashboard (Hacker News)](https://news.ycombinator.com/item?id=46591589)
- [Bloomberg Terminal (Wikipedia)](https://en.wikipedia.org/wiki/Bloomberg_Terminal)
- [Bloomberg's 7 Powers & Why the Terminal Dominates (The Terminalist)](https://theterminalist.substack.com/p/bloombergs-7-powers-and-why-the-terminal)
- [10,000x: Bloomberg's Return (The Terminalist)](https://theterminalist.substack.com/p/10000x-bloombergs-return-and-why)
- [How Bloomberg Terminal UX Designers Conceal Complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/)
- [Innovating a Modern Icon: How Bloomberg Keeps the Terminal Cutting-Edge](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/)
- [What Is The Bloomberg Terminal And What Makes It So Powerful? (MakeUseOf)](https://www.makeuseof.com/what-is-the-bloomberg-terminal/)
- [Why Is Bloomberg Terminal So Expensive? (Godel Terminal)](https://godeldiscount.com/blog/why-is-bloomberg-terminal-so-expensive)
- [Bloomberg System Design Interview Guide](https://www.systemdesignhandbook.com/guides/bloomberg-system-design-interview/)
- [God's Eye — Null Byte](https://null-byte.wonderhowto.com/how-to/advice-from-real-hacker-would-build-gods-eye-furious-7-0166661/)
- [God's Eye Persistent Surveillance (Washington Times)](https://www.washingtontimes.com/news/2014/apr/15/gods-eye-spy-system-hits-test-market-streets-real-/)
