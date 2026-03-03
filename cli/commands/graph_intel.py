"""Graph Intelligence command — interactive graph analytics dashboard.

Provides centrality rankings, community visualization, pathfinding,
anomaly reports, and link predictions with rich contextual annotations.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from cli.rendering import (
    C, NODE_ICONS, NETWORK_ICONS, NETWORK_LABELS,
    divider, graph_intel_header, horizontal_bar, menu_option, prompt,
    spark_line, subcommand_header,
)

# ── Shared Helpers ────────────────────────────────────────────────

EDGE_TYPE_TO_CATEGORY = {
    "PART_OF": "structural", "CONTAINS": "structural", "SUBTASK_OF": "structural",
    "RELATED_TO": "associative", "SIMILAR_TO": "associative", "CONTRADICTS": "associative",
    "INSPIRED_BY": "associative", "COMPLEMENTS": "associative",
    "DERIVED_FROM": "provenance", "VERIFIED_BY": "provenance", "SOURCE_OF": "provenance",
    "PRECEDED_BY": "temporal", "EVOLVED_INTO": "temporal", "TRIGGERED": "temporal",
    "COMMITTED_TO": "personal", "DECIDED": "personal", "FELT_ABOUT": "personal",
    "KNOWS": "social", "COLLABORATES_WITH": "social", "REPORTS_TO": "social",
    "BRIDGES": "network", "MEMBER_OF": "network", "IMPACTS": "network",
}

CATEGORY_COLORS = {
    "structural": C.ACCENT, "associative": C.INTEL, "provenance": C.CYAN,
    "temporal": C.SIGNAL, "personal": C.WARM, "social": C.GREEN,
    "network": C.MAGENTA,
}

EDGE_VERBS = {
    "KNOWS": "knows", "COLLABORATES_WITH": "collaborates with",
    "RELATED_TO": "relates to", "DERIVED_FROM": "derives from",
    "SUBTASK_OF": "is subtask of", "PART_OF": "is part of", "TRIGGERED": "triggered",
    "COMMITTED_TO": "committed to", "PRECEDED_BY": "preceded by",
    "SIMILAR_TO": "is similar to", "CONTRADICTS": "contradicts",
    "INSPIRED_BY": "was inspired by", "COMPLEMENTS": "complements",
    "VERIFIED_BY": "verified by", "SOURCE_OF": "is source of",
    "EVOLVED_INTO": "evolved into", "DECIDED": "decided",
    "FELT_ABOUT": "felt about", "REPORTS_TO": "reports to",
    "BRIDGES": "bridges to", "MEMBER_OF": "is member of",
    "IMPACTS": "impacts", "CONTAINS": "contains",
}


def _freshness(decay: float) -> tuple[str, str]:
    """Return (label, color) for decay score."""
    if decay >= 0.7:
        return "fresh", C.CONFIRM
    elif decay >= 0.4:
        return "aging", C.SIGNAL
    return "stale", C.DANGER


def _confidence_dot(conf: float) -> str:
    """Confidence indicator with color."""
    if conf >= 0.8:
        return f"{C.CONFIRM}\u25cf{C.RESET}"
    elif conf >= 0.5:
        return f"{C.SIGNAL}\u25d0{C.RESET}"
    return f"{C.DIM}\u25cb{C.RESET}"


def _edge_type_counts(node_id: str, edges: list) -> dict[str, int]:
    """Count edge types touching a node from cached edge list."""
    counts: dict[str, int] = defaultdict(int)
    for src, tgt, attrs in edges:
        if src == node_id or tgt == node_id:
            counts[attrs.get("edge_type", "UNKNOWN")] += 1
    return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))


def _network_tags(networks: list[str], readable: bool = False) -> str:
    """Render inline network badges.

    When *readable* is True, use 4-char abbreviated labels instead of
    single-letter icons (e.g. [Acad] instead of [A]).
    """
    source = NETWORK_LABELS if readable else NETWORK_ICONS
    if not networks:
        return f"{C.DIM}no network{C.RESET}"
    return " ".join(source.get(n, f"{C.DIM}[{n[:4]}]{C.RESET}") for n in networks)


def _node_to_community(communities: list[dict]) -> dict[str, int]:
    """Build node_id -> community_id lookup from community results."""
    lookup: dict[str, int] = {}
    for comm in communities:
        for m in comm["members"]:
            lookup[m["node_id"]] = comm["community_id"]
    return lookup


def _top_edge_types_str(et_counts: dict[str, int], limit: int = 3,
                        readable: bool = False) -> str:
    """Format top N edge types as compact string.

    When *readable* is True, use human-friendly verb labels from
    ``EDGE_VERBS`` separated by `` · `` (e.g. "knows 3 · committed to 4").
    """
    items = list(et_counts.items())[:limit]
    if not items:
        return f"{C.DIM}no edges{C.RESET}"
    if readable:
        parts = []
        for t, c in items:
            verb = EDGE_VERBS.get(t, t.lower().replace("_", " "))
            parts.append(f"{C.BASE}{verb} {c}{C.RESET}")
        return f" {C.DIM}·{C.RESET} ".join(parts)
    return " ".join(f"{C.DIM}{t}:{c}{C.RESET}" for t, c in items)


def _section_header(title: str, color: str = C.INTEL) -> None:
    """Print a section sub-header."""
    print(f"\n  {color}{C.BOLD}{title}{C.RESET}")
    print(f"  {C.GHOST}{'─' * 50}{C.RESET}")


# ── Main Command ──────────────────────────────────────────────────

def cmd_graph_intel(app):
    """Interactive graph intelligence command."""
    graph_intel_header()

    from memora.core.graph_algorithms import GraphAlgorithms
    algo = GraphAlgorithms(app.repo)

    while True:
        print(f"\n  {C.BOLD}Analysis Options:{C.RESET}")
        print(menu_option("1", "Influence Map",       "PageRank with context and network distribution"))
        print(menu_option("2", "Connection Profile",   "Degree centrality with role classification"))
        print(menu_option("3", "Bridge Analysis",      "Betweenness centrality with resilience scoring"))
        print(menu_option("4", "Knowledge Clusters",   "Communities with cohesion and health signals"))
        print(menu_option("5", "Relationship Trace",   "Shortest path with edge context and narrative"))
        print(menu_option("6", "Missing Connections",  "Link prediction with neighbor analysis"))
        print(menu_option("7", "Graph Health",         "Structural anomalies with remediation"))
        print(menu_option("8", "Activity Pulse",       "Temporal anomalies with timeline and heatmap"))
        print(menu_option("9", "Intelligence Briefing", "Comprehensive report with recommendations"))
        print(menu_option("q", "Back",                 ""))

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


# ── Option 1: Influence Map (PageRank) ────────────────────────────

def _render_pagerank(algo):
    """Render PageRank centrality with network context and takeaways."""
    print(f"\n{divider('═', C.INTEL)}")
    print(f"  {C.BOLD}{C.INTEL}INFLUENCE MAP{C.RESET}  {C.DIM}PageRank centrality with context{C.RESET}")
    print(divider('─', C.INTEL))

    results = algo.pagerank()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    g = algo.graph
    top20 = results[:20]
    max_pr = top20[0]["pagerank"] if top20 else 1.0

    # Check bridges for top 5
    top5_ids = [e["node_id"] for e in top20[:5]]
    try:
        bridges = algo.repo.get_bridges_for_nodes(top5_ids)
    except Exception:
        bridges = []
    bridge_nodes = {b.get("source_id") or b.get("target_id") for b in bridges}

    for entry in top20:
        nid = entry["node_id"]
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(entry["pagerank"] / max(max_pr, 0.001), 15, C.INTEL)
        node = g["nodes"].get(nid, {})
        nets = _network_tags(node.get("networks", []))
        decay = node.get("decay_score", 0.5)
        fresh_label, fresh_color = _freshness(decay)
        conf_dot = _confidence_dot(node.get("confidence", 0.5))

        et = _edge_type_counts(nid, g["edges"])
        et_str = _top_edge_types_str(et)

        bridge_mark = f" {C.WARM}◆bridge{C.RESET}" if nid in bridge_nodes else ""

        print(f"  {C.DIM}{entry['rank']:3}.{C.RESET} {icon} {C.BOLD}{entry['title'][:32]:<32}{C.RESET} "
              f"{bar}  {conf_dot} {fresh_color}{fresh_label}{C.RESET}{bridge_mark}")
        print(f"       {nets}  {et_str}")

    # ── Influence by Network ──
    net_counts: dict[str, int] = defaultdict(int)
    for entry in top20:
        nid = entry["node_id"]
        for n in g["nodes"].get(nid, {}).get("networks", []):
            net_counts[n] += 1

    if net_counts:
        _section_header("Influence by Network", C.INTEL)
        total = sum(net_counts.values())
        for net, cnt in sorted(net_counts.items(), key=lambda x: x[1], reverse=True):
            pct = cnt / total
            badge = NETWORK_ICONS.get(net, net[:3])
            bar = horizontal_bar(pct, 12, C.INTEL)
            print(f"    {badge} {net:<20} {bar}  {C.DIM}{cnt} entities{C.RESET}")

    # ── Influence by Type ──
    type_counts: dict[str, int] = defaultdict(int)
    for entry in top20:
        type_counts[entry["type"]] += 1
    if type_counts:
        _section_header("Influence by Type", C.INTEL)
        for t, cnt in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            icon = NODE_ICONS.get(t, " ")
            print(f"    {icon} {t:<20} {C.BOLD}{cnt}{C.RESET}")

    # ── Takeaways ──
    _section_header("Takeaways", C.INTEL)
    takeaways = []

    # Dominant network
    if net_counts:
        dom_net, dom_cnt = max(net_counts.items(), key=lambda x: x[1])
        dom_pct = dom_cnt / max(sum(net_counts.values()), 1) * 100
        if dom_pct > 50:
            takeaways.append(f"{dom_net} dominates influence at {dom_pct:.0f}% of top entities")

    # Stale entities in top 10
    stale_top10 = []
    for entry in top20[:10]:
        nid = entry["node_id"]
        node = g["nodes"].get(nid, {})
        if node.get("decay_score", 0.5) < 0.4:
            stale_top10.append(entry["title"])
    if stale_top10:
        takeaways.append(f"{len(stale_top10)} stale entit{'y' if len(stale_top10)==1 else 'ies'} in top 10 — consider refreshing: {', '.join(stale_top10[:3])}")

    # Type skew
    if type_counts:
        dom_type, dom_type_cnt = max(type_counts.items(), key=lambda x: x[1])
        if dom_type_cnt >= len(top20) * 0.5:
            takeaways.append(f"Heavy {dom_type} concentration — influence may be narrow")

    if not takeaways:
        takeaways.append("Influence is well-distributed across networks and types")
    for t in takeaways:
        print(f"    {C.SIGNAL}→{C.RESET} {t}")


# ── Option 2: Connection Profile (Degree Centrality) ─────────────

def _render_degree_centrality(algo):
    """Render degree centrality with role classification and patterns."""
    print(f"\n{divider('═', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}CONNECTION PROFILE{C.RESET}  {C.DIM}degree centrality with role analysis{C.RESET}")
    print(divider('─', C.CYAN))

    results = algo.degree_centrality()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    g = algo.graph
    top20 = results[:20]

    incoming_hubs, outgoing_hubs, balanced = [], [], []

    for i, entry in enumerate(top20, 1):
        nid = entry["node_id"]
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(min(entry["centrality"] * 5, 1.0), 20, C.CYAN)
        node = g["nodes"].get(nid, {})
        nets = _network_tags(node.get("networks", []), readable=True)

        total = entry["total_degree"]
        in_d = entry["in_degree"]
        out_d = entry["out_degree"]
        # pct is rendered by horizontal_bar

        # Role classification
        if total > 0:
            in_pct = in_d / total
            out_pct = out_d / total
        else:
            in_pct = out_pct = 0.5

        if in_pct >= 0.7:
            role = f"{C.CYAN}← receiver{C.RESET}"
            incoming_hubs.append(entry["title"])
        elif out_pct >= 0.7:
            role = f"{C.WARM}→ connector{C.RESET}"
            outgoing_hubs.append(entry["title"])
        else:
            role = f"{C.CONFIRM}⇄ balanced{C.RESET}"
            balanced.append(entry["title"])

        entity_type = entry["type"].replace("_", " ").title()

        et = _edge_type_counts(nid, g["edges"])
        et_str = _top_edge_types_str(et, readable=True)

        # Line 1: rank, icon, name, entity type + role
        name = entry["title"][:30]
        type_role = f"{C.DIM}{entity_type}{C.RESET} · {role}"
        print(f"  {C.DIM}{i:>3}{C.RESET}  {icon} {C.BOLD}{name}{C.RESET}"
              f"  {type_role}")
        # Line 2: bar chart, total connections with directional breakdown
        conn_detail = (f"{C.BASE}{total} connections{C.RESET} "
                       f"{C.DIM}(← {in_d} in · → {out_d} out){C.RESET}")
        print(f"       {bar}   {conn_detail}")
        # Line 3: edge verbs + network badges
        print(f"       {et_str}  {nets}")
        # Blank line between entities
        print()

    # ── Connection Patterns ──
    _section_header("Connection Patterns", C.CYAN)
    if incoming_hubs:
        print(f"    {C.CYAN}← Receivers:{C.RESET} {', '.join(incoming_hubs[:5])}")
    if outgoing_hubs:
        print(f"    {C.WARM}→ Connectors:{C.RESET} {', '.join(outgoing_hubs[:5])}")
    if balanced:
        print(f"    {C.CONFIRM}⇄ Balanced:{C.RESET} {', '.join(balanced[:5])}")

    # ── Edge Category Distribution ──
    cat_counts: dict[str, int] = defaultdict(int)
    for entry in top20:
        nid = entry["node_id"]
        et = _edge_type_counts(nid, g["edges"])
        for etype, cnt in et.items():
            cat = EDGE_TYPE_TO_CATEGORY.get(etype, "other")
            cat_counts[cat] += cnt

    if cat_counts:
        _section_header("Edge Category Distribution", C.CYAN)
        total_cat = sum(cat_counts.values())
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
            pct = cnt / max(total_cat, 1)
            color = CATEGORY_COLORS.get(cat, C.DIM)
            bar = horizontal_bar(pct, 12, color)
            print(f"    {color}{cat:<15}{C.RESET} {bar}  {C.DIM}{cnt}{C.RESET}")

    # ── Low-Connection High-Value ──
    low_conn_high_val = []
    for entry in results:
        nid = entry["node_id"]
        node = g["nodes"].get(nid, {})
        if node.get("confidence", 0) >= 0.8 and entry["total_degree"] <= 2:
            low_conn_high_val.append(entry)
    if low_conn_high_val:
        _section_header("Low-Connection High-Value", C.CYAN)
        print(f"  {C.DIM}  High confidence (≥0.8) but ≤2 connections — candidates for linking{C.RESET}")
        for entry in low_conn_high_val[:8]:
            icon = NODE_ICONS.get(entry["type"], " ")
            node = g["nodes"].get(entry["node_id"], {})
            conf_dot = _confidence_dot(node.get("confidence", 0.5))
            print(f"    {icon} {conf_dot} {entry['title'][:40]}  {C.DIM}deg={entry['total_degree']}{C.RESET}")


# ── Option 3: Bridge Analysis (Betweenness) ──────────────────────

def _render_betweenness(algo):
    """Render betweenness centrality with community bridging and resilience."""
    print(f"\n{divider('═', C.WARM)}")
    print(f"  {C.BOLD}{C.WARM}BRIDGE ANALYSIS{C.RESET}  {C.DIM}betweenness centrality with resilience{C.RESET}")
    print(divider('─', C.WARM))

    results = algo.betweenness_centrality()
    if not results:
        print(f"  {C.DIM}No data available.{C.RESET}")
        return

    nonzero = [r for r in results if r["betweenness"] > 0]
    if not nonzero:
        print(f"  {C.DIM}No bridge entities detected (all betweenness = 0).{C.RESET}")
        return

    g = algo.graph
    communities = algo.label_propagation_communities()
    n2c = _node_to_community(communities)
    max_bc = nonzero[0]["betweenness"]

    for i, entry in enumerate(nonzero[:20], 1):
        nid = entry["node_id"]
        icon = NODE_ICONS.get(entry["type"], " ")
        bar = horizontal_bar(entry["betweenness"] / max(max_bc, 0.001), 12, C.WARM)
        node = g["nodes"].get(nid, {})
        nets = _network_tags(node.get("networks", []))

        # Which communities does this node's neighbors belong to?
        neighbor_comms: set[int] = set()
        for src, tgt, _ in g["edges"]:
            neighbor = tgt if src == nid else (src if tgt == nid else None)
            if neighbor and neighbor in n2c:
                neighbor_comms.add(n2c[neighbor])
        own_comm = n2c.get(nid)
        if own_comm is not None:
            neighbor_comms.discard(own_comm)

        comm_str = ""
        if neighbor_comms:
            bridge_comms = sorted(neighbor_comms)[:3]
            if own_comm is not None:
                comm_str = f" {C.DIM}C{own_comm}↔C{',C'.join(str(c) for c in bridge_comms)}{C.RESET}"
            else:
                comm_str = f" {C.DIM}↔C{',C'.join(str(c) for c in bridge_comms)}{C.RESET}"

        print(f"  {C.DIM}{i:3}.{C.RESET} {icon} {C.BOLD}{entry['title'][:32]:<32}{C.RESET} "
              f"{bar}  {C.DIM}bc={entry['betweenness']:.4f}{C.RESET}{comm_str}")
        print(f"       {nets}")

    # ── Network Bridging Summary ──
    # Count bridge entities per network pair
    network_pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entry in nonzero[:20]:
        nid = entry["node_id"]
        node = g["nodes"].get(nid, {})
        node_nets = node.get("networks", [])
        # Check neighbors for different networks
        neighbor_nets: set[str] = set()
        for src, tgt, _ in g["edges"]:
            neighbor = tgt if src == nid else (src if tgt == nid else None)
            if neighbor:
                neighbor_node = g["nodes"].get(neighbor, {})
                for nn in neighbor_node.get("networks", []):
                    if nn not in node_nets:
                        neighbor_nets.add(nn)
        for nn in node_nets:
            for on in neighbor_nets:
                pair = tuple(sorted([nn, on]))
                if entry["title"] not in network_pairs[pair]:
                    network_pairs[pair].append(entry["title"])

    if network_pairs:
        _section_header("Network Bridging Summary", C.WARM)
        for pair, titles in sorted(network_pairs.items(), key=lambda x: len(x[1])):
            n1, n2 = pair
            b1 = NETWORK_ICONS.get(n1, n1[:3])
            b2 = NETWORK_ICONS.get(n2, n2[:3])
            count = len(titles)
            alert = f" {C.DANGER}⚠ single point of failure{C.RESET}" if count == 1 else ""
            print(f"    {b1} ↔ {b2}  {C.BOLD}{count}{C.RESET} bridge(s){alert}")
            for t in titles[:3]:
                print(f"      {C.DIM}· {t}{C.RESET}")

    # ── Resilience Score ──
    if network_pairs:
        min_bridges = min(len(v) for v in network_pairs.values()) if network_pairs else 0
        spof_count = sum(1 for v in network_pairs.values() if len(v) == 1)
        resilience = max(0, 1.0 - (spof_count / max(len(network_pairs), 1)))
        r_label, r_color = ("strong", C.CONFIRM) if resilience >= 0.7 else (("moderate", C.SIGNAL) if resilience >= 0.4 else ("fragile", C.DANGER))
        _section_header("Resilience", C.WARM)
        print(f"    Score: {r_color}{C.BOLD}{resilience:.0%}{C.RESET} ({r_label})  "
              f"{C.DIM}min bridges per pair: {min_bridges}, single-point pairs: {spof_count}{C.RESET}")


# ── Option 4: Knowledge Clusters (Communities) ───────────────────

def _render_communities(algo):
    """Render communities with cohesion, health, and cross-cluster bridges."""
    print(f"\n{divider('═', C.MAGENTA)}")
    print(f"  {C.BOLD}{C.MAGENTA}KNOWLEDGE CLUSTERS{C.RESET}  {C.DIM}communities with health metrics{C.RESET}")
    print(divider('─', C.MAGENTA))

    communities = algo.label_propagation_communities()
    if not communities:
        print(f"  {C.DIM}No communities detected.{C.RESET}")
        return

    g = algo.graph
    pr_results = algo.pagerank()
    pr_rank = {e["node_id"]: e["rank"] for e in pr_results}

    # Fetch pending outcomes once
    try:
        pending_outcomes = algo.repo.get_pending_outcomes()
    except Exception:
        pending_outcomes = []
    pending_node_ids = {str(o.get("node_id", "")) for o in pending_outcomes}

    cluster_health_rows = []

    for comm in communities[:12]:
        member_ids = {m["node_id"] for m in comm["members"]}
        size = comm["size"]

        # Network distribution
        net_counts: dict[str, int] = defaultdict(int)
        total_decay = 0.0
        total_conf = 0.0
        for m in comm["members"]:
            node = g["nodes"].get(m["node_id"], {})
            for n in node.get("networks", []):
                net_counts[n] += 1
            total_decay += node.get("decay_score", 0.5)
            total_conf += node.get("confidence", 0.5)

        avg_decay = total_decay / max(size, 1)
        avg_conf = total_conf / max(size, 1)
        dom_net = max(net_counts, key=net_counts.get) if net_counts else "none"
        dom_pct = net_counts.get(dom_net, 0) / max(size, 1) * 100

        # Cohesion: internal edges / possible internal edges
        internal_edges = 0
        internal_et: dict[str, int] = defaultdict(int)
        cross_cluster_edges = []
        for src, tgt, attrs in g["edges"]:
            if src in member_ids and tgt in member_ids:
                internal_edges += 1
                internal_et[attrs.get("edge_type", "UNKNOWN")] += 1
            elif src in member_ids or tgt in member_ids:
                cross_cluster_edges.append((src, tgt, attrs))

        possible = size * (size - 1) / 2 if size > 1 else 1
        cohesion = internal_edges / max(possible, 1)

        # Type distribution
        type_counts: dict[str, int] = defaultdict(int)
        for m in comm["members"]:
            type_counts[m["type"]] = type_counts.get(m["type"], 0) + 1
        type_str = ", ".join(f"{t}:{c}" for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True))

        # Pending outcomes in this cluster
        cluster_pending = [nid for nid in member_ids if nid in pending_node_ids]

        # Health status
        fresh_label, fresh_color = _freshness(avg_decay)
        alert = ""
        if cluster_pending:
            alert = f" {C.DANGER}{len(cluster_pending)} pending outcome(s){C.RESET}"
        elif avg_decay < 0.4:
            alert = f" {C.SIGNAL}needs refresh{C.RESET}"

        print(f"\n  {C.MAGENTA}Cluster {comm['community_id']}{C.RESET}  "
              f"{C.BOLD}{size} members{C.RESET}  "
              f"cohesion={C.BOLD}{cohesion:.2f}{C.RESET}  "
              f"{fresh_color}{fresh_label}{C.RESET}{alert}")
        print(f"    {C.DIM}({type_str}){C.RESET}  "
              f"dominant: {NETWORK_ICONS.get(dom_net, dom_net)} {dom_pct:.0f}%  "
              f"avg conf={avg_conf:.2f}")

        # Key members with PR rank
        for m in comm["members"][:6]:
            icon = NODE_ICONS.get(m["type"], " ")
            rank = pr_rank.get(m["node_id"])
            rank_str = f" {C.INTEL}#{rank}{C.RESET}" if rank and rank <= 20 else ""
            print(f"    {icon} {m['title'][:42]}{rank_str}")
        if len(comm["members"]) > 6:
            print(f"    {C.DIM}... and {len(comm['members']) - 6} more{C.RESET}")

        # Internal edge profile
        if internal_et:
            top_et = list(sorted(internal_et.items(), key=lambda x: x[1], reverse=True))[:4]
            print(f"    {C.DIM}edges: {' '.join(f'{t}:{c}' for t, c in top_et)}{C.RESET}")

        cluster_health_rows.append({
            "id": comm["community_id"], "size": size, "cohesion": cohesion,
            "avg_decay": avg_decay, "alert": bool(alert),
        })

    # ── Cluster Health Summary ──
    if cluster_health_rows:
        _section_header("Cluster Health Summary", C.MAGENTA)
        print(f"    {C.DIM}{'ID':>4}  {'Size':>5}  {'Cohesion':>9}  {'Freshness':>10}  Status{C.RESET}")
        for row in cluster_health_rows:
            fl, fc = _freshness(row["avg_decay"])
            status = f"{C.DANGER}⚠{C.RESET}" if row["alert"] else f"{C.CONFIRM}✓{C.RESET}"
            print(f"    {row['id']:4}  {row['size']:5}  {row['cohesion']:9.3f}  "
                  f"{fc}{fl:>10}{C.RESET}  {status}")

    # ── Isolated Nodes ──
    all_community_nodes = set()
    for comm in communities:
        if comm["size"] > 1:
            for m in comm["members"]:
                all_community_nodes.add(m["node_id"])
    isolated = [nid for nid in g["nodes"] if nid not in all_community_nodes]
    if isolated:
        _section_header("Isolated Nodes", C.MAGENTA)
        print(f"    {C.DIM}{len(isolated)} node(s) not in any multi-member community{C.RESET}")
        for nid in isolated[:5]:
            node = g["nodes"][nid]
            icon = NODE_ICONS.get(node["type"], " ")
            print(f"    {icon} {node['title'][:40]}  {_network_tags(node.get('networks', []))}")
        if len(isolated) > 5:
            print(f"    {C.DIM}... and {len(isolated) - 5} more{C.RESET}")


# ── Option 5: Relationship Trace (Shortest Path) ────────────────

def _render_shortest_path(app, algo):
    """Interactive shortest path with edge context and narrative."""
    print(f"\n{divider('═', C.GREEN)}")
    print(f"  {C.BOLD}{C.GREEN}RELATIONSHIP TRACE{C.RESET}  {C.DIM}path with edge context{C.RESET}")
    print(divider('─', C.GREEN))

    from_query = prompt("  From entity: ").strip()
    if not from_query:
        return
    to_query = prompt("  To entity: ").strip()
    if not to_query:
        return

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

    from memora.graph.repository import YOU_NODE_ID
    excluded = {YOU_NODE_ID} - {str(source.id), str(target.id)}

    paths = algo.k_shortest_paths(str(source.id), str(target.id), k=3, excluded_nodes=excluded)
    if not paths:
        print(f"  {C.SIGNAL}No path found between these entities.{C.RESET}")
        return

    g = algo.graph
    adj = g["adj"]

    for pi, path_data in enumerate(paths, 1):
        steps = path_data["path"]
        # Compute confidence floor and build narrative
        min_conf = 1.0
        narrative_parts = []

        print(f"\n  {C.GREEN}Path {pi}{C.RESET}  {C.DIM}{path_data['hops']} hops{C.RESET}")

        for si, step in enumerate(steps):
            nid = step["node_id"]
            icon = NODE_ICONS.get(step["type"], " ")
            node = g["nodes"].get(nid, {})
            nets = _network_tags(node.get("networks", []))

            if si < len(steps) - 1:
                next_nid = steps[si + 1]["node_id"]
                # Look up edge details from adj (try both directions)
                edge_attrs = adj.get(nid, {}).get(next_nid, adj.get(next_nid, {}).get(nid, {}))
                etype = edge_attrs.get("edge_type", "?")
                weight = edge_attrs.get("weight", 0)
                conf = edge_attrs.get("confidence", 0.5)
                min_conf = min(min_conf, conf)

                verb = EDGE_VERBS.get(etype, etype.lower().replace("_", " "))
                narrative_parts.append(f"{step['title'][:25]} {verb}")

                # Check network change
                next_node = g["nodes"].get(next_nid, {})
                node_nets = set(node.get("networks", []))
                next_nets = set(next_node.get("networks", []))
                crossing = ""
                if node_nets and next_nets and not node_nets & next_nets:
                    crossing = f" {C.SIGNAL}⚡network crossing{C.RESET}"

                conf_dot = _confidence_dot(conf)
                print(f"    {icon} {C.BOLD}{step['title'][:38]}{C.RESET}  {nets}")
                print(f"      {C.DIM}──[{etype} w={weight:.2f}]──{C.RESET} {conf_dot}{crossing}")
            else:
                narrative_parts.append(step["title"][:25])
                print(f"    {icon} {C.BOLD}{step['title'][:38]}{C.RESET}  {nets}")

        # Confidence floor
        conf_color = C.CONFIRM if min_conf >= 0.7 else (C.SIGNAL if min_conf >= 0.4 else C.DANGER)
        print(f"    {C.DIM}Confidence floor:{C.RESET} {conf_color}{min_conf:.0%}{C.RESET}")

        # Path narrative
        if narrative_parts:
            narrative = " → ".join(narrative_parts)
            print(f"    {C.DIM}Narrative:{C.RESET} {C.ITALIC}{narrative}{C.RESET}")

    # ── Shared Connections ──
    try:
        shared = app.repo.get_shared_connections([str(source.id), str(target.id)])
        if shared:
            _section_header("Shared Connections", C.GREEN)
            for s in shared[:5]:
                title = s.get("title", s.get("node_id", "?"))
                print(f"    {C.DIM}·{C.RESET} {title}")
    except Exception:
        pass


# ── Option 6: Missing Connections (Link Prediction) ──────────────

def _render_link_predictions(algo):
    """Render link predictions with neighbor analysis and context."""
    print(f"\n{divider('═', C.SIGNAL)}")
    print(f"  {C.BOLD}{C.SIGNAL}MISSING CONNECTIONS{C.RESET}  {C.DIM}link prediction with context{C.RESET}")
    print(divider('─', C.SIGNAL))

    predictions = algo.predict_links(top_k=15)
    if not predictions:
        print(f"  {C.DIM}No link predictions available.{C.RESET}")
        return

    g = algo.graph
    same_net_count = 0
    cross_net_count = 0

    for i, pred in enumerate(predictions, 1):
        src_node = g["nodes"].get(pred["source_id"], {})
        tgt_node = g["nodes"].get(pred["target_id"], {})
        src_nets = set(src_node.get("networks", []))
        tgt_nets = set(tgt_node.get("networks", []))

        is_cross = bool(src_nets and tgt_nets and not src_nets & tgt_nets)
        if is_cross:
            cross_net_count += 1
            cross_flag = f" {C.WARM}⚡cross-network{C.RESET}"
        else:
            same_net_count += 1
            cross_flag = ""

        cn_ids = pred.get("common_neighbor_ids", [])

        # Suggested edge type: most frequent among common neighbors' edges
        et_freq: dict[str, int] = defaultdict(int)
        for cn_id in cn_ids:
            for src, tgt, attrs in g["edges"]:
                if src == cn_id or tgt == cn_id:
                    if src == pred["source_id"] or tgt == pred["source_id"] or \
                       src == pred["target_id"] or tgt == pred["target_id"]:
                        et_freq[attrs.get("edge_type", "UNKNOWN")] += 1
        suggested_et = max(et_freq, key=et_freq.get) if et_freq else "RELATED_TO"

        print(f"  {C.DIM}{i:2}.{C.RESET} {C.BOLD}{pred['source_title'][:24]}{C.RESET} "
              f"{C.SIGNAL}···{C.RESET} "
              f"{C.BOLD}{pred['target_title'][:24]}{C.RESET}  "
              f"{C.DIM}score={pred['score']:.3f}{C.RESET}{cross_flag}")

        # Common neighbor names
        if cn_ids:
            cn_names = []
            for cn_id in cn_ids[:4]:
                cn_node = g["nodes"].get(cn_id, {})
                cn_names.append(cn_node.get("title", "?")[:20])
            cn_str = ", ".join(cn_names)
            extra = f" +{len(cn_ids)-4}" if len(cn_ids) > 4 else ""
            print(f"       {C.DIM}via: {cn_str}{extra}{C.RESET}  "
                  f"suggested: {C.ACCENT}{suggested_et}{C.RESET}")

        # Why sentence
        verb = EDGE_VERBS.get(suggested_et, suggested_et.lower().replace("_", " "))
        print(f"       {C.DIM}Why: {pred['common_neighbors']} shared neighbor(s) suggest "
              f"'{pred['source_title'][:15]}' {verb} '{pred['target_title'][:15]}'{C.RESET}")

    # ── Predictions by Network Pair ──
    _section_header("Prediction Distribution", C.SIGNAL)
    print(f"    Same-network:  {C.BOLD}{same_net_count}{C.RESET}")
    print(f"    Cross-network: {C.BOLD}{cross_net_count}{C.RESET}")

    # Context stats
    total_edges = len(g["edges"])
    avg_cn = sum(p["common_neighbors"] for p in predictions) / max(len(predictions), 1)
    pct_add = len(predictions) / max(total_edges, 1) * 100
    print(f"    {C.DIM}Avg common neighbors: {avg_cn:.1f}  "
          f"Would add {len(predictions)} edges ({pct_add:.1f}% of current {total_edges}){C.RESET}")


# ── Option 7: Graph Health (Structural Anomalies) ────────────────

def _render_structural_anomalies(algo):
    """Render structural anomalies with remediation and health score."""
    print(f"\n{divider('═', C.DANGER)}")
    print(f"  {C.BOLD}{C.DANGER}GRAPH HEALTH{C.RESET}  {C.DIM}structural anomalies with remediation{C.RESET}")
    print(divider('─', C.DANGER))

    anomalies = algo.structural_anomalies()
    g = algo.graph

    # ── Per-anomaly rendering with enrichment ──
    if not anomalies:
        print(f"  {C.CONFIRM}No structural anomalies detected.{C.RESET}")

    for anomaly in anomalies:
        sev_color = C.DANGER if anomaly["severity"] == "warning" else C.SIGNAL if anomaly["severity"] == "info" else C.DIM
        print(f"\n  {sev_color}[{anomaly['severity'].upper()}]{C.RESET} "
              f"{C.BOLD}{anomaly['anomaly_type']}{C.RESET}")
        print(f"    {anomaly['description']}")

        details = anomaly.get("details", {})
        node_ids = anomaly.get("node_ids", [])

        if anomaly["anomaly_type"] == "orphan_nodes":
            # Show network, decay, age for each orphan
            for nid in node_ids[:5]:
                node = g["nodes"].get(nid, {})
                icon = NODE_ICONS.get(node.get("type", ""), " ")
                nets = _network_tags(node.get("networks", []))
                decay = node.get("decay_score", 0.5)
                fl, fc = _freshness(decay)
                print(f"      {icon} {node.get('title', '?')[:35]}  {nets}  {fc}{fl}{C.RESET}")

        elif anomaly["anomaly_type"] == "isolated_high_importance":
            # Show predicted links as remediation
            for nid in node_ids[:3]:
                try:
                    preds = algo.get_entity_predicted_links(nid, top_k=3)
                    if preds:
                        print(f"      {C.DIM}Suggested links:{C.RESET}")
                        for p in preds:
                            other = p["target_title"] if p["source_id"] == nid else p["source_title"]
                            print(f"        {C.SIGNAL}→{C.RESET} {other}  {C.DIM}score={p['score']:.3f}{C.RESET}")
                except Exception:
                    pass

        elif anomaly["anomaly_type"] == "unusual_density":
            # Show edge type breakdown for dense nodes
            for nid in node_ids[:5]:
                node = g["nodes"].get(nid, {})
                et = _edge_type_counts(nid, g["edges"])
                et_str = _top_edge_types_str(et, 5)
                print(f"      {C.DIM}{node.get('title', '?')[:30]}: {et_str}{C.RESET}")
        else:
            if "titles" in details:
                for title in details["titles"][:5]:
                    print(f"      {C.DIM}- {title}{C.RESET}")

    # ── Confidence Distribution ──
    _section_header("Confidence Distribution", C.DANGER)
    high_conf = sum(1 for n in g["nodes"].values() if n.get("confidence", 0) >= 0.8)
    med_conf = sum(1 for n in g["nodes"].values() if 0.5 <= n.get("confidence", 0) < 0.8)
    low_conf = sum(1 for n in g["nodes"].values() if n.get("confidence", 0) < 0.5)
    total = len(g["nodes"]) or 1
    print(f"    {C.CONFIRM}High (≥0.8):{C.RESET}  {horizontal_bar(high_conf/total, 15, C.CONFIRM)}  {high_conf}")
    print(f"    {C.SIGNAL}Med (0.5-0.8):{C.RESET} {horizontal_bar(med_conf/total, 15, C.SIGNAL)}  {med_conf}")
    print(f"    {C.DANGER}Low (<0.5):{C.RESET}  {horizontal_bar(low_conf/total, 15, C.DANGER)}  {low_conf}")

    # ── Decay Distribution ──
    _section_header("Decay Distribution", C.DANGER)
    fresh = sum(1 for n in g["nodes"].values() if n.get("decay_score", 0) >= 0.7)
    aging = sum(1 for n in g["nodes"].values() if 0.4 <= n.get("decay_score", 0) < 0.7)
    stale = sum(1 for n in g["nodes"].values() if n.get("decay_score", 0) < 0.4)
    print(f"    {C.CONFIRM}Fresh (≥0.7):{C.RESET} {horizontal_bar(fresh/total, 15, C.CONFIRM)}  {fresh}")
    print(f"    {C.SIGNAL}Aging (0.4-0.7):{C.RESET} {horizontal_bar(aging/total, 15, C.SIGNAL)}  {aging}")
    print(f"    {C.DANGER}Stale (<0.4):{C.RESET} {horizontal_bar(stale/total, 15, C.DANGER)}  {stale}")

    # ── Active Patterns ──
    try:
        patterns = algo.repo.get_patterns(status="active", limit=5)
        if patterns:
            _section_header("Active Patterns", C.DANGER)
            for p in patterns:
                ptype = p.get("pattern_type", "?")
                desc = p.get("description", p.get("title", ""))[:50]
                print(f"    {C.INTEL}◆{C.RESET} {ptype}: {desc}")
    except Exception:
        pass

    # ── Overall Health Score ──
    orphan_ratio = sum(1 for a in anomalies if a["anomaly_type"] == "orphan_nodes") / max(total, 1)
    # Use actual orphan count
    orphan_count = 0
    for a in anomalies:
        if a["anomaly_type"] == "orphan_nodes":
            orphan_count = len(a.get("node_ids", []))
    orphan_ratio = orphan_count / max(total, 1)
    avg_conf = sum(n.get("confidence", 0.5) for n in g["nodes"].values()) / max(total, 1)
    stale_ratio = stale / max(total, 1)
    health = (1 - orphan_ratio) * avg_conf * (1 - stale_ratio)
    h_label, h_color = ("healthy", C.CONFIRM) if health >= 0.6 else (("fair", C.SIGNAL) if health >= 0.3 else ("needs attention", C.DANGER))

    _section_header("Overall Health Score", C.DANGER)
    print(f"    {h_color}{C.BOLD}{health:.0%}{C.RESET} ({h_label})")
    print(f"    {C.DIM}= (1-orphan_ratio:{orphan_ratio:.2f}) × avg_conf:{avg_conf:.2f} × (1-stale_ratio:{stale_ratio:.2f}){C.RESET}")

    # ── Remediation Priority ──
    remediations = []
    if orphan_count > 0:
        remediations.append(f"Link {orphan_count} orphan node(s) — biggest structural gap")
    if stale > total * 0.3:
        remediations.append(f"Refresh {stale} stale entities — decay eroding graph quality")
    iso_hi = [a for a in anomalies if a["anomaly_type"] == "isolated_high_importance"]
    if iso_hi:
        remediations.append(f"Connect {len(iso_hi)} high-confidence isolate(s) — wasted knowledge")
    if remediations:
        _section_header("Remediation Priority", C.DANGER)
        for i, r in enumerate(remediations, 1):
            print(f"    {C.SIGNAL}{i}.{C.RESET} {r}")


# ── Option 8: Activity Pulse (Temporal Anomalies) ────────────────

def _render_temporal_anomalies(algo):
    """Render temporal anomalies with timeline, heatmap, and velocity."""
    print(f"\n{divider('═', C.SIGNAL)}")
    print(f"  {C.BOLD}{C.SIGNAL}ACTIVITY PULSE{C.RESET}  {C.DIM}temporal analysis — last 30 days{C.RESET}")
    print(divider('─', C.SIGNAL))

    g = algo.graph
    now = datetime.now(timezone.utc)

    # Build daily activity over 30 days
    daily: dict[int, int] = defaultdict(int)  # day_offset -> count
    network_weekly: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))  # net -> week -> count

    for nid, data in g["nodes"].items():
        created = data.get("created_at")
        if not created:
            continue
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
        if not hasattr(created, "date"):
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        delta = (now - created).days
        if 0 <= delta < 30:
            daily[delta] += 1
            week = delta // 7
            for net in data.get("networks", []):
                network_weekly[net][week] += 1

    # ── Activity Timeline (sparkline) ──
    _section_header("Activity Timeline (30 days)", C.SIGNAL)
    if daily:
        max_daily = max(daily.values()) if daily else 1
        values = [daily.get(29 - d, 0) / max(max_daily, 1) for d in range(30)]
        total_30d = sum(daily.values())
        print(f"    {spark_line(values, 30)}  {C.DIM}{total_30d} total{C.RESET}")
        print(f"    {C.DIM}{'30d ago':<15}{'today':>15}{C.RESET}")
    else:
        print(f"    {C.DIM}No activity in the last 30 days.{C.RESET}")

    # ── 7-day comparison ──
    recent_7 = sum(daily.get(d, 0) for d in range(7))
    prior_7 = sum(daily.get(d, 0) for d in range(7, 14))
    if prior_7 > 0:
        change = ((recent_7 - prior_7) / prior_7) * 100
        change_color = C.CONFIRM if change > 0 else C.DANGER
        arrow = "▲" if change > 0 else "▼"
        print(f"\n    This week: {C.BOLD}{recent_7}{C.RESET}  "
              f"Prior week: {C.BOLD}{prior_7}{C.RESET}  "
              f"{change_color}{arrow} {abs(change):.0f}%{C.RESET}")
    elif recent_7 > 0:
        print(f"\n    This week: {C.BOLD}{recent_7}{C.RESET}  "
              f"{C.DIM}Prior week: 0 (new activity){C.RESET}")

    # ── Standard anomalies ──
    anomalies = algo.temporal_anomalies()
    if anomalies:
        _section_header("Detected Anomalies", C.SIGNAL)
        for anomaly in anomalies:
            sev_color = C.DANGER if anomaly["severity"] == "warning" else C.SIGNAL
            print(f"    {sev_color}[{anomaly['severity'].upper()}]{C.RESET} "
                  f"{C.BOLD}{anomaly['anomaly_type']}{C.RESET}")
            print(f"      {anomaly['description']}")

            # Burst detail: what was created
            if anomaly["anomaly_type"] == "activity_burst":
                burst_days = anomaly.get("details", {}).get("burst_days", [])
                for day_str, count in burst_days[:3]:
                    try:
                        nodes = algo.repo.get_nodes_by_date_range(day_str, day_str)
                        if nodes:
                            titles = [n.get("title", "?")[:25] for n in nodes[:4]]
                            extra = f" +{len(nodes)-4}" if len(nodes) > 4 else ""
                            # Check for shared source
                            captures = {n.get("source_capture_id") for n in nodes if n.get("source_capture_id")}
                            batch = f" {C.DIM}(single capture){C.RESET}" if len(captures) == 1 and captures != {None} else ""
                            print(f"        {day_str}: {', '.join(titles)}{extra}{batch}")
                    except Exception:
                        print(f"        {day_str}: {count} nodes")

            # Network silence detail
            elif anomaly["anomaly_type"] == "network_silence":
                net = anomaly.get("details", {}).get("network", "")
                if net:
                    # Find last entity in this network
                    latest = None
                    for nid, data in g["nodes"].items():
                        if net in data.get("networks", []):
                            c = data.get("created_at")
                            if c and (latest is None or str(c) > str(latest[1])):
                                latest = (data["title"], c)
                    if latest:
                        print(f"        Last: {latest[0][:30]} {C.DIM}({str(latest[1])[:10]}){C.RESET}")
                    print(f"        {C.SIGNAL}→{C.RESET} Consider adding new {net} content")

    # ── Network Activity Heatmap ──
    if network_weekly:
        _section_header("Network Activity Heatmap (4 weeks)", C.SIGNAL)
        all_vals = [c for wk in network_weekly.values() for c in wk.values()]
        max_val = max(all_vals) if all_vals else 1
        print(f"    {C.DIM}{'Network':<20} W4    W3    W2    W1{C.RESET}")
        for net in sorted(network_weekly.keys()):
            weeks = network_weekly[net]
            badge = NETWORK_ICONS.get(net, net[:3])
            cells = []
            for w in [3, 2, 1, 0]:
                v = weeks.get(w, 0)
                if v == 0:
                    cells.append(f"{C.GHOST}  ·  {C.RESET}")
                else:
                    intensity = v / max(max_val, 1)
                    if intensity > 0.6:
                        cells.append(f"{C.CONFIRM}{v:^5}{C.RESET}")
                    elif intensity > 0.3:
                        cells.append(f"{C.SIGNAL}{v:^5}{C.RESET}")
                    else:
                        cells.append(f"{C.DIM}{v:^5}{C.RESET}")
            print(f"    {badge} {net:<17} {''.join(cells)}")

    # ── Commitment Velocity ──
    try:
        created_comms = algo.repo.count_nodes_by_status("COMMITMENT", "active")
        completed_comms = algo.repo.count_nodes_by_status("COMMITMENT", "completed")
        if created_comms or completed_comms:
            _section_header("Commitment Velocity", C.SIGNAL)
            print(f"    Created:   {C.BOLD}{created_comms}{C.RESET}")
            print(f"    Completed: {C.BOLD}{completed_comms}{C.RESET}")
            if created_comms > 0:
                ratio = completed_comms / created_comms
                r_color = C.CONFIRM if ratio >= 0.7 else (C.SIGNAL if ratio >= 0.4 else C.DANGER)
                print(f"    Throughput: {r_color}{ratio:.0%}{C.RESET}")
    except Exception:
        pass


# ── Option 9: Intelligence Briefing (Full Summary) ───────────────

def _render_full_summary(algo):
    """Render comprehensive intelligence briefing with recommendations."""
    print(f"\n{divider('═', C.INTEL)}")
    print(f"  {C.BOLD}{C.INTEL}INTELLIGENCE BRIEFING{C.RESET}")
    print(divider('─', C.INTEL))

    g = algo.graph
    total_nodes = len(g["nodes"])
    total_edges = len(g["edges"])

    if total_nodes == 0:
        print(f"  {C.DIM}Empty graph — no data to analyze.{C.RESET}")
        return

    # Compute everything
    pr = algo.pagerank()
    communities = algo.label_propagation_communities()
    structural = algo.structural_anomalies()
    temporal = algo.temporal_anomalies()
    predictions = algo.predict_links(top_k=10)
    bc = algo.betweenness_centrality()

    # Averages
    avg_conf = sum(n.get("confidence", 0.5) for n in g["nodes"].values()) / max(total_nodes, 1)
    avg_decay = sum(n.get("decay_score", 0.5) for n in g["nodes"].values()) / max(total_nodes, 1)
    fresh_label, fresh_color = _freshness(avg_decay)

    stale_count = sum(1 for n in g["nodes"].values() if n.get("decay_score", 0) < 0.4)
    orphan_count = 0
    for a in structural:
        if a["anomaly_type"] == "orphan_nodes":
            orphan_count = len(a.get("node_ids", []))
    health = (1 - orphan_count / max(total_nodes, 1)) * avg_conf * (1 - stale_count / max(total_nodes, 1))
    h_label, h_color = ("healthy", C.CONFIRM) if health >= 0.6 else (("fair", C.SIGNAL) if health >= 0.3 else ("needs attention", C.DANGER))

    # ── Graph Vitals ──
    _section_header("Graph Vitals", C.INTEL)
    multi_communities = [c for c in communities if c["size"] > 1]
    print(f"    Nodes: {C.BOLD}{total_nodes}{C.RESET}  "
          f"Edges: {C.BOLD}{total_edges}{C.RESET}  "
          f"Communities: {C.BOLD}{len(multi_communities)}{C.RESET}")
    print(f"    Avg Confidence: {C.BOLD}{avg_conf:.2f}{C.RESET}  "
          f"Avg Freshness: {fresh_color}{C.BOLD}{avg_decay:.2f}{C.RESET} ({fresh_label})  "
          f"Health: {h_color}{C.BOLD}{health:.0%}{C.RESET} ({h_label})")

    # ── Network Balance ──
    net_counts: dict[str, int] = defaultdict(int)
    for n in g["nodes"].values():
        for net in n.get("networks", []):
            net_counts[net] += 1

    if net_counts:
        _section_header("Network Balance", C.INTEL)
        for net in sorted(net_counts.keys()):
            cnt = net_counts[net]
            badge = NETWORK_ICONS.get(net, net[:3])
            pct = cnt / max(total_nodes, 1)
            bar = horizontal_bar(pct, 12, C.INTEL)

            # Network health from repo
            momentum = ""
            try:
                nh = algo.repo.get_latest_network_health(net)
                if nh:
                    score = nh.get("health_score", nh.get("overall_score", 0))
                    s_color = C.CONFIRM if score >= 70 else (C.SIGNAL if score >= 40 else C.DANGER)
                    momentum = f" {s_color}health={score:.0f}{C.RESET}"
            except Exception:
                pass

            print(f"    {badge} {net:<20} {bar}  {C.DIM}{cnt}{C.RESET}{momentum}")

    # ── Key Influencers ──
    if pr:
        _section_header("Key Influencers", C.INTEL)
        # Build bridge set
        top5_ids = [e["node_id"] for e in pr[:5]]
        bc_top = {e["node_id"] for e in (bc[:10] if bc else []) if e.get("betweenness", 0) > 0}

        for entry in pr[:5]:
            nid = entry["node_id"]
            icon = NODE_ICONS.get(entry["type"], " ")
            node = g["nodes"].get(nid, {})
            nets = _network_tags(node.get("networks", []))
            role = "bridge" if nid in bc_top else "hub"
            role_color = C.WARM if role == "bridge" else C.CYAN
            print(f"    {entry['rank']:2}. {icon} {C.BOLD}{entry['title'][:35]}{C.RESET}  "
                  f"{nets}  {role_color}{role}{C.RESET}")

    # ── Attention Required ──
    attention_items = []

    # Overdue commitments / pending outcomes
    try:
        pending = algo.repo.get_pending_outcomes()
        if pending:
            attention_items.append(f"{len(pending)} pending outcome(s) awaiting resolution")
    except Exception:
        pass

    # Activity drops from temporal
    for a in temporal:
        if a["severity"] == "warning":
            attention_items.append(a["description"][:60])

    # Orphans
    if orphan_count > 3:
        attention_items.append(f"{orphan_count} orphan nodes with no connections")

    if attention_items:
        _section_header("Attention Required", C.DANGER)
        for item in attention_items[:5]:
            print(f"    {C.DANGER}⚠{C.RESET} {item}")

    # ── Strongest Clusters ──
    if multi_communities:
        _section_header("Strongest Clusters", C.MAGENTA)
        for comm in multi_communities[:3]:
            member_ids = {m["node_id"] for m in comm["members"]}
            internal = sum(1 for s, t, _ in g["edges"] if s in member_ids and t in member_ids)
            size = comm["size"]
            possible = size * (size - 1) / 2 if size > 1 else 1
            cohesion = internal / max(possible, 1)
            top_members = ", ".join(m["title"][:18] for m in comm["members"][:3])
            print(f"    Cluster {comm['community_id']}: {C.BOLD}{size}{C.RESET} members  "
                  f"cohesion={cohesion:.2f}  {C.DIM}{top_members}{C.RESET}")

    # ── Predicted Connections ──
    if predictions:
        _section_header("Predicted Connections", C.SIGNAL)
        for p in predictions[:3]:
            src_nets = set(g["nodes"].get(p["source_id"], {}).get("networks", []))
            tgt_nets = set(g["nodes"].get(p["target_id"], {}).get("networks", []))
            cross = " ⚡" if (src_nets and tgt_nets and not src_nets & tgt_nets) else ""
            print(f"    {p['source_title'][:22]} {C.SIGNAL}···{C.RESET} {p['target_title'][:22]}  "
                  f"{C.DIM}cn={p['common_neighbors']}{C.RESET}{cross}")

    # ── Active Patterns ──
    try:
        patterns = algo.repo.get_patterns(status="active", limit=5)
        if patterns:
            _section_header("Active Patterns", C.INTEL)
            for p in patterns:
                ptype = p.get("pattern_type", "?")
                desc = p.get("description", p.get("title", ""))[:50]
                print(f"    {C.INTEL}◆{C.RESET} {ptype}: {desc}")
    except Exception:
        pass

    # ── Weekly Focus Suggestions ──
    _section_header("Weekly Focus", C.INTEL)
    suggestions = []

    if orphan_count > 0:
        suggestions.append(f"Link {orphan_count} isolated entit{'y' if orphan_count==1 else 'ies'} to strengthen graph connectivity")

    try:
        pending = algo.repo.get_pending_outcomes()
        if pending:
            suggestions.append(f"Record outcomes for {len(pending)} pending decision(s)")
    except Exception:
        pass

    stale_top = [e for e in pr[:20] if g["nodes"].get(e["node_id"], {}).get("decay_score", 1) < 0.4]
    if stale_top:
        suggestions.append(f"Refresh {len(stale_top)} stale influential entit{'y' if len(stale_top)==1 else 'ies'}")

    silent_nets = [a for a in temporal if a["anomaly_type"] == "network_silence"]
    if silent_nets:
        nets = [a.get("details", {}).get("network", "?") for a in silent_nets]
        suggestions.append(f"Add content to silent network(s): {', '.join(nets[:3])}")

    if predictions:
        suggestions.append(f"Review {len(predictions)} predicted connection(s) for manual linking")

    if not suggestions:
        suggestions.append("Graph is in good shape — continue regular knowledge capture")

    for i, s in enumerate(suggestions[:5], 1):
        print(f"    {C.SIGNAL}{i}.{C.RESET} {s}")
