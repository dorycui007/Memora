"""Actions command — execute kinetic graph operations interactively."""

from __future__ import annotations

from uuid import UUID

from cli.rendering import C, NODE_ICONS, divider, menu_option, prompt, subcommand_header


def cmd_actions(app):
    """Interactive action executor: select node, see available actions, execute."""
    while True:
        subcommand_header(
            title="ACTIONS",
            symbol="◉",
            color=C.ACCENT,
            taglines=["Kinetic graph operations · Execute and track"],
            border="simple",
        )
        print(menu_option("1", "Execute action",  "Pick a node and run an action"))
        print(menu_option("2", "Action history",  "View past actions"))
        print()

        choice = prompt("actions> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _execute_action(app)
        elif choice == "2":
            _show_history(app)


def _execute_action(app):
    """Select a node, show available actions, and execute one."""
    from memora.core.actions import ActionEngine
    from memora.graph.models import ActionType

    query = prompt("Search for a node (title): ")
    if not query:
        return

    results = app.repo.search_nodes_ilike(query, limit=10)
    if not results:
        print(f"  {C.DIM}No nodes found matching '{query}'{C.RESET}")
        return

    print(f"\n  {C.BOLD}Matching nodes:{C.RESET}")
    for i, n in enumerate(results, 1):
        icon = NODE_ICONS.get(n["node_type"], " ")
        print(f"    {C.DIM}{i:2}.{C.RESET} {icon} {n['title']}  {C.DIM}({n['node_type']}){C.RESET}")

    idx = prompt("Select node #: ")
    try:
        node = results[int(idx) - 1]
    except (ValueError, IndexError):
        print(f"  {C.RED}Invalid selection{C.RESET}")
        return

    node_id = node["id"]
    engine = ActionEngine(app.repo)
    available = engine.get_available_actions(node_id)

    if not available:
        print(f"  {C.DIM}No actions available for this node{C.RESET}")
        return

    print(f"\n  {C.BOLD}Available actions for '{node['title']}':{C.RESET}")
    for i, action in enumerate(available, 1):
        print(f"    {C.CYAN}[{i}]{C.RESET} {action['label']}")

    action_idx = prompt("Select action #: ")
    try:
        selected = available[int(action_idx) - 1]
    except (ValueError, IndexError):
        print(f"  {C.RED}Invalid selection{C.RESET}")
        return

    action_type = ActionType(selected["action_type"])
    params = {"node_id": node_id}

    # Gather action-specific parameters
    if action_type == ActionType.ADVANCE_GOAL:
        progress = prompt("New progress (0.0-1.0): ")
        try:
            params["progress"] = float(progress)
        except ValueError:
            pass
        milestone = prompt("Milestone (optional): ")
        if milestone:
            params["milestone"] = milestone

    elif action_type == ActionType.ARCHIVE_GOAL:
        reason = prompt("Reason for archiving: ")
        params["reason"] = reason

    elif action_type == ActionType.RECORD_OUTCOME:
        outcome_text = prompt("Outcome description: ")
        params["outcome_text"] = outcome_text
        rating = prompt("Rating (positive/neutral/negative/mixed): ")
        if rating in ("positive", "neutral", "negative", "mixed"):
            params["rating"] = rating
        else:
            params["rating"] = "neutral"

    elif action_type == ActionType.PROMOTE_IDEA:
        title = prompt(f"Project title [{node['title']}]: ")
        if title:
            params["project_title"] = title

    elif action_type == ActionType.LINK_ENTITIES:
        target_query = prompt("Search for target node: ")
        targets = app.repo.search_nodes_ilike(target_query, limit=5)
        if not targets:
            print(f"  {C.DIM}No target nodes found{C.RESET}")
            return
        for i, t in enumerate(targets, 1):
            icon = NODE_ICONS.get(t["node_type"], " ")
            print(f"    {C.DIM}{i}.{C.RESET} {icon} {t['title']}")
        tidx = prompt("Select target #: ")
        try:
            target = targets[int(tidx) - 1]
        except (ValueError, IndexError):
            return
        params["source_id"] = node_id
        params["target_id"] = target["id"]

    # Execute
    result = engine.execute(action_type, params)
    if result.get("success"):
        print(f"\n  {C.GREEN}Done:{C.RESET} {result.get('message', 'Action completed')}")
    else:
        print(f"\n  {C.RED}Failed:{C.RESET} {result.get('error', 'Unknown error')}")


def _show_history(app):
    """Display action audit trail."""
    history = app.repo.get_action_history(limit=20)
    if not history:
        print(f"\n  {C.DIM}No actions recorded yet{C.RESET}")
        return

    print(f"\n  {C.BOLD}Recent Actions ({len(history)}):{C.RESET}\n")
    for action in history:
        status_color = C.GREEN if action["status"] == "completed" else C.RED
        ts = str(action.get("executed_at", ""))[:19]
        print(
            f"    {status_color}●{C.RESET} {action['action_type']}"
            f"  {C.DIM}{ts}{C.RESET}"
        )
        if action.get("result", {}).get("message"):
            print(f"      {C.DIM}{action['result']['message']}{C.RESET}")
