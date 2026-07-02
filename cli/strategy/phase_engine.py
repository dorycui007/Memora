"""Phase detection and time intelligence — ported from TimeEngine in strategy_mindmap.html."""

from __future__ import annotations

import math
from datetime import date, datetime

from cli.strategy.data import NODE_DATA, PHASES


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def current_phase() -> dict:
    """Return the phase dict for today's date."""
    today = date.today()
    for phase in PHASES:
        start = _parse_date(phase["start"])
        end = _parse_date(phase["end"])
        if start and end and start <= today <= end:
            return phase
    # Before first phase
    if today < _parse_date(PHASES[0]["start"]):
        return PHASES[0]
    # After last phase
    return PHASES[-1]


def current_phase_index() -> int:
    cp = current_phase()
    for i, phase in enumerate(PHASES):
        if phase["id"] == cp["id"]:
            return i
    return 0


def phase_progress() -> int:
    """Return percentage (0-100) through the current phase."""
    cp = current_phase()
    start = _parse_date(cp["start"])
    end = _parse_date(cp["end"])
    if not start or not end:
        return 0
    today = date.today()
    total = (end - start).days
    elapsed = (today - start).days
    if total <= 0:
        return 100
    return max(0, min(100, round(elapsed / total * 100)))


def days_until(date_str: str | None) -> int | None:
    """Days until a deadline. Negative means overdue."""
    d = _parse_date(date_str)
    if not d:
        return None
    return (d - date.today()).days


def is_overdue(date_str: str | None) -> bool:
    d = days_until(date_str)
    return d is not None and d < 0


def urgency_level(date_str: str | None) -> str:
    """Return urgency: overdue, critical, high, medium, low."""
    d = days_until(date_str)
    if d is None:
        return "low"
    if d < 0:
        return "overdue"
    if d <= 7:
        return "critical"
    if d <= 30:
        return "high"
    if d <= 90:
        return "medium"
    return "low"


def day_of_phase() -> int:
    cp = current_phase()
    start = _parse_date(cp["start"])
    if not start:
        return 1
    return max(1, (date.today() - start).days)


def phase_days_remaining() -> int | None:
    cp = current_phase()
    return days_until(cp["end"])


def urgent_actions(max_days: int = 14) -> list[tuple[str, str, str, int | None]]:
    """Return (entity_id, entity_label, action, days_left) for items due within max_days."""
    results = []
    for eid, data in NODE_DATA.items():
        deadline = data.get("deadline")
        if not deadline:
            continue
        d = days_until(deadline)
        if d is not None and d <= max_days:
            for action in data.get("actions", []):
                results.append((eid, eid.replace("_", " ").title(), action, d))
    results.sort(key=lambda x: x[3] if x[3] is not None else math.inf)
    return results


def entities_by_phase(phase_id: str) -> list[str]:
    """Return entity IDs that belong to a given phase."""
    return [eid for eid, data in NODE_DATA.items() if data.get("phase") == phase_id]


def at_risk_entities() -> list[tuple[str, dict]]:
    """Return entities with at-risk status."""
    return [(eid, data) for eid, data in NODE_DATA.items() if data.get("status") == "at-risk"]
