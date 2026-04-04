import re
from typing import List, Tuple


def _extract_grade_weight(source_text: str) -> str:
    match = re.search(r"(\\d{1,3}(?:\\.\\d+)?)\\s*%", source_text or "")
    if not match:
        return ""
    return f"{match.group(1)}%"


def _derive_name(source_text: str, subject: str, assignment_type: str) -> str:
    cleaned = re.sub(r"\\s+", " ", (source_text or "")).strip(" .")
    if not cleaned:
        return f"{subject} {assignment_type.title()}"

    lowered = cleaned.lower()
    type_words = {
        "exam": ["midterm", "final", "exam", "test"],
        "quiz": ["quiz"],
        "project": ["project", "capstone", "proposal", "presentation"],
        "assignment": ["assignment", "homework", "hw", "problem set"],
    }
    words = type_words.get(assignment_type, [])
    for word in words:
        index = lowered.find(word)
        if index != -1:
            end = min(len(cleaned), index + 80)
            snippet = cleaned[index:end]
            return snippet.strip(" .")

    return cleaned[:80].strip(" .")


def _split_time_range(time_value: str) -> Tuple[str, str]:
    if not time_value:
        return "", ""
    parts = re.split(r"\\s*(?:-|–|to)\\s*", time_value, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return time_value.strip(), ""


def convert_rows_to_workflow_format(rows: List[List[str]]) -> dict:
    exams_quizzes: List[List[str]] = []
    take_home_assignments: List[List[str]] = []

    for row in rows:
        if len(row) < 8:
            continue

        subject, date, time_value, assignment_type, _time_given, location, _page, source_text = row[:8]
        normalized_type = (assignment_type or "").strip().lower()
        grade_weight = _extract_grade_weight(source_text)
        name = _derive_name(source_text, subject or "Unknown", normalized_type or "assignment")

        if normalized_type in {"exam", "quiz"}:
            start_time, end_time = _split_time_range(time_value)
            exams_quizzes.append([
                subject,
                date,
                normalized_type.title(),
                start_time,
                end_time,
                location,
                name,
                grade_weight,
            ])
        else:
            take_home_assignments.append([
                subject,
                date,
                normalized_type.title() if normalized_type else "Assignment",
                time_value,
                name,
                grade_weight,
            ])

    return {
        "exams_quizzes": exams_quizzes,
        "take_home_assignments": take_home_assignments,
    }
