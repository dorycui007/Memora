"""Horizon command — operational awareness with graph-weighted priority."""

from __future__ import annotations

from cli.rendering import (
    C,
    NETWORK_ABBREV,
    NODE_ICONS,
    divider,
    horizon_header,
    menu_option,
    prompt,
)


def cmd_horizon(app):
    """Unified operational view: what needs attention, when, and why."""
    while True:
        horizon_header()

        print(menu_option("1", "Today", "What needs attention now"))
        print(menu_option("2", "This week", "7-day operational view"))
        print(menu_option("3", "This month", "30-day planning horizon"))
        print(menu_option("4", "All open", "Everything active, by priority"))
        print(menu_option("5", "By network", "Filter by context network"))
        print(menu_option("6", "Check off", "Complete a task and see impact"))
        print(menu_option("c", "Capture", "Quick redirect to capture"))
        print()

        choice = prompt("horizon> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "c":
            from cli.commands.capture import cmd_capture
            cmd_capture(app)
        elif choice == "1":
            _show_view(app, "day")
        elif choice == "2":
            _show_view(app, "week")
        elif choice == "3":
            _show_view(app, "month")
        elif choice == "4":
            _show_view(app, "all")
        elif choice == "5":
            _show_by_network(app)
        elif choice == "6":
            _check_off(app)


# ── View rendering ────────────────────────────────────────────────────

_WINDOW_LABELS = {
    "day": "today",
    "week": "this week",
    "month": "this month",
    "all": "all open",
}


def _show_view(app, window: str, networks: list[str] | None = None):
    """Build and render a time-bucketed horizon view."""
    from memora.core.horizon import HorizonEngine

    engine = HorizonEngine(app.repo)
    view = engine.build_view(window=window, networks=networks)

    R = C.RESET
    label = _WINDOW_LABELS.get(window, window)

    if view.total == 0:
        print(f"\n  {C.DIM}No items on the horizon.{R}")
        print(f"  {C.DIM}Use Capture to record commitments, goals, and events.{R}\n")
        return

    # Header summary
    print(f"\n  {C.SIGNAL}{C.BOLD}HORIZON{R}  {C.BASE}{label}{R}  "
          f"{C.DIM}({view.total} items, {view.overdue_count} overdue){R}")
    print(f"  {C.FRAME}{'─' * 50}{R}")

    # Pattern alerts
    if view.pattern_warnings:
        print(f"\n  {C.DANGER}{C.BOLD}PATTERN ALERTS:{R}")
        for w in view.pattern_warnings:
            desc = w.get("description", "")
            print(f"    {C.DANGER}▲{R} {C.BASE}{desc}{R}")
        print()

    # Render each non-empty bucket
    _render_bucket("OVERDUE", view.overdue, C.DANGER)
    _render_bucket("TODAY", view.today, C.SIGNAL)
    _render_bucket("TOMORROW", view.tomorrow, C.WARM)
    _render_bucket("THIS WEEK", view.this_week, C.WARM)
    _render_bucket("NEXT WEEK", view.next_week, C.ACCENT)
    _render_bucket("THIS MONTH", view.this_month, C.ACCENT)
    _render_bucket("LATER", view.later, C.DIM)
    _render_bucket("UNDATED", view.undated, C.GHOST)

    # Network load footer
    if view.network_load:
        load_parts = []
        for net, count in sorted(view.network_load.items(), key=lambda x: -x[1]):
            abbrev = NETWORK_ABBREV.get(net, net[:4])
            load_parts.append(f"{abbrev}:{count}")
        print(f"\n  {C.DIM}Network load:  {' '.join(load_parts)}{R}")

    print(f"  {C.DIM}{view.completable_count} completable  "
          f"{view.overdue_count} overdue  "
          f"{view.total} total{R}\n")


def _render_bucket(label: str, items, color: str):
    """Render a single time bucket if it has items."""
    if not items:
        return
    R = C.RESET

    sorted_items = sorted(items, key=lambda i: -i.composite_priority)
    print(f"\n  {color}{C.BOLD}{label}{R} {C.DIM}({len(items)}){R}")

    for item in sorted_items:
        print(f"    {_format_item(item)}")


def _format_item(item) -> str:
    """Format a single HorizonItem as a one-line string."""
    R = C.RESET

    # Checkbox
    if not item.completable:
        checkbox = f" {C.DIM}.{R} "
    elif item.status in ("completed", "achieved"):
        checkbox = f"{C.CONFIRM}[x]{R}"
    else:
        checkbox = f"{C.FRAME}[ ]{R}"

    # Node icon
    icon = NODE_ICONS.get(item.kind, " ")

    # Title (truncated)
    title = item.title[:35]

    # Priority mini-bar (4 chars)
    pbar = _priority_bar(item.composite_priority)

    # Network badge
    nets = ""
    if item.networks:
        primary = item.networks[0]
        nets = f"  {C.DIM}{NETWORK_ABBREV.get(primary, primary[:4])}{R}"

    # Days label
    days = _days_label(item)

    # Progress bar for goals
    progress = ""
    if item.progress is not None and item.kind == "GOAL":
        filled = int(item.progress * 4)
        progress = f"  {C.CONFIRM}{'█' * filled}{C.GHOST}{'░' * (4 - filled)}{R}"

    # Blocking indicator
    blocking = ""
    if item.blocking_count > 0:
        blocking = f"  {C.DIM}[blocks {item.blocking_count}]{R}"

    # Parent context
    parent = ""
    if item.parent_title:
        ptitle = item.parent_title[:20]
        parent = f"  {C.GHOST}← {ptitle}{R}"

    return (
        f"{checkbox} {icon} {C.BASE}{title}{R}"
        f"  {pbar}{nets}  {days}{progress}{blocking}{parent}"
    )


def _priority_bar(score: float) -> str:
    """4-char priority gradient bar."""
    R = C.RESET
    level = min(int(score * 4), 4)

    if level >= 4:
        return f"{C.DANGER}████{R}"
    elif level == 3:
        return f"{C.SIGNAL}███{C.GHOST}░{R}"
    elif level == 2:
        return f"{C.WARM}██{C.GHOST}░░{R}"
    elif level == 1:
        return f"{C.DIM}█{C.GHOST}░░░{R}"
    else:
        return f"{C.GHOST}░░░░{R}"


def _days_label(item) -> str:
    """Human-readable days-until label."""
    R = C.RESET

    if item.days_until is None:
        return f"{C.GHOST}undated{R}"
    elif item.overdue:
        n = abs(item.days_until)
        return f"{C.DANGER}{n}d overdue{R}"
    elif item.days_until == 0:
        return f"{C.SIGNAL}today{R}"
    elif item.days_until == 1:
        return f"{C.WARM}tomorrow{R}"
    else:
        return f"{C.DIM}{item.days_until}d{R}"


# ── Network filter ────────────────────────────────────────────────────

def _show_by_network(app):
    """Show horizon filtered by a selected network."""
    from memora.core.health_scoring import ALL_NETWORKS

    R = C.RESET
    print(f"\n  {C.BOLD}Select network:{R}")
    for i, net in enumerate(ALL_NETWORKS, 1):
        abbrev = NETWORK_ABBREV.get(net, net[:4])
        print(f"    {C.ACCENT}[{i}]{R} {net} ({abbrev})")

    idx = prompt("network #: ")
    try:
        selected = ALL_NETWORKS[int(idx) - 1]
    except (ValueError, IndexError):
        print(f"  {C.DANGER}Invalid selection{R}")
        return

    _show_view(app, "all", networks=[selected])


# ── Check-off flow ────────────────────────────────────────────────────

def _check_off(app):
    """Search, preview impact, and complete an item."""
    from memora.core.horizon import HorizonEngine

    R = C.RESET
    query = prompt("Search for item to complete: ")
    if not query:
        return

    all_results = app.repo.search_nodes_ilike(query, limit=10)
    # Filter to completable types
    completable_types = {"COMMITMENT", "GOAL"}
    results = [r for r in all_results if r.get("node_type") in completable_types]

    if not results:
        if all_results:
            top = all_results[0]
            print(f"  {C.DIM}Found '{top['title']}' ({top['node_type']}) "
                  f"— only commitments and goals can be checked off{R}")
        else:
            print(f"  {C.DIM}No items found matching '{query}'{R}")
        return

    print(f"\n  {C.BOLD}Matching items:{R}")
    for i, n in enumerate(results, 1):
        icon = NODE_ICONS.get(n["node_type"], " ")
        nets = ", ".join(
            NETWORK_ABBREV.get(net, net[:4])
            for net in (n.get("networks") or [])
        )
        net_badge = f"  {C.DIM}({nets}){R}" if nets else ""
        print(f"    {C.DIM}{i:2}.{R} {icon} {n['title']}  "
              f"{C.DIM}{n['node_type']}{R}{net_badge}")

    idx = prompt("Select item #: ")
    try:
        selected = results[int(idx) - 1]
    except (ValueError, IndexError):
        print(f"  {C.DANGER}Invalid selection{R}")
        return

    node_id = selected["id"]
    engine = HorizonEngine(app.repo)

    # Preview impact
    impact = engine.get_impact_preview(node_id)
    print(f"\n  {C.SIGNAL}{C.BOLD}IMPACT PREVIEW{R}")
    print(f"  {C.FRAME}{'─' * 30}{R}")

    if impact.unblocked_items:
        print(f"  {C.CONFIRM}Unblocks:{R}")
        for item in impact.unblocked_items:
            print(f"    {C.BASE}• {item['title']} ({item['kind']}){R}")
    else:
        print(f"  {C.DIM}No items directly unblocked{R}")

    if impact.network_health_delta:
        print(f"  {C.BASE}Network status:{R}")
        for net, status in impact.network_health_delta.items():
            abbrev = NETWORK_ABBREV.get(net, net[:4])
            color = (
                C.DANGER if status == "falling_behind"
                else C.SIGNAL if status == "needs_attention"
                else C.CONFIRM
            )
            print(f"    {abbrev}: {color}{status}{R}")

    if impact.pattern_note:
        print(f"  {C.SIGNAL}Pattern: {impact.pattern_note}{R}")

    # Confirm
    confirm = prompt(f"\n  Complete '{selected['title']}'? (y/n): ")
    if confirm not in ("y", "yes"):
        print(f"  {C.DIM}Cancelled{R}")
        return

    result = engine.complete_item(node_id)

    if result.unblocked_items:
        count = len(result.unblocked_items)
        print(f"\n  {C.CONFIRM}Completed! Unblocked {count} item(s).{R}")
    else:
        print(f"\n  {C.CONFIRM}Completed.{R}")

    if result.pattern_note:
        print(f"  {C.DIM}{result.pattern_note}{R}")
