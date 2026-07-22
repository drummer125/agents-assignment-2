"""
Google Calendar tools for the Workspace Assistant agent.

Each tool is a plain Python function with type hints and a descriptive
docstring. ADK introspects both to build the tool schema the LLM sees, so
richness in the docstring directly improves tool-selection accuracy.

Return convention:
    Every tool returns a dict with a ``status`` key of ``"success"`` or
    ``"error"``. Success payloads carry the requested data. Error payloads
    carry a ``message`` that is safe to surface to the end user.

All datetime inputs are RFC 3339 / ISO 8601 strings with timezone offset,
e.g. ``"2026-07-10T14:30:00-06:00"``. The system instruction reminds the
agent to normalise user phrasings ("tomorrow at 2pm") to this format
before calling the tools.

Import note:
    ``agent.py`` prepends ``workspace_assistant/`` to sys.path at import
    time, so this file can safely use absolute imports like
    ``from tools.auth import get_calendar_service`` regardless of whether
    ADK loaded us as a package or the test harness loaded us top-level.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from googleapiclient.errors import HttpError

from tools.auth import get_calendar_service


# ---------------------------------------------------------------------------
# Helpers (not exposed as tools)
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _to_rfc3339(dt: datetime) -> str:
    """Format a timezone-aware datetime as an RFC 3339 string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _summarize_event(ev: dict) -> dict:
    """Trim a raw Google Calendar event to a compact, LLM-friendly shape."""
    return {
        "id": ev.get("id"),
        "summary": ev.get("summary", "(no title)"),
        "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date"),
        "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date"),
        "location": ev.get("location", ""),
        "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
        "html_link": ev.get("htmlLink", ""),
    }


# ---------------------------------------------------------------------------
# Tool 1: list upcoming events
# ---------------------------------------------------------------------------

