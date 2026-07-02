"""Graph analytics for strategy network — uses networkx."""

from __future__ import annotations

from cli.strategy.data import GRAPH_EDGES, GRAPH_NODES

try:
    import networkx as nx

    _HAS_NX = True
except ImportError:
    _HAS_NX = False


def _require_nx() -> None:
    if not _HAS_NX:
        raise ImportError("networkx is required for graph analytics: pip install networkx>=3.0")


_graph_cache: object | None = None


def build_graph():
    """Build a networkx Graph from strategy data."""
    _require_nx()
    G = nx.Graph()
    for node in GRAPH_NODES:
        G.add_node(node["id"], label=node["label"], group=node["group"])
    for edge in GRAPH_EDGES:
        G.add_edge(edge["from"], edge["to"], label=edge.get("label", ""))
    return G


def get_graph():
    """Return cached graph, building if necessary."""
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = build_graph()
    return _graph_cache


def degree_centrality() -> dict[str, float]:
    """Return degree centrality for all nodes."""
    _require_nx()
    return nx.degree_centrality(get_graph())


def betweenness_centrality() -> dict[str, float]:
    """Return betweenness centrality for all nodes."""
    _require_nx()
    return nx.betweenness_centrality(get_graph(), normalized=True)


def pagerank() -> dict[str, float]:
    """Return PageRank for all nodes."""
    _require_nx()
    return nx.pagerank(get_graph())


def bridges() -> list[tuple[str, str]]:
    """Return bridge edges (whose removal disconnects the graph)."""
    _require_nx()
    return list(nx.bridges(get_graph()))


def communities() -> list[set[str]]:
    """Return communities detected by greedy modularity."""
    _require_nx()
    return list(nx.community.greedy_modularity_communities(get_graph()))


def shortest_path(source: str, target: str) -> list[str] | None:
    """Return shortest path between two nodes, or None if unreachable."""
    _require_nx()
    try:
        return nx.shortest_path(get_graph(), source, target)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def hub_score(node_id: str) -> float:
    """Composite hub score: weighted combination of degree, betweenness, pagerank."""
    _require_nx()
    G = get_graph()
    if node_id not in G:
        return 0.0
    dc = degree_centrality()
    bc = betweenness_centrality()
    pr = pagerank()
    return dc.get(node_id, 0) * 0.4 + bc.get(node_id, 0) * 0.3 + pr.get(node_id, 0) * 0.3


def top_nodes(metric: str = "hub", n: int = 10) -> list[tuple[str, float]]:
    """Return top-n nodes by a given metric."""
    _require_nx()
    if metric == "degree":
        scores = degree_centrality()
    elif metric == "betweenness":
        scores = betweenness_centrality()
    elif metric == "pagerank":
        scores = pagerank()
    else:  # hub
        G = get_graph()
        scores = {nid: hub_score(nid) for nid in G.nodes}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:n]


def node_connections(node_id: str) -> list[dict]:
    """Return edges connected to a node with labels."""
    _require_nx()
    G = get_graph()
    if node_id not in G:
        return []
    result = []
    for neighbor in G.neighbors(node_id):
        edge_data = G.edges[node_id, neighbor]
        result.append({
            "neighbor": neighbor,
            "label": edge_data.get("label", ""),
            "neighbor_group": G.nodes[neighbor].get("group", ""),
        })
    return result
