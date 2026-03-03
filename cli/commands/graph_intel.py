"""Graph Intelligence command — interactive graph analytics dashboard.

Provides centrality rankings, community visualization, pathfinding,
anomaly reports, and link predictions.
"""

from __future__ import annotations

from cli.rendering import (
    C, NODE_ICONS,
    divider, horizontal_bar, prompt, subcommand_header,
)


def cmd_graph_intel(app):
    """Interactive graph intelligence command."""
    subcommand_header(
        title="GRAPH INTELLIGENCE",
        symbol="◆",
        color=C.INTEL,
        taglines=["Centrality · Communities · Pathfinding · Anomalies · Link Prediction"],
        border="simple",
    )

    from memora.core.graph_algorithms import GraphAlgorithms
    algo = GraphAlgorithms(app.repo)

    while True:
        print(f"\n  {C.BOLD}Analysis Options:{C.RESET}")
        print(f"    {C.INTEL}1{C.RESET}  Centrality Rankings (PageRank)")
        print(f"    {C.INTEL}2{C.RESET}  Degree Centrality")
        print(f"    {C.INTEL}3{C.RESET}  Betweenness Centrality (Bridge Entities)")
        print(f"    {C.INTEL}4{C.RESET}  Community Detection")
        print(f"    {C.INTEL}5{C.RESET}  Shortest Path")
        print(f"    {C.INTEL}6{C.RESET}  Link Prediction")
        print(f"    {C.INTEL}7{C.RESET}  Structural Anomalies")
        print(f"    {C.INTEL}8{C.RESET}  Temporal Anomalies")
        print(f"    {C.INTEL}9{C.RESET}  Full Intelligence Summary")
        print(f"    {C.DIM}q{C.RESET}  Back")

        choice = prompt("graph-intel> ").strip()
        if choice in ("q", "quit", ""):
            break
        elif choice == "1":
            _render_pagerank(algo)
        elif choice == "2":
            _render_degree_centrality(algo)
        elif choice == "3":
            _render_betweenness(algo)
        elif choice == "4":
            _render_communities(algo)
        elif choice == "5":
            _render_shortest_path(app, algo)
        elif choice == "6":
            _render_link_predictions(algo)
        elif choice == "7":
            _render_structural_anomalies(algo)
        elif choice == "8":
            _render_temporal_anomalies(algo)
        elif choice == "9":
            _render_full_summary(algo)
        else:
            print(f"  {C.DIM}Invalid option.{C.RESET}")


def _render_pagerank(algo):
    """Render PageRank centrality rankings."""
    print(f"\n{divider('═', C.INTEL)}")
    print(f"  {C.BOLD}{C.INTEL}PAGERANK CENTRALITY{C.RESET}  {C.DIM}most influential entities{C.RESET}")
    print(divider('─', C.INTEL))

    results = algo.pagerank()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    max_pr = results[0]["pagerank"] if results else 1.0
    for entry in results[:20]:
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(entry["pagerank"] / max(max_pr, 0.001), 15, C.INTEL)
        rank = entry["rank"]
        print(f"  {C.DIM}{rank:3}.{C.RESET} {icon} {C.BOLD}{entry['title'][:35]:<35}{C.RESET} "
              f"{bar}  {C.DIM}pr={entry['pagerank']:.4f}{C.RESET}")


def _render_degree_centrality(algo):
    """Render degree centrality rankings."""
    print(f"\n{divider('═', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}DEGREE CENTRALITY{C.RESET}  {C.DIM}most connected entities{C.RESET}")
    print(divider('─', C.CYAN))

    results = algo.degree_centrality()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    for i, entry in enumerate(results[:20], 1):
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(min(entry["centrality"] * 5, 1.0), 12, C.CYAN)
        print(f"  {C.DIM}{i:3}.{C.RESET} {icon} {C.BOLD}{entry['title'][:30]:<30}{C.RESET} "
              f"{bar}  in={entry['in_degree']} out={entry['out_degree']} "
              f"{C.DIM}total={entry['total_degree']}{C.RESET}")