def list_upcoming_events(max_results: int = 10, days_ahead: int = 7) -> dict:
    """List the user's upcoming calendar events over the next N days.

    Use this tool when the user asks what is on their calendar, what
    meetings they have today or this week, or wants a general overview
    of their schedule. Do NOT use this tool when the user wants to find
    a specific free time slot (use ``find_available_slots``) or check a
    single time range for conflicts (use ``check_conflicts``).

    Args:
        max_results: Maximum number of events to return. Defaults to 10.
            Values above 50 will be capped at 50 by the Google Calendar API.
        days_ahead: How many days from now to look ahead. Defaults to 7.
            Use 1 for "today", 7 for "this week", 30 for "this month".

    Returns:
        On success: ``{"status": "success", "count": int, "events": [...]}``
        where each event has id, summary, start, end, location, attendees,
        and html_link.
        On error: ``{"status": "error", "message": str}``.
    """
    try:
        service = get_calendar_service()
        time_min = _to_rfc3339(_now_utc())
        time_max = _to_rfc3339(_now_utc() + timedelta(days=days_ahead))

        events_result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=min(max_results, 50),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = [_summarize_event(e) for e in events_result.get("items", [])]
        return {"status": "success", "count": len(events), "events": events}

    except HttpError as e:
        return {
            "status": "error",
            "message": f"Google Calendar API error: {e.reason or str(e)}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 2: find available slots
# ---------------------------------------------------------------------------

def find_available_slots(
    duration_minutes: int,
    start_date: str,
    end_date: str,
    working_hours_start: int = 9,
    working_hours_end: int = 18,
) -> dict:
    """Find free time slots of a given duration within a date range.

    Scans the user's primary calendar between ``start_date`` and
    ``end_date`` and returns time slots of at least ``duration_minutes``
    that fall inside working hours and do not overlap any existing event.

    Use this tool when the user wants to know when they are free, wants
    to schedule a meeting but doesn't have a specific time in mind, or
    asks for options. Do NOT use this tool to create the event itself
    (use ``create_event``) or to check a specific pre-chosen time
    (use ``check_conflicts``).

    Args:
        duration_minutes: Length of the meeting to fit, in minutes.
            E.g. 30 for a half-hour sync, 60 for a one-hour meeting.
        start_date: RFC 3339 / ISO 8601 timestamp for the earliest slot
            considered, e.g. ``"2026-07-10T00:00:00-06:00"``.
        end_date: RFC 3339 / ISO 8601 timestamp for the latest slot
            considered, e.g. ``"2026-07-17T23:59:59-06:00"``.
        working_hours_start: Hour of day (0-23) when working hours begin.
            Defaults to 9 (9am).
        working_hours_end: Hour of day (0-23) when working hours end.
            Defaults to 18 (6pm).

    Returns:
        On success: ``{"status": "success", "count": int, "slots": [...]}``
        where each slot is ``{"start": iso, "end": iso, "duration_minutes": int}``.
        Slots are returned in chronological order, up to 10 results.
        On error: ``{"status": "error", "message": str}``.
    """
    try:
        service = get_calendar_service()

        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_date,
            timeMax=end_date,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        busy = events_result.get("items", [])

        # Extract busy intervals as (start, end) tuples of aware datetimes.
        busy_intervals: list[tuple[datetime, datetime]] = []
        for ev in busy:
            s = ev.get("start", {}).get("dateTime")
            e = ev.get("end", {}).get("dateTime")
            if s and e:
                busy_intervals.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))

        # Walk the range in 30-minute steps and emit non-overlapping slots.
        cursor = datetime.fromisoformat(start_date)
        range_end = datetime.fromisoformat(end_date)
        step = timedelta(minutes=30)
        needed = timedelta(minutes=duration_minutes)

        slots: list[dict] = []
        while cursor + needed <= range_end and len(slots) < 10:
            # Skip outside working hours; jump to next working-day window.
            if cursor.hour < working_hours_start:
                cursor = cursor.replace(
                    hour=working_hours_start, minute=0, second=0, microsecond=0
                )
                continue
            if cursor.hour >= working_hours_end:
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=working_hours_start, minute=0, second=0, microsecond=0
                )
                continue

            candidate_end = cursor + needed
            eod = cursor.replace(hour=working_hours_end, minute=0, second=0, microsecond=0)
            if candidate_end > eod:
                cursor = (cursor + timedelta(days=1)).replace(
                    hour=working_hours_start, minute=0, second=0, microsecond=0
                )
                continue

            overlaps = any(
                not (candidate_end <= b_start or cursor >= b_end)
                for b_start, b_end in busy_intervals
            )
            if not overlaps:
                slots.append({
                    "start": _to_rfc3339(cursor),
                    "end": _to_rfc3339(candidate_end),
                    "duration_minutes": duration_minutes,
                })
                cursor = candidate_end
            else:
                cursor = cursor + step

        return {"status": "success", "count": len(slots), "slots": slots}

    except HttpError as e:
        return {
            "status": "error",
            "message": f"Google Calendar API error: {e.reason or str(e)}",
        }
    except ValueError as e:
        return {
            "status": "error",
            "message": (
                "Invalid date format. Use ISO 8601 with timezone, e.g. "
                f"'2026-07-10T14:00:00-06:00'. Details: {e}"
            ),
        }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 3: create event
# ---------------------------------------------------------------------------

