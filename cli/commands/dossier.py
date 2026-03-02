"""Dossier command — deep search for everything about an entity."""

from __future__ import annotations

from cli.rendering import (
    C, DOSSIER_CONFIG, NETWORK_ICONS, NODE_ICONS,
    divider, horizontal_bar, prompt, subcommand_header,
)
from cli.commands.browse import render_node_detail, render_ascii_graph


def cmd_dossier(app):
    subcommand_header(
        title="DOSSIER",
        symbol="◇",
        color=C.ACCENT,
        taglines=["Hybrid search · Vector + full-text", "Multi-signal scoring · Subgraph visualization"],
        border="simple",
    )

    query = prompt(f"  {C.ACCENT}Entity name or keyword{C.RESET}\n  ❯ ")
    if not query or query == "q":
        return

    # 1. Hybrid search
    title_matches = app.repo.search_by_title(query, limit=DOSSIER_CONFIG["title_search_limit"])
    semantic_matches = _semantic_fallback(app, query)

    seen_ids: dict[str, object] = {}
    for node in title_matches:
        seen_ids[str(node.id)] = node
    for node in semantic_matches:
        nid = str(node.id)
        if nid not in seen_ids:
            seen_ids[nid] = node

    all_matches = list(seen_ids.values())
    if not all_matches:
        print(f"\n  {C.DIM}No entities matching '{query}'.{C.RESET}")
        return

    # Multi-signal scoring
    lower_q = query.lower()
    scored: list[tuple[float, object]] = []
    for node in all_matches:
        lt = node.title.lower()
        if lt == lower_q:
            title_score = 0.50
        elif lt.startswith(lower_q):
            title_score = 0.40
        elif lower_q.startswith(lt):
            title_score = 0.35
        elif lower_q in lt:
            title_score = 0.25
        else:
            title_score = 0.0
        conf_score = node.confidence * 0.25
        decay_score = (node.decay_score or 0.5) * 0.15
        access_score = min(node.access_count / 100, 1.0) * 0.10
        score = title_score + conf_score + decay_score + access_score
        scored.append((score, node))
    scored.sort(key=lambda x: x[0], reverse=True)

    if len(scored) > 1:
        print(f"\n  {C.BOLD}{len(scored)} matches found:{C.RESET}\n")
        for i, (sc, n) in enumerate(scored, 1):
            icon = NODE_ICONS.get(n.node_type.value, " ")
            nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in n.networks)
            print(f"  {C.DIM}{i:2}.{C.RESET} {icon} {C.BOLD}{n.title}{C.RESET}  {nets}  "
                  f"conf={n.confidence:.0%}  {C.DIM}{str(n.id)[:8]}{C.RESET}")
        choice = prompt(f"  Select [1-{len(scored)}, default 1]: ")
        try:
            idx = int(choice) - 1 if choice else 0
            entity = scored[idx][1]
        except (ValueError, IndexError):
            entity = scored[0][1]
    else:
        entity = scored[0][1]

    print()
    render_node_detail(entity)

    # 2. Neighborhood
    subgraph = app.repo.get_neighborhood(entity.id, hops=DOSSIER_CONFIG["neighborhood_hops"])

    entity_str = str(entity.id)
    min_strength = DOSSIER_CONFIG["connection_min_strength"]
    connections = _compute_connections(entity_str, subgraph)
    top_connections = _render_connections(connections, entity_str, min_strength)

    # 3. Vector-similar entities
    neighborhood_ids = {str(n.id) for n in subgraph.nodes}
    related = _find_related(app, entity, neighborhood_ids)
    if related:
        print(f"\n{divider('─', C.MAGENTA)}")
        print(f"  {C.BOLD}{C.MAGENTA}RELATED ENTITIES ({len(related)}){C.RESET}  {C.DIM}semantically similar, not directly connected{C.RESET}")
        print(divider())
        for sim_score, rel_node in related:
            icon = NODE_ICONS.get(rel_node.node_type.value, " ")
            nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in rel_node.networks)
            pct = f"{sim_score * 100:.0f}%"
            print(f"  {C.MAGENTA}~{C.RESET} {icon} {C.BOLD}{rel_node.title[:35]:<35}{C.RESET} "
                  f"{nets}  {C.DIM}similarity {pct}{C.RESET}")

    # 4. Facts
    facts = _get_facts(app, entity_str)
    if facts:
        print(f"\n{divider('─', C.GREEN)}")
        print(f"  {C.BOLD}{C.GREEN}VERIFIED FACTS ({len(facts)}){C.RESET}")
        print(divider())
        for fact in facts[:15]:
            conf = fact.get("confidence", 0)
            lifecycle = fact.get("lifecycle", "")
            lc_color = C.GREEN if lifecycle == "static" else C.YELLOW
            statement = fact.get("statement", "")
            print(f"  {C.GREEN}✓{C.RESET} {statement[:70]}")
            print(f"    {horizontal_bar(conf, 10, C.GREEN)}  "
                  f"{lc_color}{lifecycle}{C.RESET}")
        if len(facts) > 15:
            print(f"    {C.DIM}... and {len(facts) - 15} more{C.RESET}")
    else:
        print(f"\n  {C.DIM}No verified facts for this entity.{C.RESET}")

    # 5. Graph summary
    print(f"\n{divider('─', C.BLUE)}")
    n_nodes = len(subgraph.nodes)
    n_edges = len(subgraph.edges)
    print(f"  {C.BOLD}{C.BLUE}SUBGRAPH{C.RESET}  "
          f"{C.BOLD}{n_nodes}{C.RESET} nodes  {C.DIM}|{C.RESET}  "
          f"{C.BOLD}{n_edges}{C.RESET} edges  {C.DIM}(2-hop neighborhood){C.RESET}")

    drill_hint = f"[1-{len(top_connections)}] Drill into connection  " if connections else ""
    print(f"\n  {C.DIM}{drill_hint}[v] Visualize graph map  [b] Back{C.RESET}")
    action = prompt("dossier> ").strip()
    if action == "v":
        render_ascii_graph(subgraph, center_id=entity.id)
    elif action.isdigit() and connections:
        idx = int(action) - 1
        if 0 <= idx < len(top_connections):
            _, _, drill_node = top_connections[idx]
            print(f"\n  {C.DIM}Drilling into {drill_node.title}...{C.RESET}")
            render_node_detail(drill_node)

            drill_sub = app.repo.get_neighborhood(drill_node.id, hops=DOSSIER_CONFIG["neighborhood_hops"])
            drill_str = str(drill_node.id)
            drill_conns = _compute_connections(drill_str, drill_sub, exclude_id=entity_str)
            _render_connections(drill_conns, drill_str, min_strength)
        else:
            print(f"  {C.DIM}Invalid selection.{C.RESET}")


