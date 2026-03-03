"""Connectors command — manage data source connectors.

Provides list, add, sync, sync-all, status, and remove operations.
"""

from __future__ import annotations

from cli.rendering import (
    C,
    connectors_header, divider, horizontal_bar, menu_option, prompt, subcommand_header,
)


def cmd_connectors(app):
    """Connector management CLI."""
    connectors_header()

    from memora.connectors.base import get_default_registry

    registry = get_default_registry()

    # Load saved connectors from config
    connectors_config = getattr(app.settings, "connectors", {}) or {}
    for name, cfg in connectors_config.items():
        ctype = cfg.get("type", "")
        if ctype and not registry.get(name):
            try:
                registry.create(name, ctype, cfg.get("config", {}))
            except ValueError:
                pass

    while True:
        print(f"\n  {C.BOLD}Connector Management:{C.RESET}")
        print(menu_option("1", "List connectors",   "Show all configured sources"))
        print(menu_option("2", "Add connector",     "Connect a new data source"))
        print(menu_option("3", "Sync connector",    "Pull latest from one source"))
        print(menu_option("4", "Sync all",          "Pull latest from all sources"))
        print(menu_option("5", "Status",            "View sync health and errors"))
        print(menu_option("6", "Remove connector",  "Disconnect a data source"))
        print(menu_option("q", "Back",              ""))

        choice = prompt("connectors> ").strip()
        if choice in ("q", "quit", ""):
            break
        elif choice == "1":
            _list_connectors(registry)
        elif choice == "2":
            _add_connector(app, registry)
        elif choice == "3":
            _sync_connector(app, registry)
        elif choice == "4":
            _sync_all(app, registry)
        elif choice == "5":
            _status(app, registry)
        elif choice == "6":
            _remove_connector(registry)
        else:
            print(f"  {C.DIM}Invalid option.{C.RESET}")


def _list_connectors(registry):
    """List registered connector types and instances."""
    print(f"\n{divider('─', C.WARM)}")
    print(f"  {C.BOLD}{C.WARM}CONNECTOR TYPES{C.RESET}")
    print(divider())

    types = registry.get_types()
    if types:
        for name, cls in types.items():
            print(f"    {C.WARM}>{C.RESET} {C.BOLD}{name}{C.RESET}  {C.DIM}{cls.__doc__.strip().split(chr(10))[0] if cls.__doc__ else ''}{C.RESET}")
    else:
        print(f"    {C.DIM}No connector types available.{C.RESET}")
        print(f"    {C.DIM}Install optional deps: pip install icalendar python-frontmatter{C.RESET}")

    instances = registry.list_instances()
    print(f"\n  {C.BOLD}{C.WARM}ACTIVE INSTANCES ({len(instances)}){C.RESET}")
    if instances:
        for name, connector in instances.items():
            print(f"    {C.CONFIRM}●{C.RESET} {C.BOLD}{name}{C.RESET}  "
                  f"{C.DIM}type={connector.connector_type}{C.RESET}")
    else:
        print(f"    {C.DIM}No connectors configured. Use 'Add' to create one.{C.RESET}")


def _add_connector(app, registry):
    """Add a new connector instance."""
    types = registry.get_types()
    if not types:
        print(f"\n  {C.SIGNAL}No connector types available. Install optional dependencies.{C.RESET}")
        return

    print(f"\n  {C.BOLD}Available types:{C.RESET}")
    type_list = list(types.keys())
    for i, t in enumerate(type_list, 1):
        print(f"    {i}. {t}")

    choice = prompt(f"  Select type [1-{len(type_list)}]: ").strip()
    try:
        idx = int(choice) - 1
        connector_type = type_list[idx]
    except (ValueError, IndexError):
        print(f"  {C.DIM}Invalid selection.{C.RESET}")
        return

    name = prompt("  Connector name: ").strip()
    if not name:
        print(f"  {C.DIM}Name required.{C.RESET}")
        return

    if registry.get(name):
        print(f"  {C.SIGNAL}Connector '{name}' already exists.{C.RESET}")
        return

    # Collect config based on type
    config = {}
    if connector_type == "calendar":
        path = prompt("  Path to .ics file or directory: ").strip()
        if path:
            config["path"] = path
    elif connector_type == "markdown":
        path = prompt("  Path to markdown directory: ").strip()
        if path:
            config["path"] = path
        exclude = prompt(f"  Exclude dirs {C.DIM}(comma-separated, default: .obsidian,.trash){C.RESET}: ").strip()
        if exclude:
            config["exclude_dirs"] = [d.strip() for d in exclude.split(",")]

    try:
        connector = registry.create(name, connector_type, config)
        errors = connector.validate_config()
        if errors:
            print(f"\n  {C.SIGNAL}Configuration errors:{C.RESET}")
            for err in errors:
                print(f"    - {err}")
            registry.remove(name)
            return

        print(f"\n  {C.CONFIRM}Connector '{name}' created ({connector_type}).{C.RESET}")

    except ValueError as e:
        print(f"\n  {C.DANGER}{e}{C.RESET}")


def _sync_connector(app, registry):
    """Sync a specific connector."""
    instances = registry.list_instances()
    if not instances:
        print(f"\n  {C.DIM}No connectors configured.{C.RESET}")
        return

    print(f"\n  {C.BOLD}Active connectors:{C.RESET}")
    names = list(instances.keys())
    for i, name in enumerate(names, 1):
        print(f"    {i}. {name} ({instances[name].connector_type})")

    choice = prompt(f"  Select [1-{len(names)}]: ").strip()
    try:
        idx = int(choice) - 1
        name = names[idx]
    except (ValueError, IndexError):
        print(f"  {C.DIM}Invalid selection.{C.RESET}")
        return

    _run_sync(app, registry, name)


