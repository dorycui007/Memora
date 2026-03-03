"""Browse command — explore the knowledge graph."""

from __future__ import annotations

import textwrap
from collections import defaultdict, deque
from uuid import UUID

from cli.rendering import (
    C, NETWORK_ICONS, NODE_ICONS,
    divider, horizontal_bar, menu_option, prompt, render_profile_card,
    spinner, term_width, subcommand_header,
)

from memora.graph.models import NetworkType, NodeType, enum_val
from memora.graph.repository import YOU_NODE_ID

# Keep BRAIN_ART reference for backward compat
BRAIN_ART = ""


def cmd_browse(app):
    while True:
        subcommand_header(
            title="BROWSE",
            symbol="◇",
            color=C.ACCENT,
            taglines=["Graph explorer · Navigate nodes and relationships"],
            border="simple",
        )
        print(menu_option("1", "List nodes",    "All, by type, or by network"))
        print(menu_option("2", "Search",        "Search nodes by title"))
        print(menu_option("3", "Node detail",   "View a node and its connections"))
        print(menu_option("4", "Graph map",     "ASCII graph — node, galaxy, or full"))
        print()

        choice = prompt("browse> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _browse_list_nodes(app)
        elif choice == "2":
            _browse_search(app)
        elif choice == "3":
            _browse_node_detail(app)
        elif choice == "4":
            _browse_graph_map_menu(app)


def _browse_list_nodes(app):
    """Unified node listing with optional filter."""
    from memora.graph.models import NodeFilter

    print(f"\n  {C.BOLD}Filter:{C.RESET}")
    print(f"    {C.BOLD}[a]{C.RESET} All nodes")
    print(f"    {C.BOLD}[t]{C.RESET} By type")
    print(f"    {C.BOLD}[n]{C.RESET} By network")
    filt = prompt("filter> ").lower()

    node_filter = NodeFilter()

    if filt == "t":
        types = list(NodeType)
        print(f"\n  {C.BOLD}Node Types:{C.RESET}")
        for i, nt in enumerate(types, 1):
            icon = NODE_ICONS.get(nt.value, " ")
            print(f"    {C.DIM}{i:2}.{C.RESET} {icon} {nt.value}")
        choice = prompt("Type number: ")
        try:
            idx = int(choice) - 1
            node_filter = NodeFilter(node_types=[types[idx]])
        except (ValueError, IndexError):
            print(f"  {C.RED}Invalid selection.{C.RESET}")
            return
    elif filt == "n":
        nets = list(NetworkType)
        print(f"\n  {C.BOLD}Networks:{C.RESET}")
        for i, nt in enumerate(nets, 1):
            icon = NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]")
            print(f"    {C.DIM}{i}.{C.RESET} {icon} {nt.value}")
        choice = prompt("Network number: ")
        try:
            idx = int(choice) - 1
            node_filter = NodeFilter(networks=[nets[idx]])
        except (ValueError, IndexError):
            print(f"  {C.RED}Invalid selection.{C.RESET}")
            return

    try:
        nodes = app.repo.query_nodes(node_filter)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not nodes:
        print(f"\n  {C.DIM}No nodes found.{C.RESET}")
        return

    print(f"\n  {C.BOLD}{len(nodes)} node(s) found{C.RESET}\n")
    render_node_table(nodes[:30])
    if len(nodes) > 30:
        print(f"\n  {C.DIM}... and {len(nodes) - 30} more{C.RESET}")


def _browse_search(app):
    query = prompt("Search title: ")
    if not query:
        return
    try:
        rows = app.repo.search_nodes_ilike(query)
    except Exception as e:
        print(f"  {C.RED}Search error: {e}{C.RESET}")
        return

    if not rows:
        print(f"\n  {C.DIM}No nodes matching '{query}'.{C.RESET}")
        return

    print(f"\n  {C.BOLD}{len(rows)} result(s){C.RESET}\n")
    for row in rows:
        nid, ntype, title, content, networks, conf, created = (
            row["id"], row["node_type"], row["title"], row["content"],
            row["networks"], row["confidence"], row["created_at"],
        )
        icon = NODE_ICONS.get(ntype, " ")
        nets = " ".join(NETWORK_ICONS.get(n, f"[{n}]") for n in (networks or []))
        short_id = str(nid)[:8]
        print(f"  {C.DIM}{short_id}{C.RESET}  {icon} {C.BOLD}{title}{C.RESET}  {nets}  conf={conf:.0%}")
        if content:
            print(f"           {C.DIM}{content[:60]}{C.RESET}")


