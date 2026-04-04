def build_text_prompt(text: str) -> str:
    return f"""
You extract academic deadlines from syllabus text.

Return ONLY valid JSON (no markdown), as an array of arrays.
Each row must have exactly 8 fields in this exact order:
[Subject, Date, Time, Type, TimeGiven, Location, Page, SourceText]

Rules:
- Include only actionable deadlines/events (homework, assignment, project, quiz, exam, test, midterm, final).
- Type must be one of: assignment, project, quiz, exam.
- Date format must be YYYY-MM-DD when possible.
- TimeGiven is duration only (for quiz/exam), else empty string.
- Location should be filled for exams when available, else empty string.
- Page should be the page number if inferable from PAGE markers.
- SourceText should be a concise supporting snippet from the document.
- Do not include explanatory text.

Syllabus text:
{text}
""".strip()


def build_pdf_prompt() -> str:
    return """
You extract academic deadlines from the provided syllabus PDF.

Return ONLY valid JSON (no markdown), as an array of arrays.
Each row must have exactly 8 fields in this exact order:
[Subject, Date, Time, Type, TimeGiven, Location, Page, SourceText]

Rules:
- Include only actionable deadlines/events (homework, assignment, project, quiz, exam, test, midterm, final).
- Type must be one of: assignment, project, quiz, exam.
- Date format must be YYYY-MM-DD when possible.
- TimeGiven is duration only (for quiz/exam), else empty string.
- Location should be filled for exams when available, else empty string.
- Page should be the page number when available.
- SourceText should be a concise supporting snippet from the document.
- Do not include explanatory text.
""".strip()
