"""Patterns command — display detected behavioral patterns."""

from __future__ import annotations

from cli.rendering import C, divider, horizontal_bar, menu_option, prompt, subcommand_header


def cmd_patterns(app):
    """View and trigger pattern detection."""
    while True:
        subcommand_header(
            title="PATTERNS",
            symbol="▣",
            color=C.ACCENT,
            taglines=["Behavioral pattern detection · Trend analysis"],
            border="simple",
        )
        print(menu_option("1", "View patterns",   "Show detected patterns"))
        print(menu_option("2", "Run detection",   "Trigger pattern analysis now"))
        print()

        choice = prompt("patterns> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _view_patterns(app)
        elif choice == "2":
            _run_detection(app)


_TYPE_ICONS = {
    "commitment_pattern": f"{C.RED}!{C.RESET}",
    "goal_lifecycle": f"{C.MAGENTA}>{C.RESET}",
    "temporal_pattern": f"{C.YELLOW}*{C.RESET}",
    "cross_network": f"{C.CYAN}~{C.RESET}",
    "relationship_pattern": f"{C.GREEN}@{C.RESET}",
    "decision_quality": f"{C.YELLOW}?{C.RESET}",
    "goal_alignment": f"{C.MAGENTA}={C.RESET}",
    "commitment_scope": f"{C.RED}#{C.RESET}",
    "idea_maturity": f"{C.CYAN}~{C.RESET}",
    "network_balance": f"{C.GREEN}%{C.RESET}",
    "outcome_pattern": f"{C.YELLOW}${C.RESET}",
}

_SEVERITY_COLORS = {
    "critical": C.RED,
    "warning": C.YELLOW,
    "info": C.DIM,
}


def _view_patterns(app):
    """Display stored patterns grouped by type."""
    patterns = app.repo.get_patterns(limit=50)

    if not patterns:
        print(f"\n  {C.DIM}No patterns detected yet. Try running detection first.{C.RESET}")
        return

    # Group by type
    by_type: dict[str, list] = {}
    for p in patterns:
        pt = p.get("pattern_type", "unknown")
        by_type.setdefault(pt, []).append(p)

    print(f"\n  {C.BOLD}Detected Patterns ({len(patterns)}):{C.RESET}")

    for ptype, items in by_type.items():
        icon = _TYPE_ICONS.get(ptype, " ")
        print(f"\n  {icon} {C.BOLD}{ptype.replace('_', ' ').title()}{C.RESET}")
        print(f"  {C.DIM}{'─' * 50}{C.RESET}")

        for p in items:
            conf = p.get("confidence", 0)
            desc = p.get("description", "")
            action = p.get("suggested_action", "")
            networks = p.get("networks", [])
            severity = p.get("severity", "info")

            sev_color = _SEVERITY_COLORS.get(severity, C.DIM)
            sev_label = severity.upper() if severity != "info" else ""

            conf_bar = horizontal_bar(conf, width=10, color=C.CYAN)
            sev_prefix = f"{sev_color}[{sev_label}]{C.RESET} " if sev_label else ""
            print(f"    {conf_bar}  {sev_prefix}{desc}")

            if networks:
                net_str = ", ".join(networks)
                print(f"              {C.DIM}Networks: {net_str}{C.RESET}")

            if action:
                print(f"              {C.GREEN}→ {action}{C.RESET}")


def _run_detection(app):
    """Trigger on-demand pattern detection."""
    from memora.core.patterns import PatternEngine

    print(f"\n  {C.DIM}Running pattern detection...{C.RESET}")
    engine = PatternEngine(app.repo)
    patterns = engine.detect_all()

    if not patterns:
        print(f"  {C.DIM}No patterns detected yet. Your graph needs more data:{C.RESET}\n")
        diag = engine.diagnose()
        for item in diag.get("missing", []):
            print(f"    {C.RED}\u2717{C.RESET} {item}")
        for item in diag.get("satisfied", []):
            print(f"    {C.GREEN}\u2713{C.RESET} {C.DIM}{item}{C.RESET}")
        print()
        return

    stored = engine.store_patterns(patterns)
    print(f"  {C.GREEN}Detected {len(patterns)} pattern(s), stored {stored}{C.RESET}\n")

    for p in patterns:
        conf = p.get("confidence", 0)
        severity = p.get("severity", "info")
        sev_color = _SEVERITY_COLORS.get(severity, C.DIM)
        sev_tag = f" {sev_color}[{severity.upper()}]{C.RESET}" if severity != "info" else ""
        print(f"    {C.CYAN}●{C.RESET} [{conf:.0%}]{sev_tag} {p['description']}")
        if p.get("suggested_action"):
            print(f"      {C.GREEN}→ {p['suggested_action']}{C.RESET}")
