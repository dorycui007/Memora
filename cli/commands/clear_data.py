"""Clear data command — erase all databases and start fresh."""

from __future__ import annotations

import shutil
from pathlib import Path

from cli.rendering import C, divider, prompt, subcommand_header

from memora.graph.repository import GraphRepository


def cmd_clear_data(app):
    """Erase all databases (DuckDB, LanceDB, SQLite, backups) and start fresh."""
    subcommand_header(
        title="CLEAR DATA",
        symbol="✕",
        color=C.DANGER,
        border="simple",
    )
    print(f"  {C.SIGNAL}This will permanently delete:{C.RESET}")
    print(f"    - Graph database   {C.DIM}({app.settings.graph_dir}){C.RESET}")
    print(f"    - Vector store     {C.DIM}({app.settings.vector_dir}){C.RESET}")
    print(f"    - Backups          {C.DIM}({app.settings.backups_dir}){C.RESET}")

    sqlite_path = Path(__file__).resolve().parent.parent.parent / "memora.db"
    if sqlite_path.exists():
        print(f"    - SQLite file      {C.DIM}({sqlite_path}){C.RESET}")

    print()
    confirm = prompt(f"  {C.RED}Type 'yes' to confirm: {C.RESET}")
    if confirm.lower() != "yes":
        print(f"  {C.DIM}Cancelled.{C.RESET}")
        return

    if app.repo:
        app.repo.close()
        app.repo = None

    deleted = []

    graph_dir = app.settings.graph_dir
    if graph_dir.exists():
        shutil.rmtree(graph_dir)
        deleted.append("Graph database")

    vector_dir = app.settings.vector_dir
    if vector_dir.exists():
        shutil.rmtree(vector_dir)
        deleted.append("Vector store")

    backups_dir = app.settings.backups_dir
    if backups_dir.exists():
        shutil.rmtree(backups_dir)
        deleted.append("Backups")

    if sqlite_path.exists():
        sqlite_path.unlink()
        deleted.append("SQLite file")

    if deleted:
        print(f"\n  {C.GREEN}Deleted:{C.RESET} {', '.join(deleted)}")
    else:
        print(f"\n  {C.DIM}Nothing to delete.{C.RESET}")

    from memora.config import init_data_directory
    init_data_directory(app.settings)
    app.repo = GraphRepository(db_path=app.settings.db_path)

    print(f"  {C.GREEN}Fresh databases initialized. Memora is ready.{C.RESET}\n")
