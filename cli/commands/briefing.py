"""Briefing command — generate daily briefing with typed sections."""

from __future__ import annotations

import textwrap
from datetime import UTC, datetime

from cli.rendering import (
    C, divider, prompt, spinner, term_width,
    briefing_header, progress_step, progress_step_last,
)
from memora.core.async_utils import run_async


# ── Section rendering config ────────────────────────────────────

MOOD_COLORS = {
    "good_day": C.CONFIRM,
    "mixed": C.BASE,
    "needs_focus": C.SIGNAL,
    "urgent": C.DANGER,
}

MOOD_LABELS = {
    "good_day": "GOOD DAY",
    "mixed": "MIXED",
    "needs_focus": "NEEDS FOCUS",
    "urgent": "URGENT",
}

SECTIONS = [
    ("network_overview", "Network Overview",  C.ACCENT,  False),
    ("urgent",           "Urgent",            C.RED,     True),
    ("since_last",       "Since Last Check",  C.BASE,    True),
    ("upcoming",         "Coming Up",         C.SIGNAL,  True),
    ("people_followup",  "People",            C.CYAN,    True),
    ("patterns_insights","Insights",          C.MAGENTA, True),
    ("wins",             "Wins",              C.GREEN,   True),
    ("stalled_attention","Stalled",           C.YELLOW,  True),
    ("review_items",     "Review Queue",      C.DIM,     True),
]


def _render_section(title: str, items: list[str], color: str, is_list: bool):
    """Render a single briefing section with color and bullet items."""
    print(f"\n  {color}{C.BOLD}{title}{C.RESET}")
    print(f"  {C.FRAME}{'─' * len(title)}{C.RESET}")
    if is_list:
        for item in items:
            wrapped = textwrap.wrap(item, min(term_width() - 8, 68))
            if wrapped:
                print(f"    {color}•{C.RESET} {wrapped[0]}")
                for line in wrapped[1:]:
                    print(f"      {line}")
    else:
        # Single paragraph (network_overview)
        text = items if isinstance(items, str) else " ".join(items)
        for line in textwrap.wrap(text, min(term_width() - 6, 68)):
            print(f"    {line}")


def cmd_briefing(app):
    # Get operator name for header
    _op_name = ""
    try:
        from uuid import UUID
        from memora.graph.repository import YOU_NODE_ID
        you_node = app.repo.get_node(UUID(YOU_NODE_ID))
        if you_node and you_node.properties:
            _op_name = you_node.properties.get("name", "")
    except Exception:
        pass
    briefing_header(operator_name=_op_name)

    # Collect data from all sources
    print(f"\n  {C.DIM}Gathering intelligence...{C.RESET}")

    from memora.core.briefing import BriefingCollector, get_last_briefing_time

    truth_layer = getattr(app, "truth_layer", None)
    collector = BriefingCollector(app.repo, truth_layer=truth_layer)

    progress_step("Health scores", in_progress=True)
    since = get_last_briefing_time(app.repo)
    briefing_data = collector.collect(since=since)
    progress_step("Health scores", done=True)
    progress_step("Commitments & decay", done=True)
    progress_step("Timeline & actions", done=True)
    progress_step("Patterns & gaps", done=True)
    progress_step_last("People & review queue", done=True)

    sources = briefing_data.get("data_sources_used", [])
    print(f"\n  {C.DIM}Sources: {', '.join(sources) if sources else 'none'}{C.RESET}")

    # Try LLM synthesis
    strat = app._get_strategist()
    if not strat:
        print(f"\n  {C.YELLOW}Strategist unavailable (no API key).{C.RESET}")
        print(f"  {C.DIM}Showing raw data dashboard...{C.RESET}")
        _render_raw_fallback(briefing_data)
        return

    spinner("Strategist composing briefing", 1.5)

    try:
        briefing = run_async(strat.generate_briefing(briefing_data))
    except Exception as e:
        print(f"\n  {C.RED}Briefing failed: {e}{C.RESET}")
        print(f"  {C.DIM}Falling back to raw data...{C.RESET}")
        _render_raw_fallback(briefing_data)
        return

    # Mood-colored summary header
    mood = briefing.mood or "mixed"
    mood_color = MOOD_COLORS.get(mood, C.BASE)
    mood_label = MOOD_LABELS.get(mood, mood.upper())

    print(f"\n  {mood_color}{C.BOLD}━━ {mood_label} ━━{C.RESET}")
    if briefing.summary:
        print()
        for line in textwrap.wrap(briefing.summary, min(term_width() - 6, 68)):
            print(f"    {mood_color}{line}{C.RESET}")

    # Render each section
    for field_name, title, color, is_list in SECTIONS:
        value = getattr(briefing, field_name, None)
        if not value:
            continue
        if is_list and isinstance(value, list) and len(value) > 0:
            _render_section(title, value, color, is_list=True)
        elif not is_list and isinstance(value, str) and value.strip():
            _render_section(title, value, color, is_list=False)

    print(f"\n{divider()}")
    print(f"  {C.DIM}Generated {briefing.generated_at.strftime('%H:%M UTC') if briefing.generated_at else 'now'}"
          f" · {len(sources)} data source(s){C.RESET}")
    print()


