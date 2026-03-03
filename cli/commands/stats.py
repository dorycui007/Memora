"""Stats command — full graph statistics, network health, and charts."""

from __future__ import annotations

from cli.rendering import C, NODE_ICONS, NETWORK_ICONS, horizontal_bar, divider, stats_header, subcommand_header

_NET_COLORS = {
    "ACADEMIC": C.BLUE, "PROFESSIONAL": C.CYAN,
    "FINANCIAL": C.GREEN, "HEALTH": C.RED,
    "PERSONAL_GROWTH": C.MAGENTA, "SOCIAL": C.YELLOW,
    "VENTURES": C.ORANGE,
}


def cmd_stats(app):
    stats = app.repo.get_graph_stats()

    total_nodes = stats.get("node_count", 0)
    total_edges = stats.get("edge_count", 0)
    nodes_by_type = stats.get("type_breakdown", {})
    nodes_by_net = stats.get("network_breakdown", {})

    stats_header()

    print(f"    {C.BOLD}{total_nodes}{C.RESET} {C.DIM}nodes{C.RESET}    {C.BOLD}{total_edges}{C.RESET} {C.DIM}edges{C.RESET}")
    print()

    if nodes_by_type:
        print(f"  {C.BOLD}Nodes by Type{C.RESET}\n")
        max_count = max(nodes_by_type.values()) if nodes_by_type else 1
        for ntype, count in sorted(nodes_by_type.items(), key=lambda x: -x[1]):
            icon = NODE_ICONS.get(ntype, " ")
            ratio = count / max_count if max_count else 0
            bar_width = int(ratio * 25)
            print(f"    {icon} {ntype:<17} {C.CYAN}{'█' * bar_width}{C.DIM}{'░' * (25 - bar_width)}{C.RESET} {count}")
        print()

    if nodes_by_net:
        print(f"  {C.BOLD}Nodes by Network{C.RESET}\n")
        max_count = max(nodes_by_net.values()) if nodes_by_net else 1
        for net, count in sorted(nodes_by_net.items(), key=lambda x: -x[1]):
            icon = NETWORK_ICONS.get(net, f"[{net[0]}]")
            ratio = count / max_count if max_count else 0
            bar_width = int(ratio * 25)
            color = _NET_COLORS.get(net, C.WHITE)
            print(f"    {icon} {net:<17} {color}{'█' * bar_width}{C.DIM}{'░' * (25 - bar_width)}{C.RESET} {count}")

    if total_nodes > 0:
        density = total_edges / total_nodes
        print(f"\n  {C.BOLD}Edge Density:{C.RESET} {density:.2f} edges/node")

    try:
        commits = app.repo.get_open_commitments_raw(limit=100)
        if commits:
            print(f"\n  {C.BOLD}Open Commitments:{C.RESET} {len(commits)}")
    except Exception:
        pass

    # ── Network Health (absorbed from networks command) ──────────
    try:
        health = app.repo.get_latest_health_scores()
        if health:
            print(f"\n{divider()}")
            print(f"  {C.BOLD}Network Health{C.RESET}\n")
            for h in health:
                net = h.get("network", "?")
                status = h.get("status", "unknown")
                momentum = h.get("momentum", "stable")
                completion = h.get("commitment_completion_rate", 0)

                icon = NETWORK_ICONS.get(net, f"[{net[0]}]")
                status_color = {
                    "thriving": C.GREEN, "active": C.CYAN,
                    "stable": C.YELLOW, "falling_behind": C.RED,
                }.get(status, C.DIM)

                momentum_arrow = {"rising": f"{C.GREEN}^{C.RESET}",
                                  "stable": f"{C.YELLOW}-{C.RESET}",
                                  "declining": f"{C.RED}v{C.RESET}"}.get(momentum, "?")

                print(f"  {icon} {net:<17} {status_color}{status:<15}{C.RESET} "
                      f"{momentum_arrow}  completion: {horizontal_bar(completion, 12)}")
    except Exception:
        pass

    # ── Cross-Network Bridges ────────────────────────────────────
    try:
        bridges = app.repo.get_recent_bridges(limit=5)
        if bridges:
            print(f"\n{divider()}")
            print(f"  {C.BOLD}Recent Cross-Network Bridges{C.RESET}\n")
            for b in bridges:
                src = NETWORK_ICONS.get(b["source_network"], b["source_network"])
                tgt = NETWORK_ICONS.get(b["target_network"], b["target_network"])
                sim = b.get("similarity", 0)
                meaningful = b.get("meaningful")
                marker = f"{C.GREEN}meaningful{C.RESET}" if meaningful else f"{C.DIM}unvalidated{C.RESET}" if meaningful is None else f"{C.RED}spurious{C.RESET}"
                print(f"    {src} <==> {tgt}  sim={sim:.2f}  {marker}")
    except Exception:
        pass

    print()