def _browse_node_detail(app):
    nid = prompt("Node ID (first 8 chars ok): ")
    if not nid:
        return

    try:
        matching_ids = app.repo.find_node_ids_by_prefix(nid)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not matching_ids:
        print(f"  {C.DIM}Node not found.{C.RESET}")
        return

    try:
        node = app.repo.get_node(UUID(str(matching_ids[0])))
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not node:
        print(f"  {C.DIM}Node not found.{C.RESET}")
        return

    render_node_detail(node)

    try:
        edges = app.repo.get_edges(node.id)
        if edges:
            print(f"\n  {C.BOLD}Connections ({len(edges)}):{C.RESET}")
            for edge in edges[:15]:
                direction = "-->" if str(edge.source_id) == str(node.id) else "<--"
                other_id = edge.target_id if direction == "-->" else edge.source_id
                short = str(other_id)[:8]
                other_title = ""
                try:
                    other_node = app.repo.get_node(UUID(str(other_id)))
                    if other_node:
                        other_icon = NODE_ICONS.get(other_node.node_type.value, " ")
                        other_title = f" {other_icon} {C.BOLD}{other_node.title[:25]}{C.RESET}"
                except Exception:
                    pass
                etype = enum_val(edge.edge_type)
                print(f"    {C.CYAN}{direction}{C.RESET} {C.DIM}{short}{C.RESET}{other_title}  "
                      f"{C.DIM}[{etype}]{C.RESET} conf={edge.confidence:.0%}")
            if len(edges) > 15:
                print(f"    {C.DIM}... and {len(edges) - 15} more{C.RESET}")
            print(f"\n  {C.DIM}Tip: Use option [4] Graph map to visualize this node's neighborhood{C.RESET}")
        else:
            print(f"\n  {C.DIM}No connections yet.{C.RESET}")
    except Exception:
        pass


def _browse_graph_map_menu(app):
    """Unified graph map with scope selection."""
    print(f"\n  {C.BOLD}Graph scope:{C.RESET}")
    print(f"    {C.BOLD}[1]{C.RESET} Around a node (enter ID)")
    print(f"    {C.BOLD}[2]{C.RESET} Your galaxy (You +/- depth)")
    print(f"    {C.BOLD}[3]{C.RESET} Full graph")
    scope = prompt("scope> ")

    if scope == "1":
        _graph_map_node(app)
    elif scope == "2":
        _graph_map_galaxy(app)
    elif scope == "3":
        _graph_map_full(app)


def _graph_map_node(app):
    """Graph map centered on a specific node."""
    nid = prompt("Center node ID (first 8 chars ok): ")
    if not nid:
        return

    try:
        matching_ids = app.repo.find_node_ids_by_prefix(nid)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not matching_ids:
        print(f"  {C.DIM}Node not found.{C.RESET}")
        return

    full_id = UUID(str(matching_ids[0]))

    hops_str = prompt(f"  Hops (depth) [{C.GREEN}1{C.RESET}-3, default 1]: ")
    hops = 1
    if hops_str.isdigit() and 1 <= int(hops_str) <= 3:
        hops = int(hops_str)

    spinner("Traversing graph neighborhood", 0.5)

    try:
        subgraph = app.repo.get_neighborhood(full_id, hops=hops)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not subgraph.nodes:
        print(f"  {C.DIM}No neighborhood found.{C.RESET}")
        return

    render_ascii_graph(subgraph, center_id=full_id)


def _graph_map_galaxy(app):
    """Galaxy view — centered on the You node with configurable depth."""
    you_id = UUID(YOU_NODE_ID)

    hops_str = prompt(f"  Depth [{C.GREEN}1{C.RESET}-3, default 2]: ")
    hops = 2
    if hops_str.isdigit() and 1 <= int(hops_str) <= 3:
        hops = int(hops_str)

    spinner("Mapping your galaxy", 0.5)

    try:
        subgraph = app.repo.get_neighborhood(you_id, hops=hops)
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not subgraph.nodes:
        print(f"\n  {C.DIM}Your galaxy is empty. Start by capturing some thoughts!{C.RESET}")
        return

    render_ascii_graph(subgraph, center_id=you_id)


def _graph_map_full(app):
    """Visualize the entire graph as an ASCII map."""
    from memora.graph.models import NodeFilter, Subgraph
    try:
        nodes = app.repo.query_nodes(NodeFilter())
    except Exception as e:
        print(f"  {C.RED}Error: {e}{C.RESET}")
        return

    if not nodes:
        print(f"\n  {C.DIM}Graph is empty.{C.RESET}")
        return

    if len(nodes) > 60:
        print(f"\n  {C.YELLOW}Graph has {len(nodes)} nodes. Showing first 60.{C.RESET}")
        nodes = nodes[:60]

    node_ids = {str(n.id) for n in nodes}
    all_edges = []
    seen_edge_ids = set()
    for node in nodes:
        try:
            edges = app.repo.get_edges(node.id)
            for e in edges:
                eid = str(e.id) if hasattr(e, 'id') else f"{e.source_id}-{e.target_id}"
                if eid not in seen_edge_ids:
                    if str(e.source_id) in node_ids and str(e.target_id) in node_ids:
                        all_edges.append(e)
                        seen_edge_ids.add(eid)
        except Exception:
            pass

    subgraph = Subgraph(nodes=nodes, edges=all_edges)
    you_center = UUID(YOU_NODE_ID) if YOU_NODE_ID in node_ids else None
    render_ascii_graph(subgraph, center_id=you_center)


