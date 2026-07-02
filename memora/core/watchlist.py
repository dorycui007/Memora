"""Watchlist Scanner — detect professional updates about people in the graph."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from memora.graph.models import parse_properties
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

# Scan interval mapping (days) — matches relationship decay tiers
SCAN_INTERVALS: dict[str, int] = {
    "close": 7,
    "regular": 14,
    "acquaintance": 30,
}

_CLOSE_KEYWORDS = {
    "partner", "spouse", "parent", "sibling", "child",
    "best friend", "close friend", "family",
}
_REGULAR_KEYWORDS = {
    "friend", "colleague", "teammate", "mentor", "mentee",
    "manager", "coworker", "collaborator",
}


def classify_relationship(properties: dict[str, Any]) -> str:
    """Classify a person's relationship tier based on *relationship_to_user*.

    Returns one of: 'close', 'regular', 'acquaintance'.
    Shared between WatchlistScanner and RelationshipDecayDetector.
    """
    rel = str(properties.get("relationship_to_user", "")).lower()
    for kw in _CLOSE_KEYWORDS:
        if kw in rel:
            return "close"
    for kw in _REGULAR_KEYWORDS:
        if kw in rel:
            return "regular"
    return "acquaintance"


class WatchlistScanner:
    """Scan for professional updates about people in the graph."""

    def __init__(
        self,
        repo: GraphRepository,
        truth_layer: Any | None = None,
        search_tool: Any | None = None,
        scraper: Any | None = None,
    ) -> None:
        self._repo = repo
        self._truth_layer = truth_layer
        self._search_tool = search_tool
        self._scraper = scraper

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> list[dict[str, Any]]:
        """Scan all PERSON nodes due for a watchlist check.

        Returns a list of change dicts suitable for notification creation.
        Each dict has: node_id, person_name, change_type, message, old_value,
        new_value, source_url.
        """
        persons = self._get_person_nodes()
        all_changes: list[dict[str, Any]] = []

        for person in persons:
            props = person.get("properties") or {}
            tier = classify_relationship(props)

            if not self._is_due_for_scan(person, tier):
                continue

            try:
                search_results = self._search_person(person)
                profile_data = self._extract_profile_data(search_results)
                changes = self._detect_changes(person, profile_data)

                if changes:
                    applied = self._apply_changes(person, changes, tier)
                    all_changes.extend(applied)
                else:
                    # No changes, but still update last scan timestamp
                    self._update_last_scan(person)

            except Exception:
                logger.warning(
                    "Watchlist scan failed for %s", person.get("title", "?"),
                    exc_info=True,
                )

        logger.info("Watchlist scan found %d change(s) across %d person(s)",
                     len(all_changes), len(persons))
        return all_changes

    # ------------------------------------------------------------------
    # Search & extraction
    # ------------------------------------------------------------------

    def _build_search_query(self, person: dict[str, Any]) -> str:
        """Construct a search query from Person node data."""
        name = person.get("title", "")
        props = person.get("properties") or {}
        org = props.get("organization", "")
        role = props.get("role", "")

        parts = [f'"{name}"']
        if org:
            parts.append(f'"{org}"')
        elif role:
            parts.append(f'"{role}"')
        parts.append("LinkedIn")
        return " ".join(parts)

    def _search_person(self, person: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute web search for a person and return combined results."""
        if not self._search_tool:
            return []

        query = self._build_search_query(person)
        results = self._search_tool.search(query, num_results=5)

        # Filter to LinkedIn-relevant URLs
        linkedin_results = [
            r for r in results if "linkedin.com" in r.get("url", "")
        ]

        # Also scrape known LinkedIn URL if available
        props = person.get("properties") or {}
        contact_info = props.get("contact_info") or {}
        linkedin_url = contact_info.get("linkedin_url", "")

        if linkedin_url and self._scraper:
            scraped = self._scraper.scrape(linkedin_url)
            if scraped.get("success"):
                linkedin_results.append({
                    "title": scraped.get("title", ""),
                    "url": linkedin_url,
                    "snippet": scraped.get("content", ""),
                    "source_type": "SCRAPED",
                })

        return linkedin_results if linkedin_results else results

    def _extract_profile_data(
        self, search_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse search results to extract current professional data."""
        data: dict[str, Any] = {
            "role": "",
            "organization": "",
            "headline": "",
            "source_url": "",
            "raw_content": "",
        }

        if not search_results:
            return data

        # Use the first result as primary source
        best = search_results[0]
        data["source_url"] = best.get("url", "")
        snippet = best.get("snippet", "")
        title = best.get("title", "")
        data["raw_content"] = snippet

        # LinkedIn titles are usually "Name - Role - Company | LinkedIn"
        # LinkedIn snippets often contain "Role at Company" patterns
        combined = f"{title} {snippet}"
        data["headline"] = title

        # Try to extract "Role at Organization" from combined text
        import re
        # Pattern: "Something at SomeCompany"
        at_match = re.search(
            r"[-–—]\s*(.+?)\s+(?:at|@)\s+(.+?)(?:\s*[|·\-–]|$)",
            combined,
        )
        if at_match:
            data["role"] = at_match.group(1).strip()
            data["organization"] = at_match.group(2).strip()
        else:
            # Fallback: split LinkedIn-style title "Name - Role - Company"
            parts = re.split(r"\s*[-–—|]\s*", title)
            if len(parts) >= 3:
                # parts[0] = name, parts[1] = role, parts[2] = company
                data["role"] = parts[1].strip()
                data["organization"] = parts[2].strip()

        # Also capture LinkedIn URL from results for later storage
        for r in search_results:
            url = r.get("url", "")
            if "linkedin.com/in/" in url:
                data["source_url"] = url
                break

        return data

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def _detect_changes(
        self,
        person: dict[str, Any],
        profile_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Compare profile data against stored person data."""
        changes: list[dict[str, Any]] = []
        props = person.get("properties") or {}
        new_role = profile_data.get("role", "").strip()
        new_org = profile_data.get("organization", "").strip()
        stored_role = str(props.get("role", "")).strip()
        stored_org = str(props.get("organization", "")).strip()
        source_url = profile_data.get("source_url", "")
        person_name = person.get("title", "Unknown")

        # Detect role change
        if new_role and stored_role and new_role.lower() != stored_role.lower():
            changes.append({
                "change_type": "role_change",
                "old_value": stored_role,
                "new_value": new_role,
                "source_url": source_url,
                "message": (
                    f"{person_name} changed role: "
                    f"{stored_role} -> {new_role}"
                ),
            })

        # Detect company change
        if new_org and stored_org and new_org.lower() != stored_org.lower():
            changes.append({
                "change_type": "company_change",
                "old_value": stored_org,
                "new_value": new_org,
                "source_url": source_url,
                "message": (
                    f"{person_name} changed company: "
                    f"{stored_org} -> {new_org}"
                ),
            })

        # Detect new activity (new data where none existed before)
        if new_role and not stored_role:
            changes.append({
                "change_type": "new_activity",
                "old_value": "",
                "new_value": new_role,
                "source_url": source_url,
                "message": f"{person_name} discovered role: {new_role}",
            })

        if new_org and not stored_org:
            changes.append({
                "change_type": "new_activity",
                "old_value": "",
                "new_value": new_org,
                "source_url": source_url,
                "message": f"{person_name} discovered organization: {new_org}",
            })

        return changes

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _apply_changes(
        self,
        person: dict[str, Any],
        changes: list[dict[str, Any]],
        tier: str,
    ) -> list[dict[str, Any]]:
        """Persist changes to the graph and truth layer."""
        import json

        node_id = str(person["id"])
        props = person.get("properties") or {}
        person_name = person.get("title", "Unknown")
        updated_props = dict(props)
        recheck_days = SCAN_INTERVALS.get(tier, 30)

        for change in changes:
            ct = change["change_type"]
            if ct == "role_change" or (ct == "new_activity" and change.get("new_value") == updated_props.get("role", change["new_value"])):
                if change["new_value"]:
                    updated_props["role"] = change["new_value"]
            if ct == "company_change" or (ct == "new_activity" and "organization" in change.get("message", "")):
                if change["new_value"]:
                    updated_props["organization"] = change["new_value"]

            # Store LinkedIn URL if found
            source_url = change.get("source_url", "")
            if "linkedin.com/in/" in source_url:
                contact_info = updated_props.get("contact_info") or {}
                if not contact_info.get("linkedin_url"):
                    contact_info["linkedin_url"] = source_url
                    updated_props["contact_info"] = contact_info

            # Deposit fact via truth layer
            if self._truth_layer:
                try:
                    self._truth_layer.deposit_fact(
                        node_id=node_id,
                        statement=change["message"],
                        confidence=0.7,
                        verified_by="watchlist",
                        recheck_interval_days=recheck_days,
                        metadata={"source_url": source_url},
                    )
                except Exception:
                    logger.warning("Failed to deposit watchlist fact for %s", person_name)

            change["node_id"] = node_id
            change["person_name"] = person_name

        # Update node properties + last scan timestamp
        updated_props["watchlist_last_scan"] = datetime.now(timezone.utc).isoformat()
        try:
            self._repo.update_node_properties_raw(node_id, json.dumps(updated_props))
        except Exception:
            logger.warning("Failed to update properties for %s", person_name, exc_info=True)

        return changes

    def _update_last_scan(self, person: dict[str, Any]) -> None:
        """Update just the last scan timestamp when no changes detected."""
        import json

        node_id = str(person["id"])
        props = person.get("properties") or {}
        updated_props = dict(props)
        updated_props["watchlist_last_scan"] = datetime.now(timezone.utc).isoformat()
        try:
            self._repo.update_node_properties_raw(node_id, json.dumps(updated_props))
        except Exception:
            logger.debug("Failed to update watchlist_last_scan for %s", person.get("title"))

    # ------------------------------------------------------------------
    # Scan eligibility
    # ------------------------------------------------------------------

    def _is_due_for_scan(self, person: dict[str, Any], tier: str) -> bool:
        """Check if enough time has passed since last watchlist scan."""
        props = person.get("properties") or {}
        last_scan = props.get("watchlist_last_scan")
        if not last_scan:
            return True

        last_dt = self._parse_datetime(last_scan)
        if last_dt is None:
            return True

        interval = SCAN_INTERVALS.get(tier, 30)
        days_since = (datetime.now(timezone.utc) - last_dt).days
        return days_since >= interval

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_person_nodes(self) -> list[dict[str, Any]]:
        """Query all PERSON nodes from the graph."""
        try:
            rows = self._repo.get_person_nodes()
        except Exception:
            logger.warning("Failed to fetch person nodes", exc_info=True)
            return []

        results: list[dict[str, Any]] = []
        for d in rows:
            d["properties"] = parse_properties(d["properties"])
            results.append(d)
        return results

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Safely parse a datetime from a string or datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None