def _render_betweenness(algo):
    """Render betweenness centrality (bridge entities)."""
    print(f"\n{divider('═', C.WARM)}")
    print(f"  {C.BOLD}{C.WARM}BETWEENNESS CENTRALITY{C.RESET}  {C.DIM}bridge/broker entities{C.RESET}")
    print(divider('─', C.WARM))

    results = algo.betweenness_centrality()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    # Only show non-zero entries
    nonzero = [r for r in results if r["betweenness"] > 0]
    if not nonzero:
        print(f"  {C.DIM}No bridge entities detected (all betweenness = 0).{C.RESET}")
        return

    max_bc = nonzero[0]["betweenness"]
    for i, entry in enumerate(nonzero[:20], 1):
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(entry["betweenness"] / max(max_bc, 0.001), 12, C.WARM)
        print(f"  {C.DIM}{i:3}.{C.RESET} {icon} {C.BOLD}{entry['title'][:35]:<35}{C.RESET} "
              f"{bar}  {C.DIM}bc={entry['betweenness']:.4f}{C.RESET}")


def _render_communities(algo):
    """Render detected communities."""
    print(f"\n{divider('═', C.MAGENTA)}")
    print(f"  {C.BOLD}{C.MAGENTA}COMMUNITIES{C.RESET}  {C.DIM}detected clusters via label propagation{C.RESET}")
    print(divider('─', C.MAGENTA))

    communities = algo.label_propagation_communities()
    if not communities:
        print(f"  {C.DIM}No communities detected.{C.RESET}")
        return

    for comm in communities[:15]:
        size = comm["size"]
        members = comm["members"]
        # Show type distribution
        type_counts: dict[str, int] = {}
        for m in members:
            type_counts[m["type"]] = type_counts.get(m["type"], 0) + 1
        type_str = ", ".join(f"{t}:{c}" for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True))

        print(f"\n  {C.MAGENTA}Community {comm['community_id']}{C.RESET}  "
              f"{C.BOLD}{size} members{C.RESET}  {C.DIM}({type_str}){C.RESET}")

        for m in members[:8]:
            icon = NODE_ICONS.get(m["type"], " ")
            print(f"    {icon} {m['title'][:45]}")
        if len(members) > 8:
            print(f"    {C.DIM}... and {len(members) - 8} more{C.RESET}")


def _render_shortest_path(app, algo):
    """Interactive shortest path finder."""
    print(f"\n{divider('═', C.GREEN)}")
    print(f"  {C.BOLD}{C.GREEN}SHORTEST PATH{C.RESET}  {C.DIM}Dijkstra pathfinding{C.RESET}")
    print(divider('─', C.GREEN))

    from_query = prompt("  From entity: ").strip()
    if not from_query:
        return
    to_query = prompt("  To entity: ").strip()
    if not to_query:
        return

    # Resolve entities
    from_nodes = app.repo.search_by_title(from_query, limit=5)
    to_nodes = app.repo.search_by_title(to_query, limit=5)

    if not from_nodes:
        print(f"  {C.DIM}No entity matching '{from_query}'.{C.RESET}")
        return
    if not to_nodes:
        print(f"  {C.DIM}No entity matching '{to_query}'.{C.RESET}")
        return

    source = from_nodes[0]
    target = to_nodes[0]

    print(f"\n  Finding paths: {C.BOLD}{source.title}{C.RESET} → {C.BOLD}{target.title}{C.RESET}")

    paths = algo.k_shortest_paths(str(source.id), str(target.id), k=3)
    if not paths:
        print(f"  {C.SIGNAL}No path found between these entities.{C.RESET}")
        return

    for pi, path_data in enumerate(paths, 1):
        print(f"\n  {C.GREEN}Path {pi}{C.RESET}  {C.DIM}{path_data['hops']} hops{C.RESET}")
        for si, step in enumerate(path_data["path"]):
            icon = NODE_ICONS.get(step["type"], " ")
            connector = "  →  " if si < len(path_data["path"]) - 1 else ""
            print(f"    {icon} {C.BOLD}{step['title'][:40]}{C.RESET}{connector}")


def _render_link_predictions(algo):
    """Render predicted missing links."""
    print(f"\n{divider('═', C.SIGNAL)}")
    print(f"  {C.BOLD}{C.SIGNAL}LINK PREDICTIONS{C.RESET}  {C.DIM}suggested missing connections{C.RESET}")
    print(divider('─', C.SIGNAL))

    predictions = algo.predict_links(top_k=15)
    if not predictions:
        print(f"  {C.DIM}No link predictions available.{C.RESET}")
        return

    for i, pred in enumerate(predictions, 1):
        cn = pred["common_neighbors"]
        print(f"  {C.DIM}{i:2}.{C.RESET} {C.BOLD}{pred['source_title'][:25]}{C.RESET} "
              f"{C.SIGNAL}···{C.RESET} "
              f"{C.BOLD}{pred['target_title'][:25]}{C.RESET}  "
              f"{C.DIM}score={pred['score']:.3f}  common={cn}{C.RESET}")


