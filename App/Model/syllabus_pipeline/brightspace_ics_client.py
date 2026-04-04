from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from icalendar import Calendar


def download_ics_feed(feed_url: str, output_path: Optional[str] = None) -> str:
    response = requests.get(feed_url, timeout=60)
    response.raise_for_status()

    target = output_path or str(Path("output") / "brightspace_feed.ics")
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return str(path)


def load_ics_events(ics_path: str) -> List[dict]:
    path = Path(ics_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"ICS file not found: {path}")

    with open(path, "rb") as file_handle:
        calendar = Calendar.from_ical(file_handle.read())

    events: List[dict] = []
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary", "")).strip()
        location = str(component.get("location", "")).strip()
        description = str(component.get("description", "")).strip()

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        start_value = dtstart.dt if dtstart else None
        end_value = dtend.dt if dtend else None

        events.append(
            {
                "summary": summary,
                "location": location,
                "description": description,
                "start": start_value,
                "end": end_value,
            }
        )

    return events


def _format_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return ""


def _format_time(value) -> str:
    if not value or not isinstance(value, datetime):
        return ""
    formatted = value.strftime("%I:%M %p")
    if formatted.startswith("0"):
        formatted = formatted[1:]
    return formatted


def _derive_type(summary: str, description: str) -> str:
    lowered = f"{summary} {description}".lower()
    if any(word in lowered for word in ["midterm", "final", "exam", "test"]):
        return "Exam"
    if "quiz" in lowered:
        return "Quiz"
    if any(word in lowered for word in ["project", "capstone", "presentation"]):
        return "Project"
    return "Assignment"


def ics_events_to_workflow(events: List[dict], subject_fallback: str = "Brightspace") -> Dict[str, List[List[str]]]:
    exams_quizzes: List[List[str]] = []
    take_home_assignments: List[List[str]] = []

    for event in events:
        summary = event.get("summary", "")
        description = event.get("description", "")
        event_type = _derive_type(summary, description)

        start_value = event.get("start")
        end_value = event.get("end")

        date_value = _format_date(start_value)
        start_time = _format_time(start_value)
        end_time = _format_time(end_value)

        if event_type in {"Exam", "Quiz"}:
            exam_start = start_time
            exam_end = end_time or start_time
            exams_quizzes.append([
                subject_fallback,
                date_value,
                event_type,
                exam_start,
                exam_end,
                event.get("location", ""),
                summary,
                "",
            ])
        else:
            take_home_assignments.append([
                subject_fallback,
                date_value,
                event_type,
                "",
                summary,
                "",
            ])

    return {
        "exams_quizzes": exams_quizzes,
        "take_home_assignments": take_home_assignments,
    }
