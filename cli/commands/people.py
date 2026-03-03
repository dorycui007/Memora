"""People command — people directory & relationship intelligence."""

from __future__ import annotations

from cli.rendering import (
    C, NETWORK_ICONS, NODE_ICONS, divider, horizontal_bar,
    menu_option, people_header, prompt, render_profile_card, subcommand_header,
)


def cmd_people(app):
    """People intelligence sub-menu."""
    while True:
        people_header()
        print(menu_option("1", "Directory",   "Paginated people list"))
        print(menu_option("2", "Profile",     "Individual relationship view"))
        print(menu_option("3", "Statistics",  "People analytics dashboard"))
        print(menu_option("4", "Mutual",      "Shared connections between two people"))
        print(menu_option("5", "Merge",       "Merge duplicate person nodes"))
        print()

        choice = prompt("people> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _directory_view(app)
        elif choice == "2":
            _profile_view(app)
        elif choice == "3":
            _statistics_view(app)
        elif choice == "4":
            _mutual_view(app)
        elif choice == "5":
            _merge_view(app)


# ── Helpers ───────────────────────────────────────────────────

def _strength_bar(value: float, width: int = 10) -> str:
    """Compact strength bar with dynamic color based on value."""
    if value >= 0.7:
        color = C.GREEN
    elif value >= 0.4:
        color = C.YELLOW
    else:
        color = C.RED
    return horizontal_bar(value, width, color)


def _network_badges(networks: list[str]) -> str:
    """Render network badges like [P][S]."""
    if not networks:
        return f"{C.DIM}—{C.RESET}"
    badges = []
    for n in networks:
        icon = NETWORK_ICONS.get(n, f"{C.DIM}[?]{C.RESET}")
        badges.append(icon)
    return "".join(badges)


def _node_icon(node_type: str) -> str:
    return NODE_ICONS.get(node_type, " ")


def _get_engine(app):
    from memora.core.people_intel import PeopleIntelEngine
    return PeopleIntelEngine(app.repo)


def _search_person(app, label: str = "Person name") -> str | None:
    """Prompt for a person name, search, and return selected ID."""
    name = prompt(f"{label}> ")
    if not name or name in ("b", "back"):
        return None

    from memora.graph.models import NodeFilter, NodeType
    results = app.repo.query_nodes(NodeFilter(
        node_types=[NodeType.PERSON],
        limit=20,
    ))

    # Filter by name match (case-insensitive)
    matches = [n for n in results if name.lower() in n.title.lower()]

    if not matches:
        print(f"  {C.DIM}No people found matching '{name}'{C.RESET}")
        return None

    if len(matches) == 1:
        print(f"  {C.DIM}→ {matches[0].title}{C.RESET}")
        return str(matches[0].id)

    print(f"\n  {C.BOLD}Multiple matches:{C.RESET}")
    for i, m in enumerate(matches[:10], 1):
        nets = _network_badges([n.value for n in m.networks])
        print(f"    {C.BOLD}{i}.{C.RESET} {m.title}  {nets}")

    sel = prompt("Select #> ")
    try:
        idx = int(sel) - 1
        if 0 <= idx < len(matches):
            return str(matches[idx].id)
    except (ValueError, IndexError):
        pass
    print(f"  {C.DIM}Invalid selection.{C.RESET}")
    return None


# ── Directory View ────────────────────────────────────────────

def _directory_view(app):
    """Paginated people directory."""
    engine = _get_engine(app)
    sort_by = "connections"
    order = "desc"
    page = 0
    page_size = 20
    network_filter = None

    while True:
        data = engine.get_people_directory(
            sort_by=sort_by, order=order,
            limit=page_size, offset=page * page_size,
            network_filter=network_filter,
        )
        people = data["people"]
        total = data["total"]
        total_pages = max(1, (total + page_size - 1) // page_size)

        # Header
        net_label = f"  {C.DIM}(network: {network_filter}){C.RESET}" if network_filter else ""
        print(f"\n  {C.BOLD}{C.CYAN}@ PEOPLE DIRECTORY{C.RESET}"
              f"  {C.DIM}{total} people{C.RESET}{net_label}")
        print(f"  {C.DIM}{'─' * 72}{C.RESET}")

        # Column header
        print(f"  {C.DIM}{'#':>3}  {'Name':<22} {'Role':<16} {'Networks':<10} "
              f"{'Conns':>5}  {'Strength'}{C.RESET}")

        if not people:
            print(f"\n  {C.DIM}No people found.{C.RESET}")
        else:
            for i, p in enumerate(people, start=page * page_size + 1):
                name = p["title"][:20]
                role = (p.get("role") or "")[:14]
                nets = _network_badges(p.get("networks", []))
                conns = p.get("connection_count", 0)

                # Approximate strength from decay + confidence
                confidence = p.get("confidence") or 0.5
                decay = p.get("decay_score") or 0.5
                approx_strength = (confidence + decay) / 2
                bar = _strength_bar(approx_strength)

                print(f"  {C.BOLD}{i:>3}.{C.RESET} {name:<22} {C.DIM}{role:<16}{C.RESET} "
                      f"{nets:<10} {conns:>5}  {bar}")

        # Footer
        print(f"\n  {C.DIM}Page {page + 1}/{total_pages}  |  "
              f"Sort: {sort_by} ({order}){C.RESET}")
        print(f"  {C.DIM}[s] Sort  [n] Filter network  [#] View profile  "
              f"[>/<] Page  [b] Back{C.RESET}")

        choice = prompt("directory> ")
        if choice in ("b", "back"):
            return
        elif choice == ">" and page < total_pages - 1:
            page += 1
        elif choice == "<" and page > 0:
            page -= 1
        elif choice == "s":
            print(f"  {C.DIM}Sort options: name, connections, last_activity, decay, confidence{C.RESET}")
            s = prompt("sort by> ")
            if s in ("name", "title"):
                sort_by, order = "title", "asc"
            elif s in ("connections", "conns"):
                sort_by, order = "connections", "desc"
            elif s in ("last_activity", "recent"):
                sort_by, order = "last_activity", "desc"
            elif s in ("decay",):
                sort_by, order = "decay", "asc"
            elif s in ("confidence",):
                sort_by, order = "confidence", "desc"
            page = 0
        elif choice == "n":
            print(f"  {C.DIM}Enter network name (e.g. PROFESSIONAL, SOCIAL) or empty to clear:{C.RESET}")
            nf = prompt("network> ").upper()
            network_filter = nf if nf else None
            page = 0
        else:
            # Try numeric selection → view profile
            try:
                idx = int(choice) - 1 - (page * page_size)
                if 0 <= idx < len(people):
                    _show_profile(app, people[idx]["id"])
            except (ValueError, IndexError):
                pass



# ── Profile View ──────────────────────────────────────────────

def _profile_view(app):
    """Prompt for a person and show their full profile."""
    person_id = _search_person(app, "Person to profile")
    if person_id:
        _show_profile(app, person_id)


def _show_profile(app, person_id: str):
    """Render a full person profile with ranked connections."""
    engine = _get_engine(app)
    profile = engine.get_person_profile(person_id)
    if profile is None:
        print(f"  {C.RED}Person not found.{C.RESET}")
        return

    while True:
        title = profile["title"]
        props = profile.get("properties", {})
        content = profile.get("content", "")

        # Confidence / decay — use explicit None check, not truthiness
        raw_conf = profile.get("confidence")
        raw_decay = profile.get("decay_score")
        conf = float(raw_conf) if raw_conf is not None else None
        decay = float(raw_decay) if raw_decay is not None else None

        # Build fields from all available data
        fields: list[tuple[str, str]] = []

        role = profile.get("role") or props.get("role", "")
        if role:
            fields.append(("Role", role))

        org = profile.get("organization") or props.get("organization", "")
        if org:
            fields.append(("Org", org))

        location = profile.get("location") or props.get("location", "")
        if location:
            fields.append(("Location", location))

        rel = profile.get("relationship_to_user") or props.get("relationship_to_user", "")
        if rel:
            fields.append(("Relationship", rel))

        nets_list = profile.get("networks", [])
        if nets_list:
            fields.append(("Networks", _network_badges(nets_list)))

        # Extra properties not already shown
        shown_keys = {"name", "role", "organization", "location",
                      "relationship_to_user", "bio"}
        for k, v in props.items():
            if k not in shown_keys and v:
                label = k.replace("_", " ").title()
                val = ", ".join(v) if isinstance(v, list) else str(v)
                fields.append((label, val))

        tags = profile.get("tags", [])
        if tags:
            fields.append(("Tags", ", ".join(tags)))

        # Metadata fields when profile is sparse
        created = profile.get("created_at", "")
        if created and len(fields) < 4:
            # Show date portion only
            date_str = created[:10] if len(created) >= 10 else created
            fields.append(("Since", date_str))

        short_id = str(profile.get("id", ""))[:8]
        if short_id and len(fields) < 5:
            fields.append(("ID", short_id))

        # Summary strip
        ranked = profile.get("ranked_connections", [])
        summary = profile.get("connection_summary", {})
        total_conns = summary.get("total", 0)
        by_type = summary.get("by_node_type", {})

        summary_lines: list[str] = []
        if ranked:
            strongest = max(c["strength"] for c in ranked)
            weakest = min(c["strength"] for c in ranked)
            summary_lines.append(
                f"{C.BOLD}CONNECTIONS{C.RESET}  {C.BASE}{total_conns}{C.RESET}"
                f"       {C.BOLD}STRONGEST{C.RESET}  {C.BASE}{strongest:.2f}{C.RESET}"
                f"       {C.BOLD}WEAKEST{C.RESET}  {C.BASE}{weakest:.2f}{C.RESET}"
            )
        if by_type:
            type_parts = "  │  ".join(f"{C.BOLD}{k}:{C.RESET} {v}" for k, v in sorted(by_type.items()))
            summary_lines.append(type_parts)

        # Bio: prefer explicit bio prop, fall back to content
        bio = profile.get("bio") or props.get("bio", "")
        if not bio and content:
            bio = content[:200]

        print()
        render_profile_card(
            name=title,
            fields=fields,
            confidence=conf,
            decay=decay,
            bio=bio,
            summary_lines=summary_lines,
        )

        # Ranked connections table
        print(f"\n  {C.BOLD}RANKED CONNECTIONS ({total_conns}){C.RESET}")
        print(f"  {C.DIM}{'─' * 72}{C.RESET}")

        if not ranked:
            print(f"  {C.DIM}No connections found.{C.RESET}")
        else:
            for i, c in enumerate(ranked[:20], 1):
                direction = "->" if c["direction"] == "outgoing" else "<-"
                icon = _node_icon(c["node_type"])
                edge_label = c["edge_type"]
                bar = _strength_bar(c["strength"])
                name = c["title"][:22]
                print(f"  {i:>2}. {direction} {icon} {name:<22} "
                      f"{C.DIM}[{edge_label}]{C.RESET}  {bar}")

        print(f"\n  {C.DIM}[#] Drill into connection  [m] Mutual connections  [b] Back{C.RESET}")

        choice = prompt("profile> ")
        if choice in ("b", "back"):
            return
        elif choice == "m":
            # Mutual connections with another person
            other_id = _search_person(app, "Compare with")
            if other_id:
                _show_mutual(app, person_id, other_id)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(ranked):
                    target = ranked[idx]
                    if target["node_type"] == "PERSON":
                        _show_profile(app, target["node_id"])
                    else:
                        print(f"\n  {C.BOLD}{_node_icon(target['node_type'])} "
                              f"{target['title']}{C.RESET}")
                        print(f"  {C.DIM}Type: {target['node_type']}  |  "
                              f"Edge: {target['edge_type']}  |  "
                              f"Strength: {_strength_bar(target['strength'])}{C.RESET}")
            except (ValueError, IndexError):
                pass


# ── Statistics View ───────────────────────────────────────────

def _statistics_view(app):
    """People analytics dashboard."""
    engine = _get_engine(app)
    stats = engine.get_people_statistics()

    total = stats.get("total_people", 0)
    avg = stats.get("avg_connections", 0)
    disconnected = stats.get("disconnected_count", 0)
    health = stats.get("relationship_health", {})
    net_dist = stats.get("network_distribution", {})
    most_conn = stats.get("most_connected", [])
    strongest = stats.get("strongest_ties", [])
    edge_types = stats.get("edge_type_distribution", [])

    # Compute total edges for people
    total_edges = sum(e.get("count", 0) for e in edge_types)

    print(f"\n  {C.BOLD}{C.CYAN}@ PEOPLE STATISTICS{C.RESET}")
    print(f"  {C.DIM}{'─' * 72}{C.RESET}")

    # Big numbers
    print(f"\n       {C.BOLD}{total}{C.RESET}              "
          f"{C.BOLD}{total_edges}{C.RESET}             "
          f"{C.BOLD}{avg:.1f}{C.RESET}")
    print(f"     {C.DIM}people{C.RESET}          "
          f"{C.DIM}edges{C.RESET}           "
          f"{C.DIM}avg conns{C.RESET}")

    # Network distribution + Relationship health side by side
    active = health.get("active", 0)
    fading = health.get("fading", 0)
    cold = health.get("cold", 0)
    htotal = active + fading + cold or 1

    print(f"\n  {C.BOLD}NETWORK DISTRIBUTION{C.RESET}"
          f"          {C.BOLD}RELATIONSHIP HEALTH{C.RESET}")

    net_lines = []
    for net, cnt in sorted(net_dist.items(), key=lambda x: -x[1]):
        badge = NETWORK_ICONS.get(net, f"[{net[:1]}]")
        net_lines.append(f"  {badge} {net:<18} {cnt}")

    health_lines = [
        f"  {C.GREEN}Active  (<30d){C.RESET}   {active:>3}  {active * 100 // htotal}%",
        f"  {C.YELLOW}Fading  (30-90d){C.RESET} {fading:>3}  {fading * 100 // htotal}%",
        f"  {C.RED}Cold    (>90d){C.RESET}   {cold:>3}  {cold * 100 // htotal}%",
    ]

    max_lines = max(len(net_lines), len(health_lines))
    for i in range(max_lines):
        left = net_lines[i] if i < len(net_lines) else " " * 30
        right = health_lines[i] if i < len(health_lines) else ""
        print(f"{left:<38}{right}")

    if disconnected:
        print(f"\n  {C.DIM}Disconnected people (0 edges): {disconnected}{C.RESET}")

    # Most connected
    if most_conn:
        print(f"\n  {C.BOLD}MOST CONNECTED{C.RESET}")
        for i, mc in enumerate(most_conn, 1):
            print(f"  {i}. {mc['title']} ({mc['connections']})")

    # Strongest ties
    if strongest:
        print(f"\n  {C.BOLD}STRONGEST TIES{C.RESET}")
        for i, st in enumerate(strongest, 1):
            bar = _strength_bar(st["strength"])
            print(f"  {i}. {st['source_title']} <-> {st['target_title']}  {bar}")

    print()
    prompt("Press Enter to continue...")


# ── Mutual Connections View ───────────────────────────────────

def _mutual_view(app):
    """Prompt for two people and show mutual connections."""
    print(f"\n  {C.BOLD}Find mutual connections between two people{C.RESET}")
    a_id = _search_person(app, "First person")
    if not a_id:
        return
    b_id = _search_person(app, "Second person")
    if not b_id:
        return
    _show_mutual(app, a_id, b_id)


def _show_mutual(app, a_id: str, b_id: str):
    """Display mutual connections between two people."""
    engine = _get_engine(app)
    result = engine.find_mutual_connections(a_id, b_id)

    a_name = result["person_a"]["title"]
    b_name = result["person_b"]["title"]
    mutual = result["mutual_connections"]

    print(f"\n  {C.BOLD}MUTUAL CONNECTIONS{C.RESET}")
    print(f"  {C.CYAN}{a_name}{C.RESET}  ←→  {C.CYAN}{b_name}{C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

    if not mutual:
        print(f"  {C.DIM}No mutual connections found.{C.RESET}")
    else:
        print(f"  {C.BOLD}{len(mutual)} shared connection(s){C.RESET}\n")
        for m in mutual:
            icon = _node_icon(m["node_type"])
            nets = _network_badges(m.get("networks", []))
            ea = m.get("edge_to_a", {})
            eb = m.get("edge_to_b", {})

            print(f"  {icon} {C.BOLD}{m['title']}{C.RESET}  {nets}")
            print(f"    → {a_name}: {C.DIM}[{ea.get('edge_type', '?')}]{C.RESET}")
            print(f"    → {b_name}: {C.DIM}[{eb.get('edge_type', '?')}]{C.RESET}")
            print()

    prompt("Press Enter to continue...")


# ── Merge View ────────────────────────────────────────────────

def _merge_view(app):
    """Merge two duplicate person nodes."""
    print(f"\n  {C.BOLD}{C.CYAN}@ MERGE DUPLICATE PEOPLE{C.RESET}")
    print(f"  {C.DIM}This will merge one person into another, transferring all connections.{C.RESET}\n")

    print(f"  {C.BOLD}Step 1:{C.RESET} Search for the {C.RED}duplicate to remove{C.RESET}")
    source_id = _search_person(app, "Duplicate to remove")
    if not source_id:
        return

    print(f"\n  {C.BOLD}Step 2:{C.RESET} Search for the {C.GREEN}person to keep{C.RESET}")
    target_id = _search_person(app, "Person to keep")
    if not target_id:
        return

    if source_id == target_id:
        print(f"  {C.RED}Cannot merge a person into themselves.{C.RESET}")
        return

    # Show both for confirmation
    from uuid import UUID
    source_node = app.repo.get_node(UUID(source_id))
    target_node = app.repo.get_node(UUID(target_id))
    if not source_node or not target_node:
        print(f"  {C.RED}Could not load one or both nodes.{C.RESET}")
        return

    source_nets = _network_badges([n.value for n in source_node.networks])
    target_nets = _network_badges([n.value for n in target_node.networks])

    print(f"\n  {C.DIM}{'─' * 60}{C.RESET}")
    print(f"  {C.RED}REMOVE:{C.RESET}  {source_node.title}  {source_nets}  {C.DIM}({str(source_node.id)[:8]}){C.RESET}")
    print(f"  {C.GREEN}KEEP:{C.RESET}    {target_node.title}  {target_nets}  {C.DIM}({str(target_node.id)[:8]}){C.RESET}")
    print(f"  {C.DIM}{'─' * 60}{C.RESET}")

    confirm = prompt("Confirm merge? (y/n)> ")
    if confirm.lower() not in ("y", "yes"):
        print(f"  {C.DIM}Merge cancelled.{C.RESET}")
        return

    try:
        app.repo.merge_person_nodes(source_id, target_id)
        print(f"\n  {C.GREEN}Merged '{source_node.title}' into '{target_node.title}'{C.RESET}")
        print(f"  {C.DIM}'{source_node.title}' added as alias. All connections transferred.{C.RESET}")
    except Exception as e:
        print(f"  {C.RED}Merge failed: {e}{C.RESET}")

    prompt("\nPress Enter to continue...")