def _sync_all(app, registry):
    """Sync all connectors."""
    instances = registry.list_instances()
    if not instances:
        print(f"\n  {C.DIM}No connectors configured.{C.RESET}")
        return

    for name in instances:
        _run_sync(app, registry, name)


def _run_sync(app, registry, name: str):
    """Run sync for a named connector and process captures through pipeline."""
    connector = registry.get(name)
    if not connector:
        print(f"  {C.DANGER}Connector '{name}' not found.{C.RESET}")
        return

    print(f"\n  {C.DIM}Syncing '{name}'...{C.RESET}")

    # Load last sync time from sync_records
    last_sync = _get_last_sync(app, name)
    record = connector.sync(since=last_sync)

    if record.errors > 0:
        print(f"  {C.DANGER}Sync failed with {record.errors} error(s).{C.RESET}")
        return

    captures = record.config.pop("captures", [])
    print(f"  {C.CONFIRM}Fetched {len(captures)} item(s) from '{name}'.{C.RESET}")

    if not captures:
        print(f"  {C.DIM}Nothing new to import.{C.RESET}")
        _save_sync_record(app, record)
        return

    # Process captures through pipeline or store directly
    stored = 0
    dupes = 0
    for capture in captures:
        if app.repo.check_capture_exists(capture.content_hash):
            dupes += 1
            continue

        app.repo.create_capture(capture)
        stored += 1

        # Try pipeline processing if available
        pipeline = app._get_pipeline()
        if pipeline:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    pipeline.process(capture)
                )
            except RuntimeError:
                # No event loop running
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(pipeline.process(capture))
                finally:
                    loop.close()
            except Exception as e:
                print(f"  {C.DIM}(pipeline processing skipped: {e}){C.RESET}")

    record.items_synced = stored
    _save_sync_record(app, record)

    print(f"  {C.CONFIRM}Imported {stored} new item(s){C.RESET}"
          f"{f', {dupes} duplicate(s) skipped' if dupes else ''}.")


def _status(app, registry):
    """Show sync status for all connectors."""
    print(f"\n{divider('─', C.WARM)}")
    print(f"  {C.BOLD}{C.WARM}SYNC STATUS{C.RESET}")
    print(divider())

    instances = registry.list_instances()
    if not instances:
        print(f"  {C.DIM}No connectors configured.{C.RESET}")
        return

    for name, connector in instances.items():
        last_sync = _get_last_sync(app, name)
        sync_str = last_sync.isoformat()[:19] if last_sync else "never"
        record = _get_sync_record(app, name)
        items = record.get("items_synced", 0) if record else 0
        errors = record.get("errors", 0) if record else 0

        status_icon = C.CONFIRM + "●" if last_sync else C.DIM + "○"
        print(f"  {status_icon}{C.RESET} {C.BOLD}{name}{C.RESET}  "
              f"{C.DIM}type={connector.connector_type}  "
              f"last_sync={sync_str}  items={items}  errors={errors}{C.RESET}")


def _remove_connector(registry):
    """Remove a connector instance."""
    instances = registry.list_instances()
    if not instances:
        print(f"\n  {C.DIM}No connectors to remove.{C.RESET}")
        return

    names = list(instances.keys())
    for i, name in enumerate(names, 1):
        print(f"    {i}. {name}")

    choice = prompt(f"  Remove [1-{len(names)}]: ").strip()
    try:
        idx = int(choice) - 1
        name = names[idx]
    except (ValueError, IndexError):
        print(f"  {C.DIM}Invalid selection.{C.RESET}")
        return

    if registry.remove(name):
        print(f"  {C.CONFIRM}Removed connector '{name}'.{C.RESET}")
    else:
        print(f"  {C.DIM}Connector not found.{C.RESET}")


# ── Sync Record Persistence ──────────────────────────────────────

def _get_last_sync(app, connector_name: str):
    """Get last sync timestamp for a connector."""
    from datetime import datetime, timezone
    record = _get_sync_record(app, connector_name)
    if record and record.get("last_sync"):
        try:
            return datetime.fromisoformat(record["last_sync"])
        except (ValueError, TypeError):
            pass
    return None


def _get_sync_record(app, connector_name: str) -> dict | None:
    """Get sync record from database."""
    try:
        conn = app.repo.get_truth_layer_conn()
        row = conn.execute(
            "SELECT * FROM sync_records WHERE connector_name = ? ORDER BY updated_at DESC LIMIT 1",
            [connector_name],
        ).fetchone()
        if row:
            cols = [desc[0] for desc in conn.description]
            return dict(zip(cols, row))
    except Exception:
        pass
    return None


def _save_sync_record(app, record):
    """Save sync record to database."""
    try:
        import json
        conn = app.repo.get_truth_layer_conn()
        conn.execute(
            """INSERT INTO sync_records (id, connector_name, connector_type, last_sync,
               items_synced, errors, cursor, config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                record.id,
                record.connector_name,
                record.connector_type,
                record.last_sync,
                record.items_synced,
                record.errors,
                record.cursor,
                json.dumps(record.config),
                record.created_at,
                record.updated_at,
            ],
        )
    except Exception as e:
        print(f"  {C.DIM}(sync record save failed: {e}){C.RESET}")