def _render_raw_fallback(data: dict):
    """Render collected data as a structured dashboard without LLM synthesis."""
    # Urgent
    urgent = data.get("urgent", {})
    overdue = urgent.get("overdue_commitments", [])
    decaying = urgent.get("decaying_close", [])

    if overdue or decaying:
        print(f"\n  {C.RED}{C.BOLD}Urgent{C.RESET}")
        print(f"  {C.FRAME}──────{C.RESET}")
        for item in overdue[:5]:
            print(f"    {C.RED}•{C.RESET} Overdue: {item.get('title', '?')} "
                  f"({item.get('days_overdue', '?')}d overdue)")
        for item in decaying[:5]:
            print(f"    {C.RED}•{C.RESET} {item.get('person_name', '?')} — "
                  f"{item.get('days_since_interaction', '?')}d since contact "
                  f"(close relationship)")

    # Upcoming
    upcoming = data.get("upcoming", {})
    approaching = upcoming.get("approaching", [])
    if approaching:
        print(f"\n  {C.SIGNAL}{C.BOLD}Coming Up{C.RESET}")
        print(f"  {C.FRAME}─────────{C.RESET}")
        for item in approaching[:5]:
            print(f"    {C.SIGNAL}•{C.RESET} {item.get('title', '?')} "
                  f"(due in {item.get('days_until_due', '?')}d)")

    review_count = upcoming.get("review_count", 0)
    if review_count:
        print(f"    {C.DIM}•{C.RESET} {review_count} item(s) due for review")

    # People
    people = data.get("people", {})
    decaying_all = people.get("decaying_all", [])
    if decaying_all:
        print(f"\n  {C.CYAN}{C.BOLD}People{C.RESET}")
        print(f"  {C.FRAME}──────{C.RESET}")
        for item in decaying_all[:5]:
            print(f"    {C.CYAN}•{C.RESET} {item.get('person_name', '?')} — "
                  f"{item.get('days_since_interaction', '?')}d "
                  f"({item.get('relationship_type', '?')})")

    # Stalled
    stalled = data.get("stalled", {})
    stalled_goals = stalled.get("stalled_goals", [])
    dead_ends = stalled.get("dead_end_projects", [])
    if stalled_goals or dead_ends:
        print(f"\n  {C.YELLOW}{C.BOLD}Stalled{C.RESET}")
        print(f"  {C.FRAME}───────{C.RESET}")
        for item in stalled_goals[:3]:
            print(f"    {C.YELLOW}•{C.RESET} Goal: {item.get('title', '?')} "
                  f"(stalled {item.get('stall_days', '?')}d)")
        for item in dead_ends[:3]:
            print(f"    {C.YELLOW}•{C.RESET} Project: {item.get('title', '?')} "
                  f"(stalled {item.get('stall_days', '?')}d)")

    # Health overview
    health = data.get("health", [])
    if health:
        print(f"\n  {C.ACCENT}{C.BOLD}Network Health{C.RESET}")
        print(f"  {C.FRAME}──────────────{C.RESET}")
        for h in health:
            status_color = {
                "on_track": C.CONFIRM,
                "needs_attention": C.SIGNAL,
                "falling_behind": C.DANGER,
            }.get(h.get("status", ""), C.DIM)
            print(f"    {status_color}◉{C.RESET} {h.get('network', '?')}: "
                  f"{h.get('status', '?')} ({h.get('momentum', '?')})")

    if not any([overdue, decaying, approaching, decaying_all, stalled_goals, dead_ends, health]):
        print(f"\n  {C.DIM}No significant data to display.{C.RESET}")

    print()
