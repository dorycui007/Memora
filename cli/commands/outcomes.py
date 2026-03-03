"""Outcomes command — 'What happened?' interactive outcome recording."""

from __future__ import annotations

from cli.rendering import C, NODE_ICONS, divider, horizontal_bar, menu_option, outcomes_header, prompt, subcommand_header


def cmd_outcomes(app):
    """Interactive outcome tracking: review pending, record outcomes, view stats."""
    while True:
        outcomes_header()
        print(menu_option("1", "What happened?",  "Review pending decisions/goals"))
        print(menu_option("2", "Record outcome",  "Record outcome for a specific node"))
        print(menu_option("3", "Statistics",      "View outcome win/loss stats"))
        print()

        choice = prompt("outcomes> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _review_pending(app)
        elif choice == "2":
            _record_outcome(app)
        elif choice == "3":
            _show_stats(app)


def _review_pending(app):
    """Show pending outcomes and let user record them interactively."""
    from memora.core.outcomes import OutcomeTracker

    tracker = OutcomeTracker(app.repo)
    prompts = tracker.generate_outcome_prompts(limit=10)

    if not prompts:
        print(f"\n  {C.GREEN}All caught up!{C.RESET} No pending outcomes to record.")
        return

    print(f"\n  {C.BOLD}Pending Outcomes ({len(prompts)}):{C.RESET}\n")
    for i, p in enumerate(prompts, 1):
        icon = NODE_ICONS.get(p["node_type"], " ")
        print(f"    {C.CYAN}[{i}]{C.RESET} {icon} {p['prompt']}")
        print(f"        {C.DIM}({p['node_type']} — {p['age_days']} days old){C.RESET}")

    choice = prompt("\nRecord outcome for # (or 'skip'): ")
    if choice in ("skip", "s", ""):
        return

    try:
        selected = prompts[int(choice) - 1]
    except (ValueError, IndexError):
        print(f"  {C.RED}Invalid selection{C.RESET}")
        return

    outcome_text = prompt("What happened? ")
    if not outcome_text:
        return

    print(f"\n  Rating:")
    print(f"    {C.GREEN}[p]{C.RESET} Positive")
    print(f"    {C.YELLOW}[n]{C.RESET} Neutral")
    print(f"    {C.RED}[x]{C.RESET} Negative")
    print(f"    {C.MAGENTA}[m]{C.RESET} Mixed")

    rating_map = {"p": "positive", "n": "neutral", "x": "negative", "m": "mixed"}
    rating_choice = prompt("Rating: ")
    rating = rating_map.get(rating_choice, "neutral")

    result = tracker.record_outcome(
        node_id=selected["node_id"],
        text=outcome_text,
        rating=rating,
    )
    print(f"\n  {C.GREEN}Outcome recorded{C.RESET} for '{result['title']}' ({rating})")


def _record_outcome(app):
    """Record an outcome for a specific node found by search."""
    from memora.core.outcomes import OutcomeTracker

    query = prompt("Search for node: ")
    if not query:
        return

    results = app.repo.search_nodes_ilike(query, limit=10)
    # Filter to DECISION/GOAL/COMMITMENT
    results = [r for r in results if r["node_type"] in ("DECISION", "GOAL", "COMMITMENT")]

    if not results:
        print(f"  {C.DIM}No decision/goal/commitment nodes found{C.RESET}")
        return

    for i, n in enumerate(results, 1):
        icon = NODE_ICONS.get(n["node_type"], " ")
        print(f"    {C.DIM}{i}.{C.RESET} {icon} {n['title']}  {C.DIM}({n['node_type']}){C.RESET}")

    idx = prompt("Select #: ")
    try:
        node = results[int(idx) - 1]
    except (ValueError, IndexError):
        return

    outcome_text = prompt("What happened? ")
    if not outcome_text:
        return

    rating_map = {"p": "positive", "n": "neutral", "x": "negative", "m": "mixed"}
    rating_choice = prompt("Rating (p/n/x/m): ")
    rating = rating_map.get(rating_choice, "neutral")

    tracker = OutcomeTracker(app.repo)
    result = tracker.record_outcome(
        node_id=node["id"],
        text=outcome_text,
        rating=rating,
    )
    print(f"\n  {C.GREEN}Outcome recorded{C.RESET} for '{result['title']}' ({rating})")


def _show_stats(app):
    """Display outcome statistics."""
    from memora.core.outcomes import OutcomeTracker

    tracker = OutcomeTracker(app.repo)
    stats = tracker.get_outcome_stats()

    total = stats.get("total", 0)
    if total == 0:
        print(f"\n  {C.DIM}No outcomes recorded yet{C.RESET}")
        return

    print(f"\n  {C.BOLD}Outcome Statistics{C.RESET}")
    print(f"  Total outcomes: {C.BOLD}{total}{C.RESET}")
    print(f"  Positive rate: {horizontal_bar(stats.get('positive_rate', 0), width=20)}")

    by_rating = stats.get("by_rating", {})
    if by_rating:
        print(f"\n  {C.BOLD}By Rating:{C.RESET}")
        color_map = {
            "positive": C.GREEN,
            "neutral": C.YELLOW,
            "negative": C.RED,
            "mixed": C.MAGENTA,
        }
        for rating, count in sorted(by_rating.items()):
            color = color_map.get(rating, C.DIM)
            bar_val = count / total if total > 0 else 0
            print(f"    {color}●{C.RESET} {rating:10s} {count:3d}  {horizontal_bar(bar_val, width=15, color=color)}")
