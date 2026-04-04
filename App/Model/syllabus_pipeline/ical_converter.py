from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from uuid import uuid4

from dateutil import parser as date_parser


def _escape_ics_text(value: str) -> str:
    if value is None:
        return ""
    escaped = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return escaped.replace("\n", "\\n")


def _fold_ics_line(line: str, limit: int = 75) -> List[str]:
    if len(line) <= limit:
        return [line]
    parts = [line[:limit]]
    rest = line[limit:]
    while rest:
        parts.append(" " + rest[: limit - 1])
        rest = rest[limit - 1 :]
    return parts


def _add_ics_field(lines: List[str], key: str, value: str) -> None:
    for folded in _fold_ics_line(f"{key}:{value}"):
        lines.append(folded)


def _parse_datetime(date_value: str, time_value: str):
    if not date_value:
        return None
    if time_value:
        return date_parser.parse(f"{date_value} {time_value}")
    return date_parser.parse(date_value)


def _parse_date_only(date_value: str):
    if not date_value:
        return None
    return date_parser.parse(date_value).date()


def workflow_to_ical(workflow_data: Dict[str, List[List[str]]], output_path: str, default_duration_minutes: int = 60) -> str:
    lines: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Catapult//Syllabus Pipeline//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for exam in workflow_data.get("exams_quizzes", []):
        if len(exam) < 8:
            continue
        subject, date, event_type, start_time, end_time, location, name, grade_weight = exam[:8]
        if not start_time:
            continue
        start_dt = _parse_datetime(date, start_time)
        end_dt = _parse_datetime(date, end_time) if end_time else None

        if start_dt is None:
            continue
        if end_dt is None:
            end_dt = start_dt + timedelta(minutes=default_duration_minutes)

        lines.append("BEGIN:VEVENT")
        _add_ics_field(lines, "UID", f"{uuid4()}@catapult.local")
        _add_ics_field(lines, "DTSTAMP", now_utc)
        _add_ics_field(lines, "DTSTART", start_dt.strftime("%Y%m%dT%H%M%S"))
        _add_ics_field(lines, "DTEND", end_dt.strftime("%Y%m%dT%H%M%S"))
        _add_ics_field(lines, "SUMMARY", _escape_ics_text(f"{subject} {name}".strip()))
        _add_ics_field(lines, "LOCATION", _escape_ics_text(location or ""))
        description = f"Type: {event_type}; Weight: {grade_weight}".strip()
        _add_ics_field(lines, "DESCRIPTION", _escape_ics_text(description))
        lines.append("END:VEVENT")

    for item in workflow_data.get("take_home_assignments", []):
        if len(item) < 6:
            continue
        subject, date, event_type, due_time, name, grade_weight = item[:6]
        due_day = _parse_date_only(date)
        if due_day is None:
            continue
        next_day = due_day + timedelta(days=1)
        dtstart = due_day.strftime("%Y%m%d")
        dtend = next_day.strftime("%Y%m%d")

        lines.append("BEGIN:VEVENT")
        _add_ics_field(lines, "UID", f"{uuid4()}@catapult.local")
        _add_ics_field(lines, "DTSTAMP", now_utc)
        _add_ics_field(lines, "DTSTART;VALUE=DATE", dtstart)
        _add_ics_field(lines, "DTEND;VALUE=DATE", dtend)
        _add_ics_field(lines, "SUMMARY", _escape_ics_text(f"{subject} {name}".strip()))
        description = f"Type: {event_type}; Weight: {grade_weight}".strip()
        if due_time:
            description = f"{description}; Due Time (source): {due_time}".strip()
        _add_ics_field(lines, "DESCRIPTION", _escape_ics_text(description))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ics_text = "\r\n".join(lines) + "\r\n"
    path.write_bytes(ics_text.encode("utf-8"))
    return str(path)