def _render_structural_anomalies(algo):
    """Render structural anomaly report."""
    print(f"\n{divider('═', C.DANGER)}")
    print(f"  {C.BOLD}{C.DANGER}STRUCTURAL ANOMALIES{C.RESET}")
    print(divider('─', C.DANGER))

    anomalies = algo.structural_anomalies()
    if not anomalies:
        print(f"  {C.CONFIRM}No structural anomalies detected.{C.RESET}")
        return

    for anomaly in anomalies:
        sev_color = C.DANGER if anomaly["severity"] == "warning" else C.SIGNAL if anomaly["severity"] == "info" else C.DIM
        print(f"\n  {sev_color}[{anomaly['severity'].upper()}]{C.RESET} "
              f"{C.BOLD}{anomaly['anomaly_type']}{C.RESET}")
        print(f"    {anomaly['description']}")
        details = anomaly.get("details", {})
        if "titles" in details:
            for title in details["titles"][:5]:
                print(f"      {C.DIM}- {title}{C.RESET}")


def _render_temporal_anomalies(algo):
    """Render temporal anomaly report."""
    print(f"\n{divider('═', C.SIGNAL)}")
    print(f"  {C.BOLD}{C.SIGNAL}TEMPORAL ANOMALIES{C.RESET}  {C.DIM}last 30 days{C.RESET}")
    print(divider('─', C.SIGNAL))

    anomalies = algo.temporal_anomalies()
    if not anomalies:
        print(f"  {C.CONFIRM}No temporal anomalies detected.{C.RESET}")
        return

    for anomaly in anomalies:
        sev_color = C.DANGER if anomaly["severity"] == "warning" else C.SIGNAL
        print(f"\n  {sev_color}[{anomaly['severity'].upper()}]{C.RESET} "
              f"{C.BOLD}{anomaly['anomaly_type']}{C.RESET}")
        print(f"    {anomaly['description']}")


def _render_full_summary(algo):
    """Render comprehensive intelligence summary."""
    print(f"\n{divider('═', C.INTEL)}")
    print(f"  {C.BOLD}{C.INTEL}FULL INTELLIGENCE SUMMARY{C.RESET}")
    print(divider('─', C.INTEL))

    summary = algo.graph_intelligence_summary()
    stats = summary["stats"]

    print(f"\n  {C.BOLD}Graph:{C.RESET} {stats['total_nodes']} nodes, "
          f"{stats['total_edges']} edges, "
          f"{stats['num_communities']} communities")
    print(f"  {C.BOLD}Anomalies:{C.RESET} {stats['num_anomalies']}  "
          f"{C.BOLD}Predictions:{C.RESET} {stats['num_predictions']}")

    # Top entities
    if summary["top_entities"]:
        print(f"\n  {C.BOLD}{C.INTEL}Top Entities (PageRank):{C.RESET}")
        for entry in summary["top_entities"][:5]:
            icon = NODE_ICONS.get(entry["type"], " ")
            print(f"    {entry['rank']:2}. {icon} {C.BOLD}{entry['title'][:35]}{C.RESET}  "
                  f"{C.DIM}pr={entry['pagerank']:.4f}{C.RESET}")

    # Communities overview
    if summary["communities"]:
        print(f"\n  {C.BOLD}{C.MAGENTA}Communities:{C.RESET}")
        for comm in summary["communities"][:5]:
            top_members = ", ".join(m["title"][:20] for m in comm["members"][:3])
            print(f"    Cluster {comm['community_id']}: {comm['size']} members — {top_members}")

    # Anomalies
    all_anomalies = summary["structural_anomalies"] + summary["temporal_anomalies"]
    if all_anomalies:
        print(f"\n  {C.BOLD}{C.DANGER}Anomalies:{C.RESET}")
        for a in all_anomalies[:5]:
            sev_color = C.DANGER if a["severity"] == "warning" else C.SIGNAL
            print(f"    {sev_color}[{a['severity'].upper()}]{C.RESET} {a['description'][:60]}")

    # Predictions
    if summary["predicted_links"]:
        print(f"\n  {C.BOLD}{C.SIGNAL}Predicted Links:{C.RESET}")
        for p in summary["predicted_links"][:5]:
            print(f"    {p['source_title'][:20]} {C.SIGNAL}···{C.RESET} {p['target_title'][:20]}  "
                  f"{C.DIM}score={p['score']:.3f}{C.RESET}")