def _compute_connections(node_id_str, subgraph, exclude_id=None):
    direct_edges = [e for e in subgraph.edges
                    if str(e.source_id) == node_id_str or str(e.target_id) == node_id_str]
    nodes_by_id = {str(n.id): n for n in subgraph.nodes}

    connections = []
    for edge in direct_edges:
        neighbor_id = str(edge.target_id) if str(edge.source_id) == node_id_str else str(edge.source_id)
        if exclude_id and neighbor_id == exclude_id:
            continue
        neighbor_node = nodes_by_id.get(neighbor_id)
        if neighbor_node:
            strength = (
                edge.weight * 0.4
                + edge.confidence * 0.3
                + neighbor_node.confidence * 0.2
                + (neighbor_node.decay_score or 0.5) * 0.1
            )
            connections.append((strength, edge, neighbor_node))
    connections.sort(key=lambda x: x[0], reverse=True)
    return connections


def _render_connections(connections, node_id_str, min_strength):
    top = [(s, e, n) for s, e, n in connections if s >= min_strength]
    if not connections:
        print(f"\n  {C.DIM}No direct connections.{C.RESET}")
        return []
    hidden = len(connections) - len(top)
    print(f"\n{divider('─', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}CONNECTIONS ({len(top)}){C.RESET}  {C.DIM}sorted by strength, ≥{min_strength:.0%}{C.RESET}")
    print(divider())
    for i, (strength, edge, neighbor) in enumerate(top, 1):
        direction = "→" if str(edge.source_id) == node_id_str else "←"
        icon = NODE_ICONS.get(neighbor.node_type.value, " ")
        etype = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
        bar = horizontal_bar(min(strength, 1.0), 10, C.CYAN)
        print(f"  {C.DIM}{i}.{C.RESET} {C.CYAN}{direction}{C.RESET} {icon} {C.BOLD}{neighbor.title[:35]:<35}{C.RESET} "
              f"{C.DIM}[{etype}]{C.RESET}  {bar}")
    if hidden:
        print(f"    {C.DIM}... {hidden} weaker connections below {min_strength:.0%}{C.RESET}")
    return top


def _semantic_fallback(app, query: str) -> list:
    try:
        engine = app._get_embedding_engine()
        store = app._get_vector_store()
        if not engine or not store:
            return []
        embedding = engine.embed_text(query)
        results = store.dense_search(query_vector=embedding["dense"], top_k=DOSSIER_CONFIG["title_search_limit"])
        min_score = DOSSIER_CONFIG["semantic_min_score"]
        qualified_ids = [sr.node_id for sr in results if sr.score >= min_score]
        if not qualified_ids:
            return []
        nodes_map = app.repo.get_nodes_batch(qualified_ids)
        return list(nodes_map.values())
    except Exception as e:
        print(f"  {C.DIM}(semantic search unavailable: {e}){C.RESET}")
        return []


def _find_related(app, entity, exclude_ids: set[str]) -> list[tuple[float, object]]:
    try:
        engine = app._get_embedding_engine()
        store = app._get_vector_store()
        if not engine or not store:
            return []
        text = f"{entity.title} {entity.content or ''}"
        embedding = engine.embed_text(text)
        results = store.dense_search(query_vector=embedding["dense"], top_k=20)
        entity_str = str(entity.id)
        min_score = DOSSIER_CONFIG["related_min_score"]
        candidate_ids = [
            sr.node_id for sr in results
            if sr.node_id not in exclude_ids
            and sr.node_id != entity_str
            and sr.score >= min_score
        ]
        if not candidate_ids:
            return []
        nodes_map = app.repo.get_nodes_batch(candidate_ids)
        score_by_id = {sr.node_id: sr.score for sr in results}
        related = [
            (score_by_id[nid], nodes_map[nid])
            for nid in candidate_ids
            if nid in nodes_map
        ]
        related.sort(key=lambda x: x[0], reverse=True)
        return related
    except Exception as e:
        print(f"  {C.DIM}(vector search unavailable: {e}){C.RESET}")
        return []


def _get_facts(app, node_id: str) -> list[dict]:
    try:
        from memora.core.truth_layer import TruthLayer
        truth = TruthLayer(conn=app.repo.get_truth_layer_conn())
        return truth.query_facts(node_id=node_id, status="active", limit=DOSSIER_CONFIG["facts_limit"])
    except Exception as e:
        print(f"  {C.DIM}(facts query unavailable: {e}){C.RESET}")
        return []