def create_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: str = "",
    location: str = "",
    attendees: Optional[list[str]] = None,
) -> dict:
    """Create a new event on the user's primary calendar.

    Use this tool when the user asks to schedule, book, or add a meeting,
    reminder, or appointment to their calendar. Before calling this tool,
    consider whether ``check_conflicts`` should be called first to warn
    the user about overlaps.

    Args:
        summary: Short title of the event, e.g. "Team Sync" or
            "1:1 with Alice". This is what appears on the calendar.
        start_datetime: Event start in RFC 3339 / ISO 8601 format with
            timezone, e.g. ``"2026-07-10T14:00:00-06:00"``.
        end_datetime: Event end in RFC 3339 / ISO 8601 format with
            timezone. Must be after ``start_datetime``.
        description: Longer body text for the event. Optional.
        location: Physical location or video-call link. Optional.
        attendees: List of email addresses to invite. Optional. The
            Google Calendar API will send invite emails automatically.

    Returns:
        On success: ``{"status": "success", "event": {...}}`` with the
        created event's id, summary, start, end, location, attendees,
        and html_link.
        On error: ``{"status": "error", "message": str}``.
    """
    try:
        service = get_calendar_service()

        body: dict = {
            "summary": summary,
            "start": {"dateTime": start_datetime},
            "end": {"dateTime": end_datetime},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        created = service.events().insert(
            calendarId="primary",
            body=body,
            sendUpdates="all" if attendees else "none",
        ).execute()

        return {"status": "success", "event": _summarize_event(created)}

    except HttpError as e:
        return {
            "status": "error",
            "message": f"Google Calendar API error: {e.reason or str(e)}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 4: check conflicts
# ---------------------------------------------------------------------------

def check_conflicts(start_datetime: str, end_datetime: str) -> dict:
    """Check whether any existing events overlap a proposed time range.

    Use this tool before creating a new event to warn the user about
    conflicts, or when the user directly asks "do I have anything at
    3pm tomorrow?" or "am I free between 2 and 4?".

    Args:
        start_datetime: Proposed start in RFC 3339 / ISO 8601 with
            timezone, e.g. ``"2026-07-10T14:00:00-06:00"``.
        end_datetime: Proposed end in RFC 3339 / ISO 8601 with timezone.

    Returns:
        On success: ``{"status": "success", "has_conflict": bool,
        "count": int, "conflicts": [...]}`` where ``conflicts`` is a
        list of events that overlap the requested range (empty when
        ``has_conflict`` is False).
        On error: ``{"status": "error", "message": str}``.
    """
    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_datetime,
            timeMax=end_datetime,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        conflicts = [_summarize_event(e) for e in events_result.get("items", [])]
        return {
            "status": "success",
            "has_conflict": len(conflicts) > 0,
            "count": len(conflicts),
            "conflicts": conflicts,
        }

    except HttpError as e:
        return {
            "status": "error",
            "message": f"Google Calendar API error: {e.reason or str(e)}",
        }
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 5: reschedule event
# ---------------------------------------------------------------------------

def reschedule_event(
    event_id: str,
    new_start_datetime: str,
    new_end_datetime: str,
) -> dict:
    """Move an existing event to a new time.

    Use this tool when the user asks to move, reschedule, postpone, or
    change the time of an event they already have. If the user doesn't
    know the event id, call ``list_upcoming_events`` first to find it.

    Args:
        event_id: The Google Calendar event id (e.g. from
            ``list_upcoming_events``). This is NOT the summary/title.
        new_start_datetime: New start in RFC 3339 / ISO 8601 with
            timezone.
        new_end_datetime: New end in RFC 3339 / ISO 8601 with timezone.

    Returns:
        On success: ``{"status": "success", "event": {...}}`` with the
        updated event details.
        On error: ``{"status": "error", "message": str}``. Common causes:
        the event_id doesn't exist, or the user lacks permission.
    """
    try:
        service = get_calendar_service()

        # Fetch the existing event so we preserve fields like attendees,
        # description, and location. Only the times change.
        existing = service.events().get(calendarId="primary", eventId=event_id).execute()
        existing["start"] = {"dateTime": new_start_datetime}
        existing["end"] = {"dateTime": new_end_datetime}

        updated = service.events().update(
            calendarId="primary",
            eventId=event_id,
            body=existing,
            sendUpdates="all" if existing.get("attendees") else "none",
        ).execute()

        return {"status": "success", "event": _summarize_event(updated)}

    except HttpError as e:
        reason = e.reason or str(e)
        if e.resp.status == 404:
            return {
                "status": "error",
                "message": (
                    f"Event id '{event_id}' not found. Try list_upcoming_events "
                    "first to get the correct id."
                ),
            }
        return {"status": "error", "message": f"Google Calendar API error: {reason}"}
    except Exception as e:
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


# ---------------------------------------------------------------------------
# Registry consumed by agent.py
# ---------------------------------------------------------------------------

calendar_tools = [
    list_upcoming_events,
    find_available_slots,
    create_event,
    check_conflicts,
    reschedule_event,
]
