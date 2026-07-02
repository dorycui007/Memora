"""Watchlist command — people intelligence monitor."""

from __future__ import annotations

from datetime import datetime, timezone

from cli.rendering import (
    C, horizontal_bar, menu_option, prompt, spinner,
    subcommand_header, watchlist_header,
)


def cmd_watchlist(app):
    """Watchlist intelligence sub-menu."""
    while True:
        watchlist_header()
        print(menu_option("1", "Dashboard", "Tracked people + scan status"))
        print(menu_option("2", "Scan now", "Run watchlist scan immediately"))
        print(menu_option("3", "Alerts", "Recent professional changes"))
        print(menu_option("4", "Person detail", "Scan history for one person"))
        print()

        choice = prompt("watchlist> ")
        if choice in ("b", "back", "q"):
            return
        elif choice == "1":
            _dashboard_view(app)
        elif choice == "2":
            _scan_now(app)
        elif choice == "3":
            _alerts_view(app)
        elif choice == "4":
            _person_detail(app)


# -- Dashboard ---------------------------------------------------------------

def _dashboard_view(app):
    """Show all tracked people with tier, scan status, role, org."""
    if not app.repo:
        print(f"  {C.RED}Graph not available.{C.RESET}")
        return

    from memora.graph.models import parse_properties
    from memora.core.watchlist import classify_relationship, SCAN_INTERVALS

    rows = app.repo.get_person_nodes()
    people = []
    for row in rows:
        props = parse_properties(row.get("properties"))
        row["properties"] = props
        people.append(row)

    if not people:
        print(f"\n  {C.DIM}No people in graph.{C.RESET}\n")
        prompt("Press Enter to continue...")
        return

    subcommand_header("DASHBOARD", symbol="@", color=C.CYAN, border="simple")

    # Column header
    print(f"  {C.DIM}{'#':>3}  {'Name':<22} {'Tier':<13} {'Role':<16} "
          f"{'Org':<14} {'Last Scan':<12} {'Status'}{C.RESET}")
    print(f"  {C.DIM}{'─' * 90}{C.RESET}")

    due_count = 0
    never_count = 0

    for i, person in enumerate(people, 1):
        props = person["properties"]
        name = person.get("title", "?")[:20]
        tier = classify_relationship(props)
        role = str(props.get("role", ""))[:14]
        org = str(props.get("organization", ""))[:12]
        last_scan = props.get("watchlist_last_scan")

        if last_scan:
            try:
                last_dt = datetime.fromisoformat(str(last_scan))
                days_ago = (datetime.now(timezone.utc) - last_dt).days
                scan_str = f"{days_ago}d ago"
                interval = SCAN_INTERVALS.get(tier, 30)
                if days_ago >= interval:
                    status = f"{C.SIGNAL}due{C.RESET}"
                    due_count += 1
                else:
                    status = f"{C.GREEN}ok{C.RESET}"
            except (ValueError, TypeError):
                scan_str = "invalid"
                status = f"{C.RED}never{C.RESET}"
                never_count += 1
        else:
            scan_str = "--"
            status = f"{C.RED}never{C.RESET}"
            never_count += 1

        tier_color = {"close": C.GREEN, "regular": C.YELLOW}.get(tier, C.DIM)
        print(f"  {C.BOLD}{i:>3}.{C.RESET} {name:<22} "
              f"{tier_color}{tier:<13}{C.RESET} "
              f"{C.DIM}{role:<16}{C.RESET} "
              f"{C.DIM}{org:<14}{C.RESET} "
              f"{C.DIM}{scan_str:<12}{C.RESET} "
              f"{status}")

    print(f"\n  {C.DIM}Total: {len(people)}  |  "
          f"Due: {due_count}  |  Never scanned: {never_count}{C.RESET}\n")
    prompt("Press Enter to continue...")


# -- Scan Now -----------------------------------------------------------------

def _scan_now(app):
    """Manually trigger a watchlist scan."""
    if not app.repo:
        print(f"  {C.RED}Graph not available.{C.RESET}")
        return

    spinner("Initializing watchlist scanner", 0.3)

    try:
        from memora.core.watchlist import WatchlistScanner

        # Attempt to set up search tools (graceful fallback)
        search_tool = None
        scraper = None
        try:
            from memora.mcp.google_search import GoogleSearchMCP
            from memora.mcp.brave_search import BraveSearchMCP
            google = GoogleSearchMCP()
            brave = BraveSearchMCP()
            search_tool = google if google.available else brave
        except Exception:
            pass

        try:
            from memora.mcp.playwright_scraper import PlaywrightScraperMCP
            scraper = PlaywrightScraperMCP()
        except Exception:
            pass

        if not search_tool:
            print(f"\n  {C.SIGNAL}No search API keys configured.{C.RESET}")
            print(f"  {C.DIM}Set GOOGLE_SEARCH_API_KEY or BRAVE_SEARCH_API_KEY in .env{C.RESET}\n")
            prompt("Press Enter to continue...")
            return

        # Truth layer (optional)
        truth_layer = None
        try:
            from memora.core.truth_layer import TruthLayer
            truth_layer = TruthLayer(app.repo.get_truth_layer_conn())
        except Exception:
            pass

        scanner = WatchlistScanner(
            repo=app.repo,
            truth_layer=truth_layer,
            search_tool=search_tool,
            scraper=scraper,
        )

        spinner("Scanning for professional changes", 1.0)
        changes = scanner.scan()

        if not changes:
            print(f"\n  {C.GREEN}No changes detected.{C.RESET}\n")
        else:
            print(f"\n  {C.BOLD}{len(changes)} change(s) detected:{C.RESET}\n")
            for ch in changes:
                ct = ch.get("change_type", "unknown")
                name = ch.get("person_name", "?")
                old = ch.get("old_value", "")
                new = ch.get("new_value", "")
                url = ch.get("source_url", "")

                type_color = {"role_change": C.SIGNAL, "company_change": C.CYAN}.get(ct, C.DIM)
                print(f"  {type_color}[{ct}]{C.RESET} {C.BOLD}{name}{C.RESET}")
                if old:
                    print(f"    {C.DIM}{old}{C.RESET} -> {C.BASE}{new}{C.RESET}")
                else:
                    print(f"    {C.BASE}{new}{C.RESET}")
                if url:
                    print(f"    {C.DIM}{url}{C.RESET}")
                print()

            # Create notifications for changes
            try:
                from memora.core.notifications import NotificationManager, WATCHLIST_ALERT
                nm = NotificationManager(app.repo.get_truth_layer_conn())
                for ch in changes:
                    nm.create_notification(
                        type=WATCHLIST_ALERT,
                        message=ch.get("message", ""),
                        related_node_ids=[ch["node_id"]] if ch.get("node_id") else [],
                        priority="high",
                    )
            except Exception:
                pass

    except Exception as e:
        print(f"\n  {C.RED}Scan failed: {e}{C.RESET}\n")

    prompt("Press Enter to continue...")


