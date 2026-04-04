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


def _normalize_time_text(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = text.replace("â€“", "-").replace("–", "-").replace("—", "-").replace("−", "-")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    return text.strip()


def _extract_time_range_from_source(source_text: str) -> str:
    text = _normalize_time_text(source_text)
    if not text:
        return ""

    range_pattern = re.compile(
        r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
        flags=re.IGNORECASE,
    )
    single_pattern = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b", flags=re.IGNORECASE)

    range_match = range_pattern.search(text)
    if range_match:
        return range_match.group(0).strip()

    single_match = single_pattern.search(text)
    if single_match:
        return single_match.group(0).strip()

    return ""


def _clean_exam_name(name: str) -> str:
    value = _normalize_time_text(name)
    if not value:
        return value

    value = re.sub(
        r"\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\b.*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s{2,}", " ", value).strip(" -;,")
    return value


def _split_time_range(time_value: str) -> Tuple[str, str]:
    normalized = _normalize_time_text(time_value)
    if not normalized:
        return "", ""

    parts = re.split(r"\s*(?:-|to)\s*", normalized, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        start = parts[0].strip()
        end = parts[1].strip()

        end_meridiem = re.search(r"\b(am|pm)\b", end, flags=re.IGNORECASE)
        start_meridiem = re.search(r"\b(am|pm)\b", start, flags=re.IGNORECASE)
        if end_meridiem and not start_meridiem:
            start = f"{start} {end_meridiem.group(1)}"

        return start, end

    return normalized, ""


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
            effective_time_value = time_value or _extract_time_range_from_source(source_text)
            start_time, end_time = _split_time_range(effective_time_value)
            clean_name = _clean_exam_name(name)
            exams_quizzes.append([
                subject,
                date,
                normalized_type.title(),
                start_time,
                end_time,
                location,
                clean_name or name,
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