# ── Shared rendering helpers ──────────────────────────────────────


def render_node_table(nodes):
    """Render a compact table of nodes."""
    for node in nodes:
        icon = NODE_ICONS.get(node.node_type.value, " ")
        nets = " ".join(NETWORK_ICONS.get(n.value, f"[{n.value[0]}]") for n in node.networks)
        short_id = str(node.id)[:8]
        title = node.title[:40] + ("..." if len(node.title) > 40 else "")
        print(f"  {C.DIM}{short_id}{C.RESET}  {icon} {C.BOLD}{title:<44}{C.RESET} {nets}")


def render_node_detail(node):
    # PERSON nodes get the full profile card
    if node.node_type.value == "PERSON":
        _render_person_node_detail(node)
        return

    # Non-person nodes keep existing generic rendering
    icon = NODE_ICONS.get(node.node_type.value, " ")
    nets = " ".join(NETWORK_ICONS.get(n.value, f"[{n.value[0]}]") for n in node.networks)

    art = f"""
{C.BOLD}    .───────────────────────────────────────.
    |  {icon} {node.title[:35]:<35}  |
    '───────────────────────────────────────'{C.RESET}"""
    print(art)

    print(f"\n  {C.DIM}ID:{C.RESET}         {node.id}")
    print(f"  {C.DIM}Type:{C.RESET}       {node.node_type.value}")
    print(f"  {C.DIM}Networks:{C.RESET}   {nets}")
    print(f"  {C.DIM}Confidence:{C.RESET} {horizontal_bar(node.confidence, 20)}")
    print(f"  {C.DIM}Created:{C.RESET}    {node.created_at}")

    if node.content:
        print(f"\n  {C.BOLD}Content:{C.RESET}")
        for line in textwrap.wrap(node.content, min(term_width() - 6, 68)):
            print(f"    {line}")

    if node.properties:
        print(f"\n  {C.BOLD}Properties:{C.RESET}")
        for k, v in node.properties.items():
            print(f"    {C.DIM}{k}:{C.RESET} {v}")

    if node.tags:
        print(f"\n  {C.DIM}Tags:{C.RESET} {', '.join(node.tags)}")


def _render_person_node_detail(node):
    """Render a PERSON node using the full profile card."""
    props = node.properties or {}

    fields: list[tuple[str, str]] = []
    if props.get("role"):
        fields.append(("Role", props["role"]))
    if props.get("organization"):
        fields.append(("Org", props["organization"]))
    if props.get("location"):
        fields.append(("Location", props["location"]))
    if props.get("relationship_to_user"):
        fields.append(("Relationship", props["relationship_to_user"]))

    # Network badges
    if node.networks:
        nets = " ".join(
            NETWORK_ICONS.get(n.value, f"[{n.value[0]}]")
            for n in node.networks
        )
        fields.append(("Networks", nets))

    # Extra properties
    shown = {"name", "role", "location", "organization",
             "relationship_to_user", "bio"}
    for k, v in props.items():
        if k not in shown and v:
            fields.append((k.replace("_", " ").title(), str(v)))

    # ID as a field
    fields.append(("ID", str(node.id)[:8]))

    bio = props.get("bio", "")
    if not bio and node.content:
        bio = node.content

    conf = node.confidence if hasattr(node, "confidence") else None
    decay = node.decay_score if hasattr(node, "decay_score") else None

    render_profile_card(
        name=node.title,
        fields=fields,
        confidence=conf,
        decay=decay,
        bio=bio,
    )