# -- Alerts -------------------------------------------------------------------

def _alerts_view(app):
    """Show recent watchlist alert notifications."""
    if not app.repo:
        print(f"  {C.RED}Graph not available.{C.RESET}")
        return

    subcommand_header("WATCHLIST ALERTS", symbol="!", color=C.SIGNAL, border="simple")

    try:
        from memora.core.notifications import NotificationManager, WATCHLIST_ALERT
        nm = NotificationManager(app.repo.get_truth_layer_conn())
        alerts = nm.get_notifications(type=WATCHLIST_ALERT, limit=20)
    except Exception as e:
        print(f"  {C.RED}Could not load alerts: {e}{C.RESET}\n")
        prompt("Press Enter to continue...")
        return

    if not alerts:
        print(f"  {C.DIM}No watchlist alerts.{C.RESET}\n")
        prompt("Press Enter to continue...")
        return

    for alert in alerts:
        ts = alert.get("created_at", "")[:16]
        msg = alert.get("message", "")
        priority = alert.get("priority", "medium")
        is_read = alert.get("read", False)

        priority_badge = {
            "critical": f"{C.RED}CRIT{C.RESET}",
            "high": f"{C.SIGNAL}HIGH{C.RESET}",
            "medium": f"{C.DIM}MED{C.RESET}",
            "low": f"{C.DIM}LOW{C.RESET}",
        }.get(priority, f"{C.DIM}{priority}{C.RESET}")

        read_marker = f"{C.DIM}(read){C.RESET}" if is_read else ""
        print(f"  {C.DIM}{ts}{C.RESET}  {priority_badge}  {msg}  {read_marker}")

    print()
    prompt("Press Enter to continue...")


# -- Person Detail ------------------------------------------------------------

def _person_detail(app):
    """Show watchlist detail for a single person."""
    if not app.repo:
        print(f"  {C.RED}Graph not available.{C.RESET}")
        return

    from cli.commands.people import _search_person
    person_id = _search_person(app, "Person name")
    if not person_id:
        return

    from uuid import UUID
    from memora.graph.models import parse_properties
    from memora.core.watchlist import classify_relationship, SCAN_INTERVALS

    node = app.repo.get_node(UUID(person_id))
    if not node:
        print(f"  {C.RED}Person not found.{C.RESET}")
        return

    props = {}
    if node.properties:
        props = node.properties if isinstance(node.properties, dict) else parse_properties(node.properties)

    name = node.title
    tier = classify_relationship(props)
    role = props.get("role", "")
    org = props.get("organization", "")
    interval = SCAN_INTERVALS.get(tier, 30)
    last_scan = props.get("watchlist_last_scan", "")

    subcommand_header(name, symbol="@", color=C.CYAN, border="simple")

    print(f"    {C.DIM}Role:{C.RESET}          {C.BASE}{role or '—'}{C.RESET}")
    print(f"    {C.DIM}Organization:{C.RESET}   {C.BASE}{org or '—'}{C.RESET}")
    print(f"    {C.DIM}Tier:{C.RESET}          {C.BASE}{tier}{C.RESET}")
    print(f"    {C.DIM}Scan interval:{C.RESET}  {C.BASE}every {interval} days{C.RESET}")
    print(f"    {C.DIM}Last scan:{C.RESET}      {C.BASE}{last_scan or 'never'}{C.RESET}")

    # Show watchlist facts from truth layer if available
    try:
        from memora.core.truth_layer import TruthLayer
        truth_layer = TruthLayer(app.repo.get_truth_layer_conn())
        facts = truth_layer.query_facts(person_id)
        watchlist_facts = [f for f in facts if f.get("verified_by") == "watchlist"]
        if watchlist_facts:
            print(f"\n    {C.BOLD}WATCHLIST FACTS ({len(watchlist_facts)}){C.RESET}")
            print(f"    {C.DIM}{'─' * 50}{C.RESET}")
            for fact in watchlist_facts:
                stmt = fact.get("statement", "")
                conf = fact.get("confidence", 0)
                print(f"    {horizontal_bar(conf, 8)} {stmt}")
    except Exception:
        pass

    print()
    prompt("Press Enter to continue...")
