from datetime import datetime
from typing import Dict, List, Tuple

from dateutil import parser as date_parser


def _format_date(value: str) -> str:
    if not value:
        return ""
    try:
        return date_parser.parse(value).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _format_time(value: str) -> str:
    if not value:
        return ""
    try:
        return date_parser.parse(value).strftime("%-I:%M %p")
    except Exception:
        return ""


def _derive_type(title: str, category: str) -> str:
    lowered = f"{title} {category}".lower()
    if any(word in lowered for word in ["midterm", "final", "exam", "test"]):
        return "Exam"
    if "quiz" in lowered:
        return "Quiz"
    if any(word in lowered for word in ["project", "capstone", "presentation"]):
        return "Project"
    return "Assignment"


def _extract_title(item: dict) -> str:
    return (
        item.get("Title")
        or item.get("Name")
        or item.get("TopicTitle")
        or item.get("Subject")
        or "Untitled"
    )


def _extract_location(item: dict) -> str:
    return item.get("Location") or item.get("Where") or ""


def _extract_weight(item: dict) -> str:
    for key in ["Weight", "GradeWeight", "WeightPercentage", "Percent"]:
        value = item.get(key)
        if value is not None and str(value) != "":
            text = str(value).replace("%", "").strip()
            return f"{text}%"
    return ""


def _extract_dates(item: dict) -> Tuple[str, str, str]:
    start = item.get("StartDate") or item.get("Start") or item.get("Date") or ""
    end = item.get("EndDate") or item.get("End") or ""
    due = item.get("DueDate") or item.get("Due") or ""
    return start, end, due


def brightspace_items_to_workflow(latest_data: Dict, subject_fallback: str = "Course") -> Dict[str, List[List[str]]]:
    exams_quizzes: List[List[str]] = []
    take_home_assignments: List[List[str]] = []

    subject = latest_data.get("course_name") or subject_fallback
    items = latest_data.get("items", [])

    for item in items:
        title = _extract_title(item)
        category = item.get("Type") or item.get("Category") or ""
        event_type = _derive_type(title, category)
        location = _extract_location(item)
        weight = _extract_weight(item)

        start_raw, end_raw, due_raw = _extract_dates(item)
        start_date = _format_date(start_raw or due_raw)
        start_time = _format_time(start_raw)
        end_time = _format_time(end_raw)
        due_time = _format_time(due_raw)

        if event_type in {"Exam", "Quiz"}:
            exams_quizzes.append([
                subject,
                start_date,
                event_type,
                start_time,
                end_time,
                location,
                title,
                weight,
            ])
        else:
            take_home_assignments.append([
                subject,
                start_date,
                event_type,
                due_time,
                title,
                weight,
            ])

    return {
        "exams_quizzes": exams_quizzes,
        "take_home_assignments": take_home_assignments,
    }
