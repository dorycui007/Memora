"""Strategy Mindmap — campaign intelligence views rendered in the terminal."""

from __future__ import annotations

from cli.rendering import (
    C,
    box,
    divider,
    domain_badge,
    health_bar,
    horizontal_bar,
    menu_option,
    phase_bar,
    priority_badge,
    prompt,
    spinner,
    status_dot,
    strategy_header,
    subcommand_header,
    term_width,
    urgency_badge,
)
from cli.strategy.data import (
    CONTINGENCIES,
    DECISION_RULES,
    DOMAINS,
    ENTITY_DOMAINS,
    ENTITY_TYPE_MAP,
    ENTITY_TYPES,
    EXTERNAL_NETWORK,
    GRAPH_NODES,
    GROUP_COLORS,
    GROUP_LABELS,
    IGNITEUTM_RESULTS,
    LOCATIONS,
    NODE_DATA,
    PEOPLE_LOCATIONS,
    PHASE_LOCATION_RELEVANCE,
    PHASES,
    POST_ELECTION,
    SLATE_HISTORY,
    THEORY_OF_VICTORY,
    TIME_BUDGET,
)
from cli.strategy.phase_engine import (
    at_risk_entities,
    current_phase,
    days_until,
    phase_days_remaining,
    phase_progress,
    urgent_actions,
    urgency_level,
)


def cmd_strategy(app):
    """Main strategy command with sub-menu."""
    while True:
        print()
        strategy_header()
        cp = current_phase()
        prog = phase_progress()
        remaining = phase_days_remaining()
        rem_str = f"{remaining}d left" if remaining is not None else ""
        print(f"\n  {phase_bar(cp['code'], prog)}" + (f"  {C.DIM}{rem_str}{C.RESET}" if rem_str else ""))
        print()
        print(menu_option("1", "Briefing", "Phase status, KPIs, decisions, contingencies"))
        print(menu_option("2", "Timeline", "4-phase campaign track with milestones"))
        print(menu_option("3", "Directory", "Entity directory with filters"))
        print(menu_option("4", "Matrix", "Priority x Status risk matrix"))
        print(menu_option("5", "Command", "Organizational hierarchy tree"))
        print(menu_option("6", "Academics", "Course pipeline, GPA, Vector roadmap"))
        print(menu_option("7", "Intel", "Election data, threats, external network"))
        print(menu_option("8", "Graph", "Interactive network graph (TUI)"))
        print(menu_option("9", "Map", "Campus map with locations (TUI)"))
        print(menu_option("q", "Back", "Return to main menu"))

        choice = prompt("strategy> ")
        if choice in ("q", "b", "back"):
            return
        elif choice == "1":
            _view_briefing()
        elif choice == "2":
            _view_timeline()
        elif choice == "3":
            _view_directory()
        elif choice == "4":
            _view_matrix()
        elif choice == "5":
            _view_command()
        elif choice == "6":
            _view_academics()
        elif choice == "7":
            _view_intel()
        elif choice == "8":
            _view_graph()
        elif choice == "9":
            _view_map()


# ════════════════════════════════════════════
# VIEW 1: BRIEFING
# ════════════════════════════════════════════

