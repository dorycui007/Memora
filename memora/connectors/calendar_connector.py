"""Calendar Connector — imports events from .ics files or CalDAV endpoints.

Maps calendar events to EventNode with participants, location, recurrence.
Auto-creates PersonNode references for participants and RELATED_TO edges.

Requires: icalendar>=5.0
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from memora.connectors.base import BaseConnector
from memora.graph.models import Capture

logger = logging.getLogger(__name__)


class CalendarConnector(BaseConnector):
    """Import events from iCalendar (.ics) files."""

    connector_type = "calendar"

    def __init__(self, name: str, config: dict | None = None) -> None:
        super().__init__(name, config)
        self._calendars: list = []

    def validate_config(self) -> list[str]:
        errors = []
        if not self.config.get("path") and not self.config.get("paths"):
            errors.append("Calendar connector requires 'path' or 'paths' in config")
        return errors

    def connect(self) -> bool:
        """Validate that icalendar is available and paths exist."""
        try:
            import icalendar  # noqa: F401
        except ImportError:
            logger.error("icalendar package not installed. Install with: pip install icalendar>=5.0")
            return False

        paths = self.config.get("paths", [])
        if not paths and self.config.get("path"):
            paths = [self.config["path"]]

        for path_str in paths:
            path = Path(path_str).expanduser()
            if not path.exists():
                logger.warning("Calendar path does not exist: %s", path)
            elif path.is_file() and path.suffix == ".ics":
                self._calendars.append(path)
            elif path.is_dir():
                self._calendars.extend(path.glob("*.ics"))

        if not self._calendars:
            logger.error("No .ics files found in configured paths")
            return False

        logger.info("Found %d calendar file(s)", len(self._calendars))
        return True

    def get_items(self, since: datetime | None = None) -> list[dict]:
        """Parse .ics files and extract VEVENT components."""
        import icalendar

        events = []
        for cal_path in self._calendars:
            try:
                with open(cal_path, "rb") as f:
                    cal = icalendar.Calendar.from_ical(f.read())

                for component in cal.walk():
                    if component.name != "VEVENT":
                        continue

                    dtstart = component.get("dtstart")
                    if dtstart:
                        dt = dtstart.dt
                        if hasattr(dt, "hour"):
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                        else:
                            # Date-only events
                            dt = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)

                        if since and dt < since:
                            continue

                    event = {
                        "uid": str(component.get("uid", str(uuid4()))),
                        "summary": str(component.get("summary", "Untitled Event")),
                        "description": str(component.get("description", "")),
                        "location": str(component.get("location", "")),
                        "dtstart": _dt_to_iso(component.get("dtstart")),
                        "dtend": _dt_to_iso(component.get("dtend")),
                        "attendees": _extract_attendees(component),
                        "organizer": _extract_organizer(component),
                        "recurrence": str(component.get("rrule", "")),
                        "status": str(component.get("status", "")),
                        "source_file": str(cal_path),
                    }
                    events.append(event)

            except Exception as e:
                logger.warning("Failed to parse calendar %s: %s", cal_path, e)

        logger.info("Extracted %d events from %d calendar(s)", len(events), len(self._calendars))
        return events

    def transform(self, raw_items: list[dict]) -> list[Capture]:
        """Transform calendar events into Capture objects."""
        captures = []
        for event in raw_items:
            summary = event["summary"]
            description = event.get("description", "")
            location = event.get("location", "")
            attendees = event.get("attendees", [])
            dtstart = event.get("dtstart", "")
            dtend = event.get("dtend", "")

            # Build rich content for the capture
            content_parts = [f"Calendar Event: {summary}"]
            if dtstart:
                content_parts.append(f"Date: {dtstart}")
            if dtend:
                content_parts.append(f"End: {dtend}")
            if location:
                content_parts.append(f"Location: {location}")
            if attendees:
                content_parts.append(f"Participants: {', '.join(attendees)}")
            if description:
                content_parts.append(f"Details: {description}")
            if event.get("recurrence"):
                content_parts.append(f"Recurrence: {event['recurrence']}")

            raw_content = "\n".join(content_parts)
            content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

            capture = Capture(
                id=uuid4(),
                modality="text",
                raw_content=raw_content,
                processed_content="",
                content_hash=content_hash,
                language="en",
                metadata={
                    "source": "calendar_connector",
                    "connector_name": self.name,
                    "event_uid": event["uid"],
                    "event_date": dtstart,
                    "location": location,
                    "participants": attendees,
                    "source_file": event.get("source_file", ""),
                },
                created_at=datetime.now(timezone.utc),
            )
            captures.append(capture)

        return captures


def _dt_to_iso(dt_prop) -> str:
    """Convert an icalendar datetime property to ISO string."""
    if dt_prop is None:
        return ""
    dt = dt_prop.dt
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _extract_attendees(component) -> list[str]:
    """Extract attendee names/emails from a VEVENT."""
    attendees = []
    att = component.get("attendee")
    if att is None:
        return attendees

    if not isinstance(att, list):
        att = [att]

    for a in att:
        val = str(a)
        # Strip mailto:
        if val.lower().startswith("mailto:"):
            val = val[7:]
        # Try to extract CN (Common Name) parameter
        params = getattr(a, "params", {})
        cn = params.get("CN", "")
        if cn:
            attendees.append(str(cn))
        elif val and "@" in val:
            attendees.append(val.split("@")[0].replace(".", " ").title())
        elif val:
            attendees.append(val)

    return attendees


def _extract_organizer(component) -> str:
    """Extract organizer name/email from a VEVENT."""
    org = component.get("organizer")
    if org is None:
        return ""

    params = getattr(org, "params", {})
    cn = params.get("CN", "")
    if cn:
        return str(cn)

    val = str(org)
    if val.lower().startswith("mailto:"):
        val = val[7:]
    return val
