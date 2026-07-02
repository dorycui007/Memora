"""Research command — external intelligence via MCP tools."""

from __future__ import annotations

import asyncio
import textwrap

from cli.rendering import (
    C, divider, horizontal_bar, prompt, spinner, term_width,
    research_header,
)


def cmd_research(app):
    """Run an external research query via the Researcher agent."""
    research_header()

    query = prompt(f"  What to research?\n  {C.ACCENT}>{C.RESET} ")
    if not query or query in ("q", "b", "back"):
        return

    if not app._has_api_key:
        print(f"\n  {C.RED}Research unavailable (no API key).{C.RESET}")
        print(f"  {C.DIM}Set OPENAI_API_KEY in .env to enable.{C.RESET}\n")
        return

    spinner("Initializing researcher", 0.3)

    # Initialize MCP search tools
    mcp_tools = {}
    try:
        from memora.mcp.google_search import GoogleSearchMCP
        from memora.mcp.brave_search import BraveSearchMCP
        google = GoogleSearchMCP()
        brave = BraveSearchMCP()
        if google.available:
            mcp_tools["google_search"] = google
        elif brave.available:
            mcp_tools["brave_search"] = brave
    except Exception:
        pass

    if not mcp_tools:
        print(f"\n  {C.SIGNAL}No search API keys configured.{C.RESET}")
        print(f"  {C.DIM}Set GOOGLE_API_KEY or BRAVE_API_KEY in .env{C.RESET}\n")
        return

    try:
        from memora.agents.researcher import ResearcherAgent
        researcher = ResearcherAgent(
            api_key=app.settings.openai_api_key,
            mcp_tools=mcp_tools,
        )
    except Exception as e:
        print(f"\n  {C.RED}Researcher init failed: {e}{C.RESET}")
        return

    # Build graph context for PII anonymization
    graph_context = None
    if app.repo:
        try:
            people = app.repo.get_person_nodes()
            if people:
                graph_context = {
                    "nodes": [
                        {
                            "node_type": "PERSON",
                            "title": p.get("title", ""),
                            "content": p.get("title", ""),
                        }
                        for p in people
                    ]
                }
        except Exception:
            pass

    spinner("Anonymizing query", 0.3)
    spinner("Searching external sources", 1.0)

    try:
        result = asyncio.run(researcher.research(query, graph_context=graph_context))
    except Exception as e:
        print(f"\n  {C.RED}Research failed: {e}{C.RESET}")
        return

    _render_research_result(result)


def _render_research_result(result):
    """Display a ResearchResult with sources and confidence."""
    w = min(term_width() - 6, 72)

    print(f"\n{divider('=', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}RESEARCH RESULT{C.RESET}")

    # Anonymized query
    if result.anonymized_query:
        print(f"  {C.DIM}Anonymized query: {result.anonymized_query}{C.RESET}")

    # Confidence bar
    print(f"  {C.DIM}Confidence:{C.RESET} {horizontal_bar(result.confidence, 15)}")
    print(divider())

    # Answer text, word-wrapped
    if result.answer:
        print()
        for paragraph in result.answer.split("\n\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for line in textwrap.wrap(paragraph, w):
                print(f"    {line}")
            print()

    # Sources
    if result.sources:
        print(f"  {C.BOLD}Sources:{C.RESET}")
        for i, src in enumerate(result.sources, 1):
            title = src.title or "(untitled)"
            url = src.url or ""
            rel = src.reliability_score
            stype = src.source_type

            type_badge = (f"{C.GREEN}{stype}{C.RESET}" if stype == "PRIMARY"
                         else f"{C.DIM}{stype}{C.RESET}")
            print(f"    {i}. {C.BASE}{title}{C.RESET}")
            if url:
                print(f"       {C.DIM}{url}{C.RESET}")
            print(f"       reliability: {horizontal_bar(rel, 10)}  {type_badge}")

    # Facts deposited
    fact_count = len(result.facts_to_deposit)
    if fact_count:
        print(f"\n  {C.DIM}Facts deposited: {fact_count}{C.RESET}")

    print(f"\n{divider('=', C.CYAN)}")