def _view_briefing():
    subcommand_header(
        title="STRATEGY BRIEFING",
        symbol="◆",
        color=C.ACCENT,
        taglines=["Operational intelligence summary"],
        border="double",
    )
    A, B, D, S, R = C.ACCENT, C.BASE, C.DIM, C.SIGNAL, C.RESET
    w = min(term_width() - 4, 76)

    # — Phase Status —
    cp = current_phase()
    prog = phase_progress()
    remaining = phase_days_remaining()
    idx = 0
    for i, p in enumerate(PHASES):
        if p["id"] == cp["id"]:
            idx = i
    print(f"\n  {A}{C.BOLD}CURRENT PHASE{R}")
    print(f"  {phase_bar(cp['name'], prog)}")
    if remaining is not None:
        print(f"  {D}{remaining} days remaining  |  Phase {idx + 1} of {len(PHASES)}{R}")
    if idx + 1 < len(PHASES):
        nxt = PHASES[idx + 1]
        print(f"  {D}Next: {nxt['name']} ({nxt['start']}){R}")

    # — Urgent Actions —
    print(f"\n  {S}{C.BOLD}URGENT ACTIONS (next 14 days){R}")
    actions = urgent_actions(14)
    if actions:
        for eid, label, action, days_left in actions[:8]:
            dl = f"{days_left}d" if days_left is not None else "?"
            color = C.DANGER if (days_left is not None and days_left < 0) else (C.SIGNAL if (days_left is not None and days_left <= 7) else C.DIM)
            print(f"    {color}{dl:>5}{R}  {B}{action}{R}  {D}({label}){R}")
    else:
        print(f"    {D}No deadlines within 14 days.{R}")

    # — At-Risk —
    at_risk = at_risk_entities()
    if at_risk:
        print(f"\n  {C.DANGER}{C.BOLD}AT-RISK ITEMS{R}")
        for eid, data in at_risk:
            label = eid.replace("_", " ").title()
            note = data.get("properties", {}).get("Status", data.get("properties", {}).get("Path Status", ""))
            print(f"    {status_dot('at-risk')} {B}{label}{R}")
            if note:
                print(f"      {D}{note[:80]}{R}")

    # — Theory of Victory —
    tov = THEORY_OF_VICTORY
    print(f"\n  {A}{C.BOLD}THEORY OF VICTORY{R}")
    # Wrap the statement
    for line in _wrap(tov["statement"], w - 4):
        print(f"    {D}{line}{R}")
    # Vote math
    vm = tov["vote_math"]
    print(f"\n    {B}Votes needed: {A}{C.BOLD}{vm['needed']}{R}  {D}(turnout est. {vm['turnout']}){R}")
    sources = [
        ("CS Students", vm["cs_students"], C.ACCENT),
        ("First-Year", vm["first_year"], C.SIGNAL),
        ("Math/Stats", vm["math_stats"], C.CONFIRM),
        ("Slate Network", vm["slate_network"], C.INTEL),
    ]
    for label, count, color in sources:
        pct = count / vm["needed"]
        print(f"    {horizontal_bar(pct, 25, color)}  {B}{count:>3}{R}  {D}{label}{R}")

    # — Time Budget —
    print(f"\n  {A}{C.BOLD}WEEKLY TIME BUDGET{R}")
    tb = TIME_BUDGET
    discretionary = tb["available"]
    for item in tb["items"]:
        if item.get("fixed"):
            discretionary -= item["hours"]
    for item in tb["items"]:
        if not item.get("fixed"):
            pct = item["hours"] / discretionary
            print(f"    {horizontal_bar(pct, 20, C.ACCENT)}  {B}{item['hours']:>2}h{R}  {D}{item['label']}{R}")

    # — Decision Rules —
    print(f"\n  {A}{C.BOLD}DECISION RULES{R}")
    for rule in DECISION_RULES:
        print(f"    {priority_badge(rule['priority']): <25} {D}{rule['condition']}{R}")
        print(f"                           {B}{rule['result'][:70]}{R}")

    # — Contingencies —
    print(f"\n  {A}{C.BOLD}CONTINGENCY PLANS{R}")
    for c in CONTINGENCIES:
        st = status_dot(c["status"])
        print(f"    {st} {B}{c['goal']}{R}")
        print(f"      {D}{c['fallback'][:80]}{R}")

    # — Post-Election Roadmap —
    print(f"\n  {A}{C.BOLD}POST-ELECTION ROADMAP{R}")
    for month_block in POST_ELECTION:
        print(f"\n    {S}{C.BOLD}{month_block['month']}{R}")
        for item in month_block["items"]:
            marker = f"{A}►{R}" if item["key"] else f"{D}·{R}"
            print(f"      {marker} {B}{item['text']}{R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 2: TIMELINE
# ════════════════════════════════════════════

def _view_timeline():
    subcommand_header(
        title="CAMPAIGN TIMELINE",
        symbol="◇",
        color=C.ACCENT,
        taglines=["4-phase track: Recon → Insider → Expansion → Win"],
        border="simple",
    )
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    cp = current_phase()

    # Phase track
    print(f"\n  {D}{'─' * 68}{R}")
    phase_display = []
    for p in PHASES:
        is_current = p["id"] == cp["id"]
        color = A if is_current else D
        bold = C.BOLD if is_current else ""
        marker = "▼" if is_current else " "
        phase_display.append((p, is_current, color, bold, marker))

    # Row 1: Phase names
    parts = []
    for p, is_current, color, bold, _ in phase_display:
        parts.append(f"{color}{bold}{p['code']:^14}{C.RESET}")
    print("  " + "".join(parts))

    # Row 2: Date ranges
    parts = []
    for p, _, color, _, _ in phase_display:
        date_str = f"{p['start'][5:]} - {p['end'][5:]}"
        parts.append(f"{D}{date_str:^14}{R}")
    print("  " + "".join(parts))

    # Row 3: Current marker
    parts = []
    for _, is_current, color, _, marker in phase_display:
        parts.append(f"{color}{marker:^14}{R}")
    print("  " + "".join(parts))

    # Progress bar for current phase
    prog = phase_progress()
    remaining = phase_days_remaining()
    print(f"\n  {phase_bar(cp['name'], prog)}" + (f"  {D}({remaining}d remaining){R}" if remaining else ""))

    # Milestones per phase
    for p in PHASES:
        is_current = p["id"] == cp["id"]
        color = A if is_current else D
        print(f"\n  {color}{C.BOLD}{p['name']}{R} {D}({p['start']} → {p['end']}){R}")

        # Find entities in this phase
        entities_in_phase = [(eid, data) for eid, data in NODE_DATA.items() if data.get("phase") == p["id"]]
        for eid, data in sorted(entities_in_phase, key=lambda x: x[1].get("priority", "low")):
            label = eid.replace("_", " ").title()
            deadline = data.get("deadline")
            dl_str = ""
            if deadline:
                dl = days_until(deadline)
                urg = urgency_level(deadline)
                dl_str = f"  {urgency_badge(urg)} {D}{deadline}{R}"
            print(f"    {status_dot(data['status'])} {priority_badge(data['priority']): <20} {B}{label}{R}{dl_str}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 3: DIRECTORY
# ════════════════════════════════════════════

def _view_directory():
    while True:
        subcommand_header(
            title="ENTITY DIRECTORY",
            symbol="◈",
            color=C.ACCENT,
            taglines=["All strategy entities with filtering"],
            border="simple",
        )
        A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

        print(f"\n  {A}Filter:{R}")
        print(menu_option("a", "All entities"))
        print(menu_option("s", "By status", "active/planned/pending/at-risk"))
        print(menu_option("d", "By domain", "startup/mcss/governance/ai_ml/academic"))
        print(menu_option("p", "By phase", "recon/insider/expansion/win"))
        print(menu_option("e", "Expand entity", "view details"))
        print(menu_option("q", "Back"))

        choice = prompt("directory> ")
        if choice in ("q", "b", "back"):
            return
        elif choice == "a":
            _print_entity_table(NODE_DATA)
        elif choice == "s":
            status = prompt("status (active/planned/pending/at-risk)> ")
            filtered = {k: v for k, v in NODE_DATA.items() if v.get("status") == status}
            _print_entity_table(filtered)
        elif choice == "d":
            domain = prompt("domain (startup/mcss/governance/ai_ml/academic)> ")
            filtered = {k: v for k, v in NODE_DATA.items() if domain in ENTITY_DOMAINS.get(k, [])}
            _print_entity_table(filtered)
        elif choice == "p":
            phase = prompt("phase (recon/insider/expansion/slate)> ")
            if phase == "win":
                phase = "slate"
            filtered = {k: v for k, v in NODE_DATA.items() if v.get("phase") == phase}
            _print_entity_table(filtered)
        elif choice == "e":
            entity_id = prompt("entity id> ").lower().replace(" ", "_")
            if entity_id in NODE_DATA:
                _print_entity_detail(entity_id, NODE_DATA[entity_id])
            else:
                print(f"  {C.DANGER}Entity not found.{C.RESET}")


def _print_entity_table(entities: dict):
    """Print entities as a compact table."""
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    # Sort by priority (critical first), then status
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_items = sorted(
        entities.items(),
        key=lambda x: (priority_order.get(x[1].get("priority", "low"), 4), x[1].get("status", "z")),
    )

    print(f"\n  {D}{'STATUS':<10} {'PRIORITY':<10} {'ENTITY':<24} {'PHASE':<10} {'DEADLINE':<12} {'ACTS':>4}{R}")
    print(f"  {D}{'─' * 72}{R}")
    for eid, data in sorted_items:
        label = eid.replace("_", " ").title()[:22]
        st = status_dot(data.get("status", "planned"))
        pr = data.get("priority", "low")
        pr_color = {"critical": C.DANGER, "high": C.SIGNAL, "medium": C.ACCENT, "low": C.DIM}.get(pr, C.DIM)
        phase = data.get("phase", "")[:8]
        deadline = data.get("deadline", "")[:10] if data.get("deadline") else "—"
        acts = len(data.get("actions", []))
        # Type icon
        etype = ENTITY_TYPE_MAP.get(eid, "")
        icon = ENTITY_TYPES.get(etype, {}).get("icon", " ")
        print(f"  {st} {data.get('status', 'planned'):<8} {pr_color}{pr:<10}{R} {icon} {B}{label:<22}{R} {D}{phase:<10} {deadline:<12} {acts:>4}{R}")

    print(f"\n  {D}{len(sorted_items)} entities{R}")
    prompt("[enter] back")


def _print_entity_detail(eid: str, data: dict):
    """Print detailed view of a single entity."""
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    label = eid.replace("_", " ").title()
    etype = ENTITY_TYPE_MAP.get(eid, "unknown")
    icon = ENTITY_TYPES.get(etype, {}).get("icon", " ")

    print(f"\n  {A}{C.BOLD}{icon} {label}{R}")
    print(f"  {D}Type: {etype}  |  Status: {data.get('status', '?')}  |  Priority: {data.get('priority', '?')}  |  Phase: {data.get('phase', '?')}{R}")

    if data.get("deadline"):
        dl = days_until(data["deadline"])
        urg = urgency_level(data["deadline"])
        print(f"  {D}Deadline: {data['deadline']}  ({dl}d)  {R}{urgency_badge(urg)}")

    # Domains
    domains = ENTITY_DOMAINS.get(eid, [])
    if domains:
        badges = " ".join(domain_badge(d) for d in domains)
        print(f"  {D}Domains:{R} {badges}")

    # Properties
    props = data.get("properties", {})
    if props:
        print(f"\n  {A}Properties{R}")
        for k, v in props.items():
            print(f"    {D}{k}:{R} {B}{v}{R}")

    # Actions
    actions = data.get("actions", [])
    if actions:
        print(f"\n  {A}Actions ({len(actions)}){R}")
        for i, action in enumerate(actions, 1):
            print(f"    {A}{i}.{R} {B}{action}{R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 4: MATRIX
# ════════════════════════════════════════════

def _view_matrix():
    subcommand_header(
        title="PRIORITY × STATUS MATRIX",
        symbol="⬡",
        color=C.ACCENT,
        taglines=["Entities mapped by priority and status"],
        border="simple",
    )
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    # Build the matrix
    statuses = ["active", "planned", "pending", "at-risk"]
    priorities = ["critical", "high", "medium", "low"]

    matrix: dict[str, dict[str, list[str]]] = {}
    for p in priorities:
        matrix[p] = {}
        for s in statuses:
            matrix[p][s] = []

    for eid, data in NODE_DATA.items():
        pr = data.get("priority", "low")
        st = data.get("status", "planned")
        if pr in priorities and st in statuses:
            label = eid.replace("_", " ").title()
            if len(label) > 16:
                label = label[:15] + "."
            matrix[pr][st].append(label)

    # Render
    col_w = 18
    # Header
    print(f"\n  {'PRIORITY':<12}", end="")
    for s in statuses:
        color = {"active": C.CONFIRM, "planned": C.ACCENT, "pending": C.SIGNAL, "at-risk": C.DANGER}.get(s, D)
        print(f" {color}{s.upper():^{col_w}}{R}", end="")
    print()
    print(f"  {'─' * 12}", end="")
    for _ in statuses:
        print(f" {'─' * col_w}", end="")
    print()

    for pr in priorities:
        pr_color = {"critical": C.DANGER, "high": C.SIGNAL, "medium": C.ACCENT, "low": C.DIM}.get(pr, D)
        # Find max rows in this priority
        max_rows = max(len(matrix[pr][s]) for s in statuses) if any(matrix[pr][s] for s in statuses) else 1
        for row_i in range(max(1, max_rows)):
            if row_i == 0:
                print(f"  {pr_color}{C.BOLD}{pr:<12}{R}", end="")
            else:
                print(f"  {'':12}", end="")
            for s in statuses:
                items = matrix[pr][s]
                if row_i < len(items):
                    print(f" {B}{items[row_i]:<{col_w}}{R}", end="")
                else:
                    print(f" {'':>{col_w}}", end="")
            print()
        if max_rows > 0:
            print()

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 5: COMMAND (Org Hierarchy)
# ════════════════════════════════════════════

def _view_command():
    subcommand_header(
        title="ORGANIZATIONAL HIERARCHY",
        symbol="◆",
        color=C.ACCENT,
        taglines=["Ericsson's positions and organizational structure"],
        border="simple",
    )
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    # Render tree
    tree = [
        (0, f"{A}{C.BOLD}Ericsson Cui{R}  {D}— Strategy Hub{R}"),
        (1, f"{C.INTEL}Pyko Canada Ltd.{R}  {D}Director + Software Engineer{R}"),
        (2, f"{C.INTEL}Pyko Lab{R}  {D}Founding Researcher (nonprofit parent){R}"),
        (2, f"{C.INTEL}Ambassador Program{R}  {D}Mekayel leads campus ops{R}"),
        (2, f"{C.INTEL}Pyko Learning Society{R}  {D}President — SOP registration May-Jul{R}"),
        (1, f"{C.ACCENT}MCSS{R}  {D}Target: President Feb 2027{R}"),
        (2, f"{C.ACCENT}MCSS Slate{R}  {D}5 positions{R}"),
        (3, f'{D}VP Internal  "The Insider" — female MCSS veteran{R}'),
        (3, f'{D}VP Finance  "Math/Stats Rep" — broadens coalition{R}'),
        (3, f'{D}VP External  "Technical Credibility"{R}'),
        (3, f'{D}VP Marketing  "Discord Celebrity"{R}'),
        (2, f"{C.ACCENT}DeerHacks{R}  {D}UTM's largest hackathon — president oversees{R}"),
        (1, f"{C.CONFIRM}Governance{R}"),
        (2, f"{C.CONFIRM}Campus Council / Academic Affairs{R}  {D}Results Apr 10{R}"),
        (2, f"{C.CONFIRM}Campus Affairs Committee{R}  {D}6 undergrad seats{R}"),
        (2, f"{C.CONFIRM}UTMSU Committees{R}  {D}Elections & Referenda target{R}"),
        (1, f"{C.SIGNAL}UTMIST{R}  {D}ML Developer + FYR — apply Sep 2026{R}"),
        (1, f"{D}UTMAC{R}  {D}Athletic Council member (via Mekayel + Raaid){R}"),
        (1, f"{C.WARM}Vector Institute{R}  {D}Research Intern — Summer 2028{R}"),
    ]

    for depth, text in tree:
        if depth == 0:
            prefix = ""
        elif depth == 1:
            prefix = "├── "
        elif depth == 2:
            prefix = "│   ├── "
        else:
            prefix = "│   │   ├── "
        print(f"  {D}{prefix}{R}{text}")

    # Key people
    print(f"\n  {A}{C.BOLD}KEY PEOPLE{R}")
    people = [
        ("Mekayel Omier", "Pyko Ambassador + Political Ally", "at-risk"),
        ("Ethan Koo", "Pyko CEO + Campaign Website Builder", "active"),
        ("Raaid Shabeer", "UTMAC Member + CS/Math/Stats", "active"),
        ("Emily Su", "MCSS President 2026-27 — INCUMBENT THREAT", "at-risk"),
        ("Saurabh Nair", "Outgoing MCSS President 2025-26", "active"),
        ("Lisa Zhang", "CS Faculty — MCSS Advisor, teaches CSC311/413", "active"),
    ]
    for name, role, status in people:
        print(f"    {status_dot(status)} {B}{name}{R}  {D}{role}{R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 6: ACADEMICS
# ════════════════════════════════════════════

def _view_academics():
    subcommand_header(
        title="ACADEMIC PIPELINE",
        symbol="◇",
        color=C.CYAN,
        taglines=["Course roadmap, GPA tracking, Vector Institute pathway"],
        border="simple",
    )
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    courses_data = NODE_DATA.get("courses", {})
    gpa = 3.50
    target = 3.70

    # GPA gauge
    print(f"\n  {C.CYAN}{C.BOLD}GPA PROGRESS{R}")
    pct = gpa / 4.0
    print(f"  {horizontal_bar(pct, 30, C.CYAN)}  {B}{gpa:.2f}{R} / 4.00  {D}(target: {target:.2f}){R}")

    # Program
    print(f"\n  {B}Path: CS Specialist + PHL Minor + Math Minor{R}")

    # Course pipeline
    print(f"\n  {C.CYAN}{C.BOLD}COURSE PIPELINE{R}")
    pipeline = [
        ("COMPLETED", [
            ("CSC108", "Intro to CS"),
            ("CSC148", "Intro to CS II"),
            ("MAT102", "Intro to Proofs"),
            ("MAT223", "Linear Algebra I"),
            ("STA107", "Intro to Probability"),
        ]),
        ("SUMMER 2026", [
            ("CSC207", "Software Design"),
            ("CSC236", "Theory of Computation"),
        ]),
        ("YEAR 2 (2026-27)", [
            ("CSC263", "Data Structures & Analysis"),
            ("CSC258", "Computer Organization"),
            ("MAT224", "Linear Algebra II"),
            ("STA256", "Probability & Statistics I"),
        ]),
        ("YEAR 3 (2027-28)", [
            ("CSC311", "Machine Learning — Lisa Zhang"),
            ("CSC413", "Deep Learning — Lisa Zhang"),
        ]),
    ]

    for period, courses in pipeline:
        color = C.CONFIRM if period == "COMPLETED" else (C.SIGNAL if "2026" in period else C.ACCENT)
        print(f"\n    {color}{C.BOLD}{period}{R}")
        for code, name in courses:
            marker = f"{C.CONFIRM}✓{R}" if period == "COMPLETED" else f"{D}○{R}"
            print(f"      {marker} {B}{code}{R}  {D}{name}{R}")

    # Vector roadmap
    print(f"\n  {C.SIGNAL}{C.BOLD}VECTOR INSTITUTE ROADMAP{R}")
    steps = [
        ("1", "UTMIST ML Developer", "Sep 2026", "planned"),
        ("2", "CSC311 Machine Learning", "2027-28", "planned"),
        ("3", "CSC413 Deep Learning", "2027-28", "planned"),
        ("4", "ML Project Portfolio", "Ongoing", "active"),
        ("5", "Vector Application", "Feb 2028", "planned"),
    ]
    for num, step, date_str, status in steps:
        print(f"    {status_dot(status)} {D}{num}.{R} {B}{step}{R}  {D}({date_str}){R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 7: INTEL
# ════════════════════════════════════════════

def _view_intel():
    while True:
        subcommand_header(
            title="INTELLIGENCE",
            symbol="◉",
            color=C.SIGNAL,
            taglines=["Election data, threats, external network"],
            border="simple",
        )
        print(menu_option("1", "Threat Assessment", "Emily Su + competitors"))
        print(menu_option("2", "UTMSU Slate History", "5 years of election data"))
        print(menu_option("3", "IgniteUTM Results", "2026-27 detailed results"))
        print(menu_option("4", "External Network", "Contacts outside UTM"))
        print(menu_option("5", "Slate Archetypes", "5 positions + recruitment"))
        print(menu_option("q", "Back"))

        choice = prompt("intel> ")
        if choice in ("q", "b", "back"):
            return
        elif choice == "1":
            _intel_threat()
        elif choice == "2":
            _intel_slate_history()
        elif choice == "3":
            _intel_igniteutm()
        elif choice == "4":
            _intel_external()
        elif choice == "5":
            _intel_archetypes()


def _intel_threat():
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    comp = NODE_DATA.get("competitors", {})

    print(f"\n  {C.DANGER}{C.BOLD}THREAT ASSESSMENT{R}")
    print(f"\n  {C.DANGER}█{R} {B}{C.BOLD}Emily Su{R}  {D}— MCSS President 2026-27 (INCUMBENT){R}")
    print(f"    {D}Events Associate (2024-25) → VP Internal (2025-26) → President (2026-27, unopposed){R}")
    print(f"    {D}2x Hackathon Winner, 3.85 GPA, Dean's List x2{R}")
    print(f"    {C.SIGNAL}KEY QUESTION: Does she seek re-election for 2027-28?{R}")

    print(f"\n  {A}{C.BOLD}2026-27 MCSS ELECTION RESULTS{R}")
    results = [
        ("President", "Emily Su", "UNOPPOSED"),
        ("VP Internal", "Carol Wang vs Kaiden Rai", "CONTESTED"),
        ("VP External", "Ryan C. Hui", "UNOPPOSED"),
        ("VP Marketing", "Elif Yasar vs Pragya Chaturvedi", "CONTESTED"),
        ("VP Finance", "NO CANDIDATES", "VACANT"),
    ]
    for pos, winner, status in results:
        color = C.DANGER if status == "VACANT" else (C.SIGNAL if status == "CONTESTED" else C.CONFIRM)
        print(f"    {color}●{R} {D}{pos:<14}{R} {B}{winner}{R}  {color}({status}){R}")

    print(f"\n  {C.SIGNAL}VP Finance vacancy validates 'Math/Stats students are underserved' thesis.{R}")

    prompt("[enter] back")


def _intel_slate_history():
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    print(f"\n  {A}{C.BOLD}UTMSU SLATE HISTORY (5 YEARS){R}")
    print(f"\n  {D}{'YEAR':<10} {'SLATE':<16} {'PRESIDENT':<22} {'VOTES':>6} {'MARGIN':>8} {'OPPOSITION'}{R}")
    print(f"  {D}{'─' * 80}{R}")
    for row in SLATE_HISTORY:
        votes_str = str(row["votes"]) if row["votes"] else "—"
        print(f"  {B}{row['year']:<10}{R} {A}{row['slate']:<16}{R} {B}{row['president']:<22}{R} {B}{votes_str:>6}{R} {C.CONFIRM}{row['margin']:>8}{R} {D}{row['opposition']}{R}")

    print(f"\n  {D}Pattern: Organized slates win decisively. Independents never win.{R}")
    prompt("[enter] back")


def _intel_igniteutm():
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    results = IGNITEUTM_RESULTS

    print(f"\n  {A}{C.BOLD}IGNITEUTM 2026-27 EXECUTIVE RESULTS{R}")
    print(f"  {D}Turnout: {results['turnout']} / {results['eligible']} ({results['turnout_pct']}%){R}")
    print(f"  {D}Average margin: {results['avg_margin']}%{R}")

    print(f"\n  {D}{'POSITION':<18} {'WINNER':<20} {'VOTES':>6} {'RUNNER-UP':<22} {'%':>5}{R}")
    print(f"  {D}{'─' * 76}{R}")
    for r in results["executive"]:
        print(f"  {B}{r['position']:<18}{R} {A}{r['winner']:<20}{R} {B}{r['votes']:>6}{R} {D}{r['runner_up']:<22}{R} {C.CONFIRM}{r['pct']:>5.1f}{R}")

    print(f"\n  {A}{C.BOLD}SLATE PROFILES{R}")
    for s in results["slate"]:
        print(f"    {B}{s['name']}{R} ({D}{s['position']}, {s['year']}, {s['program']}{R})")
        print(f"      {D}Prior: {s['prior_role']}  |  Orgs: {s['org_ties']}{R}")

    prompt("[enter] back")


def _intel_external():
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    print(f"\n  {A}{C.BOLD}EXTERNAL NETWORK{R}")
    for contact in EXTERNAL_NETWORK:
        st = status_dot(contact["status"])
        dom = domain_badge(contact["domain"])
        print(f"\n    {st} {B}{contact['name']}{R}  {dom}")
        print(f"      {D}{contact['role']}{R}")
        print(f"      {C.DIM}→ {contact['action']}{R}")

    prompt("[enter] back")


def _intel_archetypes():
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET

    archetypes = [
        ("PRESIDENT", '"The Face"', "Ericsson Cui", "Campaign infrastructure, Pyko credibility, GC name recognition"),
        ("VP INTERNAL", '"The Insider"', "Target: Female MCSS veteran", "Neutralizes 'outsider' critique. Source: WiSC members"),
        ("VP FINANCE", '"Math/Stats Rep"', "Target: Math or Stats major", "Unlocks 300-500 underserved voters. Source: Math Club"),
        ("VP EXTERNAL", '"Technical Credibility"', "Target: Co-op / hackathon winner", "Makes 'better sponsors' credible. Source: DeerHacks"),
        ("VP MARKETING", '"Discord Celebrity"', "Target: Known in 3+ MCS servers", "One post = 30-50 votes. Highest-impact recruit"),
    ]

    print(f"\n  {A}{C.BOLD}MCSS SLATE — 5 ARCHETYPES{R}")
    print(f"  {D}Gender target: 3 women, 2 men{R}")
    print(f"  {D}Recruit: Sep-Nov 2026 → Coffee chats Dec → Lock Jan 2027{R}")

    for pos, codename, target, desc in archetypes:
        print(f"\n    {C.DANGER}{C.BOLD}{pos}{R}  {A}{codename}{R}")
        print(f"      {B}{target}{R}")
        print(f"      {D}{desc}{R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# VIEW 8 & 9: GRAPH + MAP (Textual TUI)
# ════════════════════════════════════════════

def _view_graph():
    try:
        from cli.commands.strategy_graph import run_strategy_graph
        spinner("Launching interactive graph...", 0.5)
        run_strategy_graph()
    except ImportError:
        print(f"\n  {C.SIGNAL}Interactive graph requires optional dependencies:{C.RESET}")
        print(f"  {C.BASE}pip install textual netext networkx{C.RESET}")
        print(f"\n  {C.DIM}Showing static summary instead:{C.RESET}")
        _graph_static_fallback()


def _view_map():
    from cli.commands.strategy_map import run_strategy_map
    run_strategy_map()


def _graph_static_fallback():
    """Static fallback: show top nodes and edge summary."""
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    try:
        from cli.strategy.analytics import top_nodes, node_connections
        print(f"\n  {A}{C.BOLD}TOP ENTITIES BY INFLUENCE{R}")
        for nid, score in top_nodes("hub", 15):
            label = nid.replace("_", " ").title()
            group = ""
            for n in GRAPH_NODES:
                if n["id"] == nid:
                    group = GROUP_LABELS.get(n["group"], "")
                    break
            print(f"    {horizontal_bar(score, 20, C.ACCENT)}  {B}{label:<24}{R} {D}{group}{R}")

        print(f"\n  {A}{C.BOLD}ERICSSON'S CONNECTIONS{R}")
        for conn in node_connections("ericsson"):
            neighbor_label = conn["neighbor"].replace("_", " ").title()
            print(f"    {A}→{R} {B}{neighbor_label}{R}  {D}{conn['label']}{R}")
    except ImportError:
        print(f"  {D}Install networkx for analytics: pip install networkx{R}")
        print(f"\n  {A}{C.BOLD}GRAPH SUMMARY{R}")
        print(f"  {B}{len(GRAPH_NODES)} nodes, {len([e for e in __import__('cli.strategy.data', fromlist=['GRAPH_EDGES']).GRAPH_EDGES])} edges{R}")

    prompt("[enter] back")


def _map_static_fallback():
    """Static fallback: show location table."""
    A, B, D, R = C.ACCENT, C.BASE, C.DIM, C.RESET
    cp = current_phase()

    print(f"\n  {A}{C.BOLD}CAMPUS LOCATIONS{R}")
    print(f"  {D}Phase: {cp['name']}{R}\n")

    loc_type_colors = {
        "governance": C.CONFIRM,
        "academic": C.CYAN,
        "startup": C.INTEL,
        "event": C.SIGNAL,
        "social": C.WARM,
    }

    # Current phase relevance
    relevance = PHASE_LOCATION_RELEVANCE.get(cp["id"], {})

    for loc_id, loc in LOCATIONS.items():
        color = loc_type_colors.get(loc["type"], D)
        rel = relevance.get(loc_id, "")
        print(f"    {color}●{R} {B}{loc['name']}{R}  {D}({loc['building']}){R}")
        print(f"      {D}{loc['description']}{R}")
        if rel:
            print(f"      {A}→ {rel}{R}")

    print(f"\n  {A}{C.BOLD}KEY PEOPLE ON CAMPUS{R}")
    for pid, p in PEOPLE_LOCATIONS.items():
        print(f"    {C.INTEL}@{R} {B}{p['name']}{R} ({p['initials']})  {D}{p['role']}{R}")

    prompt("[enter] back")


# ════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════

def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=width)
