"""Tests for watchlist and research CLI commands."""

from __future__ import annotations

import builtins
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch



# -- Helpers ------------------------------------------------------------------

def _make_app(has_api_key=True, people=None):
    """Build a minimal mock app for CLI command testing."""
    app = MagicMock()
    app._has_api_key = has_api_key
    app.settings = SimpleNamespace(
        openai_api_key="sk-test-key" if has_api_key else "",
    )

    if people is not None:
        app.repo.get_person_nodes.return_value = people
    else:
        app.repo.get_person_nodes.return_value = []

    return app


def _make_person(title="Alice", role="Engineer", org="Acme", tier_rel="colleague",
                 last_scan=None):
    import json
    props = {
        "role": role,
        "organization": org,
        "relationship_to_user": tier_rel,
    }
    if last_scan:
        props["watchlist_last_scan"] = last_scan
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": title,
        "properties": json.dumps(props),
        "last_accessed": None,
        "networks": "[]",
    }


# -- Dashboard Tests ----------------------------------------------------------

def test_dashboard_displays_people(capsys):
    from cli.commands.watchlist import _dashboard_view

    people = [
        _make_person("Alice", "Engineer", "Acme", "colleague"),
        _make_person("Bob", "Manager", "BigCorp", "close friend",
                     last_scan=datetime.now(timezone.utc).isoformat()),
    ]
    app = _make_app(people=people)

    with patch("cli.commands.watchlist.prompt", return_value=""):
        _dashboard_view(app)

    out = capsys.readouterr().out
    assert "Alice" in out
    assert "Bob" in out
    assert "regular" in out or "close" in out


def test_dashboard_empty_graph(capsys):
    from cli.commands.watchlist import _dashboard_view

    app = _make_app(people=[])

    with patch("cli.commands.watchlist.prompt", return_value=""):
        _dashboard_view(app)

    out = capsys.readouterr().out
    assert "No people" in out


# -- Scan Now Tests -----------------------------------------------------------

def test_scan_now_runs_scanner(capsys):
    from cli.commands.watchlist import _scan_now

    app = _make_app()

    mock_scanner = MagicMock()
    mock_scanner.scan.return_value = [
        {
            "change_type": "role_change",
            "person_name": "Alice",
            "old_value": "Engineer",
            "new_value": "Senior Engineer",
            "source_url": "https://linkedin.com/in/alice",
            "message": "Alice changed role: Engineer -> Senior Engineer",
            "node_id": "00000000-0000-0000-0000-000000000001",
        }
    ]

    mock_google = MagicMock()
    mock_google.GoogleSearchMCP.return_value.available = True
    mock_brave = MagicMock()
    mock_playwright = MagicMock()

    with patch("cli.commands.watchlist.prompt", return_value=""), \
         patch("cli.commands.watchlist.spinner"), \
         patch("memora.core.watchlist.WatchlistScanner", return_value=mock_scanner), \
         patch.dict("sys.modules", {
             "memora.mcp.google_search": mock_google,
             "memora.mcp.brave_search": mock_brave,
             "memora.mcp.playwright_scraper": mock_playwright,
         }):
        _scan_now(app)

    mock_scanner.scan.assert_called_once()
    out = capsys.readouterr().out
    assert "Alice" in out
    assert "role_change" in out


def test_scan_now_no_api_keys(capsys):
    from cli.commands.watchlist import _scan_now

    app = _make_app()

    with patch("cli.commands.watchlist.prompt", return_value=""), \
         patch("cli.commands.watchlist.spinner"):
        # Make MCP imports fail (no search tool available)
        with patch.dict("sys.modules", {
            "memora.mcp.google_search": None,
            "memora.mcp.brave_search": None,
        }):
            # Force import error
            with patch("builtins.__import__", side_effect=_import_fail_mcp):
                _scan_now(app)

    out = capsys.readouterr().out
    assert "No search API keys" in out


_original_import = builtins.__import__


def _import_fail_mcp(name, *args, **kwargs):
    """Fail imports for MCP search modules."""
    if name in ("memora.mcp.google_search", "memora.mcp.brave_search"):
        raise ImportError(f"No module named '{name}'")
    return _original_import(name, *args, **kwargs)


# -- Alerts Tests -------------------------------------------------------------

def test_alerts_view_shows_notifications(capsys):
    from cli.commands.watchlist import _alerts_view

    app = _make_app()

    mock_nm = MagicMock()
    mock_nm.get_notifications.return_value = [
        {
            "id": "notif-1",
            "type": "watchlist_alert",
            "message": "Alice changed role: Engineer -> CTO",
            "priority": "high",
            "read": False,
            "created_at": "2026-03-07T10:00:00",
            "related_node_ids": [],
            "trigger_condition": "",
        }
    ]

    with patch("cli.commands.watchlist.prompt", return_value=""), \
         patch("memora.core.notifications.NotificationManager", return_value=mock_nm):
        _alerts_view(app)

    out = capsys.readouterr().out
    assert "Alice" in out
    assert "CTO" in out
    assert "HIGH" in out


# -- Research Tests -----------------------------------------------------------

def test_research_renders_result(capsys):
    from cli.commands.research import cmd_research
    from memora.agents.researcher import ResearchResult, ResearchSource

    app = _make_app()

    mock_result = ResearchResult(
        answer="The answer is 42.",
        sources=[
            ResearchSource(
                url="https://example.com",
                title="Example Source",
                snippet="snippet",
                source_type="PRIMARY",
                reliability_score=0.85,
            ),
        ],
        facts_to_deposit=[{"statement": "fact1"}],
        confidence=0.72,
        anonymized_query="what is the answer",
    )

    mock_researcher = MagicMock()

    mock_google = MagicMock()
    mock_google.GoogleSearchMCP.return_value.available = True
    mock_brave = MagicMock()

    prompt_calls = iter(["what is the meaning of life", ""])

    with patch("cli.commands.research.prompt", side_effect=lambda *a, **k: next(prompt_calls)), \
         patch("cli.commands.research.spinner"), \
         patch("memora.agents.researcher.ResearcherAgent", return_value=mock_researcher), \
         patch.dict("sys.modules", {
             "memora.mcp.google_search": mock_google,
             "memora.mcp.brave_search": mock_brave,
         }), \
         patch("cli.commands.research.asyncio") as mock_asyncio:
        mock_asyncio.run.return_value = mock_result
        cmd_research(app)

    out = capsys.readouterr().out
    assert "42" in out
    assert "Example Source" in out
    assert "Facts deposited: 1" in out


def test_research_no_api_key(capsys):
    from cli.commands.research import cmd_research

    app = _make_app(has_api_key=False)

    prompt_calls = iter(["test query"])

    with patch("cli.commands.research.prompt", side_effect=lambda *a, **k: next(prompt_calls)):
        cmd_research(app)

    out = capsys.readouterr().out
    assert "unavailable" in out
