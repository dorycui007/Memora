"""Timeline command — ASCII timeline viewer with date navigation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cli.rendering import C, NODE_ICONS, divider, menu_option, prompt, timeline_header


def cmd_timeline(app):
    """Interactive timeline viewer."""
    while True:
        timeline_header()

        print(menu_option("1", "This week",      "Events from the past 7 days"))
        print(menu_option("2", "This month",     "Events from the past 30 days"))
        print(menu_option("3", "Custom range",   "Specify start and end dates"))
        print(menu_option("4", "Causal chain",   "Trace cause and effect from a node"))
        print(menu_option("5", "Activity bursts","Find periods of high activity"))
        print(menu_option("6", "Weekly digest",  "Structured weekly summary"))
        print()

        choice = prompt("timeline> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _show_range(app, days=7)
        elif choice == "2":
            _show_range(app, days=30)
        elif choice == "3":
            _custom_range(app)
        elif choice == "4":
            _causal_chain(app)
        elif choice == "5":
            _activity_bursts(app)
        elif choice == "6":
            _weekly_digest(app)


def _show_range(app, days: int):
    """Show timeline for a given number of past days."""
    from memora.core.timeline import TimelineEngine

    engine = TimelineEngine(app.repo)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()

    timeline = engine.get_timeline(start=start, limit=50)
    _render_timeline(timeline, f"Last {days} days")


def _custom_range(app):
    """Show timeline for a custom date range."""
    from memora.core.timeline import TimelineEngine

    start = prompt("Start date (YYYY-MM-DD): ")
    end = prompt("End date (YYYY-MM-DD): ")
    if not start:
        return

    engine = TimelineEngine(app.repo)
    timeline = engine.get_timeline(start=start, end=end or None, limit=100)
    _render_timeline(timeline, f"{start} to {end or 'now'}")


def _render_timeline(items: list[dict], title: str):
    """Render a list of timeline items as an ASCII timeline."""
    if not items:
        print(f"\n  {C.DIM}No events found for: {title}{C.RESET}")
        return

    print(f"\n  {C.BOLD}Timeline: {title}{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

    current_date = ""
    for item in items:
        created = item.get("created_at", "")
        if isinstance(created, datetime):
            date_str = created.strftime("%Y-%m-%d")
            time_str = created.strftime("%H:%M")
        else:
            date_str = str(created)[:10]
            time_str = str(created)[11:16] if len(str(created)) > 16 else ""

        # Print date header when date changes
        if date_str != current_date:
            current_date = date_str
            print(f"\n  {C.BOLD}{C.CYAN}{date_str}{C.RESET}")
            print(f"  {C.DIM}{'─' * 40}{C.RESET}")

        icon = NODE_ICONS.get(item.get("node_type", ""), " ")
        title = item.get("title", "")[:50]
        node_type = item.get("node_type", "")

        print(f"    {C.DIM}{time_str}{C.RESET}  {icon} {title}  {C.DIM}({node_type}){C.RESET}")

    print(f"\n  {C.DIM}{len(items)} event(s) total{C.RESET}")


def _causal_chain(app):
    """Trace causal chain from a selected node."""
    from memora.core.timeline import TimelineEngine

    query = prompt("Search for starting node: ")
    if not query:
        return

    results = app.repo.search_nodes_ilike(query, limit=5)
    if not results:
        print(f"  {C.DIM}No nodes found{C.RESET}")
        return

    for i, n in enumerate(results, 1):
        icon = NODE_ICONS.get(n["node_type"], " ")
        print(f"    {C.DIM}{i}.{C.RESET} {icon} {n['title']}")

    idx = prompt("Select node #: ")
    try:
        node = results[int(idx) - 1]
    except (ValueError, IndexError):
        return

    engine = TimelineEngine(app.repo)
    chain = engine.trace_causal_chain(node["id"])

    nodes = chain.get("nodes", [])
    edges = chain.get("edges", [])

    if len(nodes) <= 1:
        print(f"\n  {C.DIM}No causal chain found from this node{C.RESET}")
        return

    print(f"\n  {C.BOLD}Causal Chain ({len(nodes)} nodes, {len(edges)} links):{C.RESET}")
    for i, n in enumerate(nodes):
        icon = NODE_ICONS.get(n.get("node_type", ""), " ")
        prefix = "  ┌─" if i == 0 else "  ├─" if i < len(nodes) - 1 else "  └─"
        print(f"  {C.CYAN}{prefix}{C.RESET} {icon} {n.get('title', '?')}  {C.DIM}({n.get('node_type', '')}){C.RESET}")

        # Show the connecting edge type
        if i < len(edges):
            edge = edges[i]
            print(f"  {C.DIM}  │    via {edge.get('edge_type', '')}{C.RESET}")


def _activity_bursts(app):
    """Show detected activity bursts."""
    from memora.core.timeline import TimelineEngine

    engine = TimelineEngine(app.repo)
    bursts = engine.detect_activity_bursts()

    if not bursts:
        print(f"\n  {C.DIM}No significant activity bursts detected{C.RESET}")
        return

    print(f"\n  {C.BOLD}Activity Bursts:{C.RESET}\n")
    for b in bursts:
        print(
            f"    {C.YELLOW}▪{C.RESET} {b['start']} → {b['end']}  "
            f"{C.BOLD}{b['node_count']}{C.RESET} nodes  "
            f"{C.DIM}({b['average_daily']}/day vs {b['overall_average']}/day avg){C.RESET}"
        )


def _weekly_digest(app):
    """Show structured weekly digest."""
    from memora.core.timeline import TimelineEngine

    engine = TimelineEngine(app.repo)
    digest = engine.get_weekly_digest()

    total = digest.get("total_nodes", 0)
    print(f"\n  {C.BOLD}Weekly Digest{C.RESET}")
    print(f"  {C.DIM}{digest['period']['start'][:10]} → {digest['period']['end'][:10]}{C.RESET}")
    print(f"\n  Total nodes created: {C.BOLD}{total}{C.RESET}")

    by_type = digest.get("by_type", {})
    if by_type:
        print(f"\n  {C.BOLD}By Type:{C.RESET}")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            icon = NODE_ICONS.get(t, " ")
            print(f"    {icon} {t}: {count}")

    by_network = digest.get("by_network", {})
    if by_network:
        print(f"\n  {C.BOLD}By Network:{C.RESET}")
        for net, count in sorted(by_network.items(), key=lambda x: -x[1]):
            print(f"    {net}: {count}")

    decisions = digest.get("decisions", [])
    if decisions:
        print(f"\n  {C.BOLD}Decisions:{C.RESET}")
        for d in decisions[:5]:
            print(f"    {C.GREEN}?{C.RESET} {d['title']}")

    commitments = digest.get("commitments", [])
    if commitments:
        print(f"\n  {C.BOLD}Commitments:{C.RESET}")
        for c in commitments[:5]:
            print(f"    {C.RED}!{C.RESET} {c['title']}")
