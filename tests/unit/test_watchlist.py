"""Tests for the WatchlistScanner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from memora.core.watchlist import WatchlistScanner, classify_relationship


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_person_nodes.return_value = []
    repo.update_node_properties_raw = MagicMock()
    return repo


@pytest.fixture
def mock_truth_layer():
    tl = MagicMock()
    tl.deposit_fact = MagicMock(return_value="fact-id-1")
    tl.query_facts = MagicMock(return_value=[])
    return tl


@pytest.fixture
def mock_search_tool():
    tool = MagicMock()
    tool.search = MagicMock(return_value=[])
    tool.available = True
    return tool


@pytest.fixture
def mock_scraper():
    scraper = MagicMock()
    scraper.scrape = MagicMock(return_value={"success": False})
    return scraper


@pytest.fixture
def scanner(mock_repo, mock_truth_layer, mock_search_tool, mock_scraper):
    return WatchlistScanner(
        repo=mock_repo,
        truth_layer=mock_truth_layer,
        search_tool=mock_search_tool,
        scraper=mock_scraper,
    )


def _make_person(
    name="Alice Smith",
    org="Acme Corp",
    role="Engineer",
    last_scan=None,
    relationship="colleague",
    linkedin_url="",
):
    """Helper to create a person dict matching repo output."""
    props = {
        "organization": org,
        "role": role,
        "relationship_to_user": relationship,
    }
    if last_scan is not None:
        props["watchlist_last_scan"] = last_scan
    if linkedin_url:
        props["contact_info"] = {"linkedin_url": linkedin_url}
    return {
        "id": "node-001",
        "title": name,
        "properties": props,
        "last_accessed": None,
        "networks": "[]",
    }


# ── classify_relationship ─────────────────────────────────────────────

class TestClassifyRelationship:
    def test_close(self):
        assert classify_relationship({"relationship_to_user": "spouse"}) == "close"
        assert classify_relationship({"relationship_to_user": "close friend"}) == "close"

    def test_regular(self):
        assert classify_relationship({"relationship_to_user": "colleague"}) == "regular"
        assert classify_relationship({"relationship_to_user": "mentor"}) == "regular"

    def test_acquaintance(self):
        assert classify_relationship({"relationship_to_user": "met at conference"}) == "acquaintance"
        assert classify_relationship({}) == "acquaintance"


# ── _build_search_query ──────────────────────────────────────────────

class TestBuildSearchQuery:
    def test_with_org_and_role(self, scanner):
        person = _make_person(name="Bob Jones", org="Google", role="SRE")
        query = scanner._build_search_query(person)
        assert '"Bob Jones"' in query
        assert '"Google"' in query
        assert "LinkedIn" in query

    def test_with_role_no_org(self, scanner):
        person = _make_person(name="Bob Jones", org="", role="SRE")
        query = scanner._build_search_query(person)
        assert '"Bob Jones"' in query
        assert '"SRE"' in query
        assert "LinkedIn" in query

    def test_minimal(self, scanner):
        person = _make_person(name="Bob Jones", org="", role="")
        query = scanner._build_search_query(person)
        assert query == '"Bob Jones" LinkedIn'


# ── _is_due_for_scan ─────────────────────────────────────────────────

class TestIsDueForScan:
    def test_never_scanned(self, scanner):
        person = _make_person(last_scan=None)
        assert scanner._is_due_for_scan(person, "regular") is True

    def test_recent_scan(self, scanner):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        person = _make_person(last_scan=recent)
        assert scanner._is_due_for_scan(person, "regular") is False

    def test_expired_close(self, scanner):
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        person = _make_person(last_scan=old)
        assert scanner._is_due_for_scan(person, "close") is True

    def test_expired_acquaintance(self, scanner):
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        person = _make_person(last_scan=old)
        assert scanner._is_due_for_scan(person, "acquaintance") is True

    def test_not_expired_acquaintance(self, scanner):
        recent = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        person = _make_person(last_scan=recent)
        assert scanner._is_due_for_scan(person, "acquaintance") is False


# ── _detect_changes ──────────────────────────────────────────────────

class TestDetectChanges:
    def test_role_change(self, scanner):
        person = _make_person(role="Engineer")
        profile = {"role": "Senior Engineer", "organization": "Acme Corp", "source_url": ""}
        changes = scanner._detect_changes(person, profile)
        assert len(changes) == 1
        assert changes[0]["change_type"] == "role_change"
        assert changes[0]["old_value"] == "Engineer"
        assert changes[0]["new_value"] == "Senior Engineer"

    def test_company_change(self, scanner):
        person = _make_person(org="Acme Corp")
        profile = {"role": "Engineer", "organization": "NewCo", "source_url": ""}
        changes = scanner._detect_changes(person, profile)
        assert len(changes) == 1
        assert changes[0]["change_type"] == "company_change"

    def test_no_changes(self, scanner):
        person = _make_person(role="Engineer", org="Acme Corp")
        profile = {"role": "Engineer", "organization": "Acme Corp", "source_url": ""}
        changes = scanner._detect_changes(person, profile)
        assert changes == []

    def test_new_activity_role(self, scanner):
        person = _make_person(role="", org="Acme Corp")
        profile = {"role": "Engineer", "organization": "Acme Corp", "source_url": ""}
        changes = scanner._detect_changes(person, profile)
        assert any(c["change_type"] == "new_activity" for c in changes)

    def test_both_changes(self, scanner):
        person = _make_person(role="Engineer", org="Acme Corp")
        profile = {"role": "VP", "organization": "NewCo", "source_url": ""}
        changes = scanner._detect_changes(person, profile)
        types = {c["change_type"] for c in changes}
        assert "role_change" in types
        assert "company_change" in types


# ── Full scan integration ────────────────────────────────────────────

class TestScan:
    def test_scan_skips_not_due(self, scanner, mock_repo):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        person = _make_person(last_scan=recent, relationship="colleague")
        mock_repo.get_person_nodes.return_value = [person]
        results = scanner.scan()
        assert results == []
        # Search should never be called
        scanner._search_tool.search.assert_not_called()

    def test_scan_processes_due(self, scanner, mock_repo, mock_search_tool, mock_truth_layer):
        person = _make_person(last_scan=None, relationship="colleague")
        mock_repo.get_person_nodes.return_value = [person]

        mock_search_tool.search.return_value = [
            {
                "title": "Alice Smith - Senior Engineer - NewCo | LinkedIn",
                "url": "https://linkedin.com/in/alice-smith",
                "snippet": "Alice Smith is a Senior Engineer at NewCo",
            }
        ]

        results = scanner.scan()

        # Should have detected changes (role and/or company)
        assert len(results) > 0
        assert all("node_id" in r for r in results)
        assert all("message" in r for r in results)

        # Truth layer should have been called
        assert mock_truth_layer.deposit_fact.called

        # Properties should have been updated
        assert mock_repo.update_node_properties_raw.called

    def test_scan_no_search_tool(self, mock_repo, mock_truth_layer):
        scanner = WatchlistScanner(repo=mock_repo, truth_layer=mock_truth_layer)
        person = _make_person(last_scan=None)
        mock_repo.get_person_nodes.return_value = [person]
        results = scanner.scan()
        assert results == []