def render_ascii_graph(subgraph, center_id: UUID | None = None):
    """Render a subgraph as a 2D mind-map / flowchart with boxed nodes
    and routed connectors.

    Layout strategy:
    - Find connected components
    - BFS tree per component, slot-based vertical positioning
    - Render on a character grid: boxed nodes in columns, connectors
      with junction routing and edge labels between them
    - Cross-edges listed below the diagram
    """
    nodes = subgraph.nodes
    edges = subgraph.edges

    if not nodes:
        print(f"  {C.DIM}Empty graph.{C.RESET}")
        return

    w = term_width()

    # ── 1. Build data structures ──────────────────────────────
    node_map = {str(n.id): n for n in nodes}
    adj: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
    edge_index: dict[frozenset, tuple] = {}

    for e in edges:
        src, tgt = str(e.source_id), str(e.target_id)
        label = (e.edge_type.value if hasattr(e.edge_type, 'value')
                 else str(e.edge_type))
        bidi = getattr(e, 'bidirectional', False)
        if src in node_map and tgt in node_map:
            adj[src].append((tgt, label, bidi))
            adj[tgt].append((src, label, bidi))
            edge_index[frozenset({src, tgt})] = (label, src, tgt, bidi)

    center_str = (str(center_id)
                  if center_id and str(center_id) in node_map else None)

    # ── 2. Find connected components ──────────────────────────
    unvisited = set(node_map.keys())
    components: list[list[str]] = []
    while unvisited:
        seed = next(iter(unvisited))
        comp: list[str] = []
        q = deque([seed])
        while q:
            nid = q.popleft()
            if nid not in unvisited:
                continue
            unvisited.discard(nid)
            comp.append(nid)
            for nb, _, _ in adj.get(nid, []):
                if nb in unvisited:
                    q.append(nb)
        components.append(comp)
    components.sort(key=len, reverse=True)

    multi = [c for c in components if len(c) > 1]
    isolated = [c[0] for c in components if len(c) == 1]

    if center_str:
        for i, c in enumerate(multi):
            if center_str in c:
                multi.insert(0, multi.pop(i))
                break

    n_comps = len(multi) + (1 if isolated else 0)

    # ── 3. Header ────────────────────────────────────────────
    is_galaxy = center_str and center_str == YOU_NODE_ID
    hdr_color = C.YELLOW if is_galaxy else C.CYAN
    print(f"\n{divider('\u2550', hdr_color)}")
    if is_galaxy:
        mode = "galaxy"
        title = "YOUR GALAXY"
    elif center_id:
        mode = "neighborhood"
        title = "RELATIONSHIP GRAPH"
    else:
        mode = "full graph"
        title = "RELATIONSHIP GRAPH"
    print(f"  {C.BOLD}{hdr_color}{title}{C.RESET}  "
          f"{C.DIM}({len(nodes)} nodes, {len(edges)} edges, "
          f"{n_comps} component"
          f"{'s' if n_comps != 1 else ''}, {mode}){C.RESET}")
    print(divider())

    # ── 4. Character grid ─────────────────────────────────────
    class Grid:
        """2D character buffer with per-cell foreground color + bold."""
        def __init__(self, gw, gh):
            self.gw, self.gh = gw, gh
            self.ch = [[' '] * gw for _ in range(gh)]
            self.fg = [[None] * gw for _ in range(gh)]
            self.bd = [[False] * gw for _ in range(gh)]

        def put(self, x, y, c, fg=None, bold=False):
            if 0 <= x < self.gw and 0 <= y < self.gh:
                self.ch[y][x] = c
                self.fg[y][x] = fg
                self.bd[y][x] = bold

        def puts(self, x, y, text, fg=None, bold=False):
            for i, c in enumerate(text):
                self.put(x + i, y, c, fg, bold)

        def render(self):
            out: list[str] = []
            for y in range(self.gh):
                last = -1
                for x in range(self.gw - 1, -1, -1):
                    if self.ch[y][x] != ' ':
                        last = x
                        break
                if last < 0:
                    out.append('')
                    continue
                line = ''
                cf, cb = None, False
                for x in range(last + 1):
                    c = self.ch[y][x]
                    f, b = self.fg[y][x], self.bd[y][x]
                    if f != cf or b != cb:
                        if cf or cb:
                            line += C.RESET
                        if b:
                            line += C.BOLD
                        if f:
                            line += f
                        cf, cb = f, b
                    line += c
                if cf or cb:
                    line += C.RESET
                out.append(line)
            while out and not out[-1]:
                out.pop()
            return out

    # ── 5. Icon / color maps (plain chars, no ANSI) ───────────
    ICHARS = {
        "EVENT": "*", "PERSON": "@", "COMMITMENT": "!",
        "DECISION": "?", "GOAL": ">", "FINANCIAL_ITEM": "$",
        "NOTE": "#", "IDEA": "~", "PROJECT": "P",
        "CONCEPT": "C", "REFERENCE": "R", "INSIGHT": "!",
    }
    ICOLORS = {
        "EVENT": C.YELLOW, "PERSON": C.CYAN, "COMMITMENT": C.RED,
        "DECISION": C.GREEN, "GOAL": C.MAGENTA,
        "FINANCIAL_ITEM": C.GREEN, "NOTE": C.LGRAY, "IDEA": C.PINK,
        "PROJECT": C.BLUE, "CONCEPT": C.TEAL, "REFERENCE": C.DIM,
        "INSIGHT": C.ORANGE,
    }
    NCHARS = {
        "ACADEMIC": "A", "PROFESSIONAL": "P", "FINANCIAL": "$",
        "HEALTH": "H", "PERSONAL_GROWTH": "G", "SOCIAL": "S",
        "VENTURES": "V",
    }
    NCOLORS = {
        "ACADEMIC": C.BLUE, "PROFESSIONAL": C.CYAN,
        "FINANCIAL": C.GREEN, "HEALTH": C.RED,
        "PERSONAL_GROWTH": C.MAGENTA, "SOCIAL": C.YELLOW,
        "VENTURES": C.ORANGE,
    }

    # ── 6. Junction character lookup ──────────────────────────
    _JUNC = {
        0b0011: '\u250c', 0b0111: '\u251c', 0b0110: '\u2514',
        0b1011: '\u252c', 0b1111: '\u253c', 0b1110: '\u2534',
        0b1001: '\u2510', 0b1101: '\u2524', 0b1100: '\u2518',
        0b1010: '\u2500', 0b0101: '\u2502',
        0b1000: '\u2500', 0b0010: '\u2500',
        0b0100: '\u2502', 0b0001: '\u2502',
    }

    def junc(left, up, right, down):
        return _JUNC.get(
            (left << 3) | (up << 2) | (right << 1) | down, ' ')

    # ── 7. Constants ─────────────────────────────────────────
    BOX_H = 3
    GAP_Y = 1
    SLOT_H = BOX_H + GAP_Y
    CONN_W = 14
    LABEL_MAX = 8

    CROSS_CHAR_H = '╌'
    CROSS_CHAR_V = '╎'
    CROSS_COLOR = C.MAGENTA
    CROSS_MAX_ROUTES = 8

    # ── 8. Draw a node box on the grid ────────────────────────
    def draw_box(g, x, y, bw, nid,
                 highlight=False, right_conn=False, left_conn=False):
        n = node_map[nid]
        is_you = (nid == YOU_NODE_ID)
        bc = C.YELLOW if is_you else (C.CYAN if highlight else C.DIM)

        if is_you:
            g.put(x, y, '\u2554', bc)
            for i in range(1, bw - 1):
                g.put(x + i, y, '\u2550', bc)
            g.put(x + bw - 1, y, '\u2557', bc)
            lc = '\u2562' if left_conn else '\u2551'
            rc = '\u255f' if right_conn else '\u2551'
            g.put(x, y + 1, lc, bc)
            g.put(x + bw - 1, y + 1, rc, bc)
            g.put(x, y + 2, '\u255a', bc)
            for i in range(1, bw - 1):
                g.put(x + i, y + 2, '\u2550', bc)
            g.put(x + bw - 1, y + 2, '\u255d', bc)
        else:
            g.put(x, y, '\u250c', bc)
            for i in range(1, bw - 1):
                g.put(x + i, y, '\u2500', bc)
            g.put(x + bw - 1, y, '\u2510', bc)
            lc = '\u2524' if left_conn else '\u2502'
            rc = '\u251c' if right_conn else '\u2502'
            g.put(x, y + 1, lc, bc)
            g.put(x + bw - 1, y + 1, rc, bc)
            g.put(x, y + 2, '\u2514', bc)
            for i in range(1, bw - 1):
                g.put(x + i, y + 2, '\u2500', bc)
            g.put(x + bw - 1, y + 2, '\u2518', bc)

        inner = bw - 2
        ic = '\u2605' if is_you else ICHARS.get(n.node_type.value, ' ')
        icol = C.YELLOW if is_you else ICOLORS.get(n.node_type.value, None)
        sid = str(n.id)[:6]

        nets_list = n.networks[:1]
        net_w = 4 if nets_list else 0
        overhead = 3 + 9 + net_w
        title_max = max(3, inner - overhead)
        title = n.title[:title_max]
        if len(n.title) > title_max and title_max > 4:
            title = title[:-2] + '..'

        cx = x + 1
        g.put(cx, y + 1, ' ')
        g.put(cx + 1, y + 1, ic, icol, bold=highlight)
        g.put(cx + 2, y + 1, ' ')
        cx += 3

        tc = C.YELLOW if is_you else (C.CYAN if highlight else None)
        for ch in title:
            g.put(cx, y + 1, ch, tc, bold=True)
            cx += 1

        right_start = x + bw - 1 - (9 + net_w)
        if right_start > cx:
            cx = right_start

        g.put(cx, y + 1, ' ', C.DIM)
        cx += 1
        g.puts(cx, y + 1, '[' + sid + ']', C.DIM)
        cx += 8

        if nets_list and cx < x + bw - 4:
            nt = nets_list[0].value
            nc = NCOLORS.get(nt, C.DIM)
            nch = NCHARS.get(nt, '?')
            g.puts(cx, y + 1, '[' + nch + ']', nc)

    # ── 9. Draw connectors from a parent to its children ─────
    def draw_connectors(g, par_nid, kids, ngx, ngy, bw):
        par_mid = ngy[par_nid] + 1
        gap_start = ngx[par_nid] + bw
        jx = gap_start + 2

        child_info = [(k, ngx[k], ngy[k] + 1)
                      for k in kids if k in ngy]
        if not child_info:
            return
        child_info.sort(key=lambda t: t[2])

        top_y = min(par_mid, child_info[0][2])
        bot_y = max(par_mid, child_info[-1][2])

        for cx in range(gap_start, min(jx + 1, g.gw)):
            g.put(cx, par_mid, '\u2500', C.DIM)

        for cy in range(top_y, bot_y + 1):
            g.put(jx, cy, '\u2502', C.DIM)

        child_mids = {ci[2] for ci in child_info}
        for cy in range(top_y, bot_y + 1):
            ch = junc(cy == par_mid, cy > top_y,
                      cy in child_mids, cy < bot_y)
            if ch != ' ':
                g.put(jx, cy, ch, C.DIM)

        for kid, kid_x, kid_mid in child_info:
            for cx in range(jx + 1, kid_x):
                g.put(cx, kid_mid, '\u2500', C.DIM)

            einfo = edge_index.get(frozenset({par_nid, kid}),
                                   ('', par_nid, kid, False))
            elabel, esrc, _, ebidi = einfo
            if ebidi:
                arrow = '\u2194'
            elif esrc == par_nid:
                arrow = '\u2192'
            else:
                arrow = '\u2190'

            ltxt = elabel[:LABEL_MAX] + arrow
            avail = kid_x - jx - 2
            if len(ltxt) > avail > 0:
                ltxt = ltxt[:avail]
            g.puts(jx + 1, kid_mid, ltxt, C.DIM)

    # ── 10. Render one connected component ────────────────────
    def render_component(comp, center_nid):
        comp_set = set(comp)

        if center_nid and center_nid in comp_set:
            root = center_nid
        elif YOU_NODE_ID in comp_set:
            root = YOU_NODE_ID
        else:
            root = max(comp_set, key=lambda k: len(adj.get(k, [])))

        parent_map = {root: None}
        depth_map = {root: 0}
        children_map: dict[str, list[str]] = defaultdict(list)
        q = deque([root])
        while q:
            nid = q.popleft()
            for nb, _, _ in adj.get(nid, []):
                if nb in comp_set and nb not in parent_map:
                    parent_map[nb] = nid
                    depth_map[nb] = depth_map[nid] + 1
                    children_map[nid].append(nb)
                    q.append(nb)

        for par in children_map:
            children_map[par].sort(
                key=lambda k: (node_map[k].node_type.value,
                               node_map[k].title))

        d1_nodes = [nid for nid, d in depth_map.items() if d == 1]
        if len(d1_nodes) > 3:
            d1_set = set(d1_nodes)
            d1_edges: list[tuple[str, str]] = []
            for nid in d1_nodes:
                for nb, _, _ in adj.get(nid, []):
                    if nb in d1_set and nb > nid:
                        d1_edges.append((nid, nb))
            d1_degree: dict[str, int] = defaultdict(int)
            for a, b in d1_edges:
                d1_degree[a] += 1
                d1_degree[b] += 1
            hubs = sorted(d1_degree, key=lambda n: d1_degree[n],
                          reverse=True)
            moved: set[str] = set()
            for hub in hubs:
                if hub in moved:
                    continue
                peers = [nb for nb, _, _ in adj.get(hub, [])
                         if nb in d1_set and nb != hub
                         and nb not in moved and nb != root
                         and hub != root]
                if not peers or hub == root:
                    continue
                for peer in peers[:4]:
                    if peer in children_map.get(root, []):
                        children_map[root].remove(peer)
                        children_map[hub].append(peer)
                        parent_map[peer] = hub
                        depth_map[peer] = 2
                        q2 = deque(children_map.get(peer, []))
                        while q2:
                            ch = q2.popleft()
                            depth_map[ch] = depth_map[parent_map[ch]] + 1
                            q2.extend(children_map.get(ch, []))
                        moved.add(peer)
                moved.add(hub)

        for par in children_map:
            children_map[par].sort(
                key=lambda k: (node_map[k].node_type.value,
                               node_map[k].title))

        max_depth = max(depth_map.values()) if depth_map else 0

        vis = max_depth + 1
        box_w = 24
        while vis > 1:
            needed = vis * box_w + (vis - 1) * CONN_W + 4
            if needed <= w:
                break
            vis -= 1
        box_w = max(16, min(28,
                    (w - 4 - max(0, vis - 1) * CONN_W) // max(1, vis)))
        while vis > 1:
            needed = vis * box_w + (vis - 1) * CONN_W + 4
            if needed <= w:
                break
            vis -= 1

        if vis < max_depth + 1:
            for nid in list(children_map.keys()):
                if depth_map.get(nid, 0) >= vis - 1:
                    children_map[nid] = []

        positions: dict[str, tuple[int, int]] = {}
        slot_ctr = [0]

        def assign(nid):
            kids = children_map.get(nid, [])
            if not kids:
                positions[nid] = (depth_map[nid], slot_ctr[0])
                slot_ctr[0] += 1
                return slot_ctr[0] - 1, slot_ctr[0] - 1
            first = slot_ctr[0]
            for kid in kids:
                assign(kid)
            last = slot_ctr[0] - 1
            positions[nid] = (depth_map[nid], (first + last) // 2)
            return first, last

        assign(root)
        total_slots = slot_ctr[0]

        mx, my = 1, 0
        ngx: dict[str, int] = {}
        ngy: dict[str, int] = {}
        for nid, (col, slot) in positions.items():
            ngx[nid] = mx + col * (box_w + CONN_W)
            ngy[nid] = my + slot * SLOT_H

        tree_edge_set = {frozenset({nid, par})
                         for nid, par in parent_map.items()
                         if par is not None}
        cross_edges = []
        for nid in comp_set:
            for nb, lbl, bidi in adj.get(nid, []):
                if nb in comp_set and nb > nid:
                    pair = frozenset({nid, nb})
                    if pair not in tree_edge_set:
                        cross_edges.append((nid, nb, lbl, bidi))

        n_routes = min(len(cross_edges), CROSS_MAX_ROUTES)
        gutter_w = n_routes * 2 + (2 if n_routes else 0)

        base_grid_w = (mx + vis * box_w + max(0, vis - 1) * CONN_W
                       + mx + 1)
        grid_w = min(base_grid_w + gutter_w, w - 2)
        actual_gutter = grid_w - base_grid_w
        if actual_gutter < 4:
            n_routes = 0
            actual_gutter = 0
            grid_w = min(base_grid_w, w - 2)
        else:
            n_routes = min(n_routes, (actual_gutter - 2) // 2)

        grid_h = min(my + total_slots * SLOT_H + my, 200)

        g = Grid(grid_w, grid_h)

        has_right = {nid for nid in children_map if children_map[nid]}
        has_left = {nid for nid, par in parent_map.items()
                    if par is not None}

        for par_nid in children_map:
            if children_map[par_nid]:
                draw_connectors(g, par_nid, children_map[par_nid],
                                ngx, ngy, box_w)

        for nid in positions:
            if nid in ngx and nid in ngy:
                draw_box(g, ngx[nid], ngy[nid], box_w, nid,
                         highlight=(nid == center_nid or nid == YOU_NODE_ID),
                         right_conn=(nid in has_right),
                         left_conn=(nid in has_left))

        def draw_cross_edges(g, cross_edges, ngx, ngy, box_w,
                             n_routes, base_grid_w):
            if n_routes <= 0:
                return
            gutter_start = base_grid_w
            routed = 0
            for a, b, lbl, bidi in cross_edges[:n_routes]:
                if a not in ngy or b not in ngy:
                    continue
                col_idx = gutter_start + 1 + routed * 2
                if col_idx >= g.gw:
                    break
                a_mid = ngy[a] + 1
                b_mid = ngy[b] + 1
                a_right = ngx[a] + box_w
                b_right = ngx[b] + box_w

                if (a_mid < 0 or a_mid >= g.gh
                        or b_mid < 0 or b_mid >= g.gh):
                    continue

                top_y = min(a_mid, b_mid)
                bot_y = max(a_mid, b_mid)

                for cx in range(a_right, min(col_idx + 1, g.gw)):
                    if g.ch[a_mid][cx] == ' ':
                        g.put(cx, a_mid, CROSS_CHAR_H, CROSS_COLOR)

                for cx in range(b_right, min(col_idx + 1, g.gw)):
                    if g.ch[b_mid][cx] == ' ':
                        g.put(cx, b_mid, CROSS_CHAR_H, CROSS_COLOR)

                for cy in range(top_y, min(bot_y + 1, g.gh)):
                    if col_idx < g.gw and g.ch[cy][col_idx] == ' ':
                        g.put(col_idx, cy, CROSS_CHAR_V, CROSS_COLOR)

                mid_y = (top_y + bot_y) // 2
                short_lbl = lbl[:5]
                for li, lch in enumerate(short_lbl):
                    ly = mid_y - len(short_lbl) // 2 + li
                    if (top_y < ly < bot_y and 0 <= ly < g.gh
                            and col_idx < g.gw
                            and g.ch[ly][col_idx] in (' ', CROSS_CHAR_V)):
                        g.put(col_idx, ly, lch, CROSS_COLOR)

                routed += 1

        draw_cross_edges(g, cross_edges, ngx, ngy, box_w,
                         n_routes, base_grid_w)

        for line in g.render():
            print(f"  {line}")

        if vis < max_depth + 1:
            deeper = sum(1 for d in depth_map.values() if d >= vis)
            print(f"\n  {C.DIM}(+{deeper} nodes beyond depth "
                  f"{vis - 1} not shown){C.RESET}")

        return (tree_edge_set, n_routes)

    # ── 11. Main render loop ─────────────────────────────────
    all_tree_edges: set[frozenset] = set()
    total_routes = 0

    for ci, comp in enumerate(multi):
        if len(multi) > 1:
            print(f"\n  {C.BOLD}Component {ci + 1} of "
                  f"{len(multi)}{C.RESET}"
                  f"  {C.DIM}({len(comp)} nodes){C.RESET}")

        tree_edges, n_routes = render_component(comp, center_str)
        all_tree_edges |= tree_edges
        total_routes += n_routes

        cs = set(comp)
        cross = [
            e for e in edges
            if (frozenset({str(e.source_id), str(e.target_id)})
                not in all_tree_edges)
            and str(e.source_id) in cs
            and str(e.target_id) in cs
        ]
        if cross:
            hdr_text = " CROSS-CONNECTIONS "
            rule_w = max(0, w - len(hdr_text) - 8)
            print(f"\n  {C.BOLD}{CROSS_COLOR}"
                  f"╌╌{hdr_text}"
                  f"{'╌' * rule_w}{C.RESET}")
            if n_routes > 0:
                print(f"  {C.DIM}({n_routes} shown as dotted "
                      f"lines above){C.RESET}")

            by_type: dict[str, list] = defaultdict(list)
            for e in cross:
                el = (e.edge_type.value
                      if hasattr(e.edge_type, 'value')
                      else str(e.edge_type))
                by_type[el].append(e)

            shown = 0
            for etype in sorted(by_type):
                if shown >= 15:
                    break
                print(f"  {CROSS_COLOR}{C.BOLD}{etype}:{C.RESET}")
                for e in by_type[etype]:
                    if shown >= 15:
                        break
                    src, tgt = str(e.source_id), str(e.target_id)
                    sn, tn = node_map.get(src), node_map.get(tgt)
                    si = ICHARS.get(sn.node_type.value, ' ') if sn else ' '
                    ti = ICHARS.get(tn.node_type.value, ' ') if tn else ' '
                    sicol = ICOLORS.get(sn.node_type.value, '') if sn else ''
                    ticol = ICOLORS.get(tn.node_type.value, '') if tn else ''
                    st = sn.title[:16] if sn else src[:8]
                    tt = tn.title[:16] if tn else tgt[:8]
                    bd = getattr(e, 'bidirectional', False)
                    arr = '\u2194' if bd else '\u2192'
                    print(f"    {sicol}{si}{C.RESET} {st} "
                          f"{C.DIM}[{src[:6]}]{C.RESET} "
                          f"{CROSS_COLOR}╌╌[{arr}]╌╌{C.RESET} "
                          f"{ticol}{ti}{C.RESET} {tt} "
                          f"{C.DIM}[{tgt[:6]}]{C.RESET}")
                    shown += 1
            remaining = len(cross) - shown
            if remaining > 0:
                print(f"  {C.DIM}  ... and "
                      f"{remaining} more{C.RESET}")
            all_tree_edges |= {
                frozenset({str(e.source_id), str(e.target_id)})
                for e in cross}

    # ── 12. Isolated singletons ──────────────────────────────
    if isolated:
        rule_w = max(0, w - 35)
        print(f"\n  {C.DIM}\u2500\u2500 unconnected nodes "
              f"({len(isolated)}) "
              + "\u2500" * rule_w + f"{C.RESET}")
        for nid in isolated:
            n = node_map[nid]
            ic = ICHARS.get(n.node_type.value, ' ')
            icol = ICOLORS.get(n.node_type.value, '')
            nets = ''.join(
                NETWORK_ICONS.get(nt.value, '') for nt in n.networks[:2])
            print(f"  {icol}{ic}{C.RESET} {C.BOLD}"
                  f"{n.title[:24]}{C.RESET} "
                  f"{C.DIM}[{str(n.id)[:6]}]{C.RESET} {nets}")

    # ── 13. Legend ───────────────────────────────────────────
    print(f"\n{divider()}")
    print(f"  {C.BOLD}LEGEND{C.RESET}")

    if any(str(n.id) == YOU_NODE_ID for n in nodes):
        print(f"  {C.YELLOW}\u2605{C.RESET}={C.DIM}YOU (center){C.RESET}  "
              f"{C.YELLOW}\u2554\u2550\u2557{C.RESET} {C.DIM}double border = You node{C.RESET}")

    types_present = sorted({n.node_type.value for n in nodes})
    tl = "  Types:     "
    for t in types_present:
        ic = ICHARS.get(t, ' ')
        icol = ICOLORS.get(t, '')
        tl += f" {icol}{ic}{C.RESET}={C.DIM}{t}{C.RESET}"
    print(tl)

    nets_present = sorted(
        {nt.value for n in nodes for nt in n.networks})
    if nets_present:
        nl = "  Networks:  "
        for nt in nets_present:
            icon = NETWORK_ICONS.get(nt, f"[{nt[0]}]")
            nl += f" {icon}={C.DIM}{nt}{C.RESET}"
        print(nl)

    edge_types = sorted({
        e.edge_type.value if hasattr(e.edge_type, 'value')
        else str(e.edge_type) for e in edges})
    if edge_types:
        print(f"  {C.DIM}Edges:      "
              f"{', '.join(edge_types)}{C.RESET}")

    print(f"\n  {C.DIM}Arrows: \u2192 directed  "
          f"\u2190 inbound  \u2194 bidirectional{C.RESET}")
    print(f"  {C.DIM}\u251c\u2500\u2500 connector exit   "
          f"\u2524\u2500\u2500 connector entry{C.RESET}")
    print(f"  {CROSS_COLOR}╌╌╌{C.RESET}"
          f" {C.DIM}= cross-connection (non-tree edge){C.RESET}")
    if center_id:
        print(f"  {C.CYAN}Colored box{C.RESET}"
              f" {C.DIM}= center node{C.RESET}")
    print(divider('\u2550', C.CYAN))
