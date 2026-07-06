from __future__ import annotations

import re
from dataclasses import dataclass, field

from .report_query import is_report_query


@dataclass(frozen=True)
class ParsedCommand:
    intent: str
    course: str
    title: str
    deadline: str = ""
    marks: int | None = None
    description: str = ""
    attachment_query: str = ""
    generated_kind: str = ""
    missing_fields: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing_fields


class CommandParser:
    def parse(self, text: str) -> ParsedCommand | None:
        normalized = normalize_spaces(text)
        lowered = normalized.lower()

        # A question about submissions/completion is a report request, not a
        # command to create anything. Bail out so the reporting path handles it
        # instead of asking the teacher for a course/title/deadline.
        if is_report_query(lowered):
            return None

        if self._looks_like_ai_generation(lowered):
            return self._parse_ai_generation(normalized)
        if self._looks_like_material(lowered):
            return self._parse_material(normalized)
        if self._looks_like_assignment(lowered):
            return self._parse_assignment(normalized)
        if self._looks_like_announcement(lowered):
            return self._parse_announcement(normalized)
        return None

    def _parse_assignment(self, text: str) -> ParsedCommand:
        course = extract_course(text)
        title = extract_title(text, ["assignment", "homework", "task"])
        deadline = extract_field(text, ["deadline", "due", "due date"])
        marks_text = extract_field(text, ["marks", "points", "max points"])
        description = extract_field(text, ["instructions", "description"])
        attachment_query = extract_attachment_query(text)

        marks = int(marks_text) if marks_text and marks_text.isdigit() else None
        if not deadline:
            deadline = extract_inline_deadline(text)
        if marks is None:
            marks = extract_inline_marks(text)

        missing = []
        if not course:
            missing.append("course")
        if not title:
            missing.append("title")
        if not deadline:
            missing.append("deadline")

        return ParsedCommand(
            intent="assignment",
            course=course,
            title=title,
            deadline=deadline,
            marks=marks,
            description=description,
            attachment_query=attachment_query,
            missing_fields=missing,
        )

    def _parse_ai_generation(self, text: str) -> ParsedCommand:
        lowered = text.lower()
        kind = "assignment"
        if "quiz" in lowered:
            kind = "quiz"
        elif "rubric" in lowered:
            kind = "rubric"

        course = extract_generated_course(text) or extract_course(text)
        topic = extract_field(text, ["topic", "title"]) or extract_generated_topic(text, kind)
        deadline = extract_field(text, ["deadline", "due", "due date"])
        marks_text = extract_field(text, ["marks", "points", "max points"])
        marks = int(marks_text) if marks_text and marks_text.isdigit() else extract_inline_marks(text)
        if not deadline and kind in {"assignment", "quiz"}:
            deadline = extract_inline_deadline(text)

        missing = []
        if not course:
            missing.append("course")
        if not topic:
            missing.append("topic")
        if kind in {"assignment", "quiz"} and not deadline:
            missing.append("deadline")

        return ParsedCommand(
            intent="ai_generate",
            course=course,
            title=topic,
            deadline=deadline,
            marks=marks,
            generated_kind=kind,
            missing_fields=missing,
        )

    def _parse_material(self, text: str) -> ParsedCommand:
        course = extract_course(text)
        title = extract_title(text, ["notes", "material", "study material", "lecture", "pdf", "file"])
        description = extract_field(text, ["description", "message"])
        attachment_query = extract_attachment_query(text)

        missing = []
        if not course:
            missing.append("course")
        if not title:
            missing.append("title")

        return ParsedCommand(
            intent="material",
            course=course,
            title=title,
            description=description,
            attachment_query=attachment_query,
            missing_fields=missing,
        )

    def _parse_announcement(self, text: str) -> ParsedCommand:
        course = extract_course(text)
        title = extract_announcement_message(text)

        missing = []
        if not course:
            missing.append("course")
        if not title:
            missing.append("message")

        return ParsedCommand(
            intent="announcement",
            course=course,
            title=title,
            missing_fields=missing,
        )

    def _looks_like_assignment(self, lowered: str) -> bool:
        return any(
            re.search(pattern, lowered)
            for pattern in [
                r"\bassignment\b",
                r"\bhomework\b",
                r"\btask\s+(?:banao|create|post|upload|add)\b",
            ]
        )

    def _looks_like_material(self, lowered: str) -> bool:
        return any(
            re.search(pattern, lowered)
            for pattern in [
                r"\bnotes?\b",
                r"\bmaterial\b",
                r"\bstudy material\b",
                r"\blecture\b",
                r"\bpdf\s+upload\b",
                r"\bfile\s+upload\b",
                r"\bupload\s+(?:pdf|file|notes?|lecture|material)\b",
            ]
        )

    def _looks_like_announcement(self, lowered: str) -> bool:
        return any(word in lowered for word in ["announcement", "announce", "notice"])

    def _looks_like_ai_generation(self, lowered: str) -> bool:
        return bool(re.search(r"\b(generate|create ai|ai)\b.*\b(assignment|quiz|rubric)\b", lowered))


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_course(text: str) -> str:
    patterns = [
        r"(?P<course>.+?)\s+(?:mein|me|main|for)\s+.+",
        r"(?:for|in)\s+(?P<course>.+?)\s+(?:generate|create)\s+.+",
        r"(?:for|in)\s+(?P<course>.+?)\s+(?:create|post|upload|add|assignment|announcement|notes|material)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return cleanup_value(match.group("course"))
    return ""


def extract_generated_course(text: str) -> str:
    match = re.search(
        r"(?:generate|create)\s+(?:ai\s+)?(?:assignment|quiz|rubric)\s+(?:for|in)\s+"
        r"(?P<course>.+?)(?:\s+topic\b|\s+title\b|\.|$)",
        text,
        re.IGNORECASE,
    )
    if match:
        return cleanup_value(match.group("course"))
    return ""


def extract_title(text: str, intent_words: list[str]) -> str:
    # Prefer high-precision matches. When nothing is clearly the title we return
    # "" on purpose so the assistant asks for it, rather than guessing a course
    # or connector phrase and publishing the wrong thing.
    field_title = extract_field(text, ["title", "topic"])
    if field_title:
        return field_title

    joined = "|".join(re.escape(word) for word in intent_words)
    # Stop the title before the class ("for X"), other markers, or field labels.
    stop = r"(?:\.|,| and | for | to | mein | deadline| due| marks| points| instructions| upload| post|$)"

    # "<word> on|about|regarding X"  ->  "assignment on Joins for databases" = "Joins"
    marker = re.search(rf"(?:{joined})\s+(?:on|about|regarding)\s+(?P<title>.+?){stop}", text, re.IGNORECASE)
    if marker:
        title = cleanup_value(marker.group("title"))
        if title:
            return title

    # "mein/me/main/for X <word>"  ->  "SE Databases mein Python Loops assignment" = "Python Loops"
    prefixed = re.search(rf"(?:mein|me|main|for)\s+(?P<title>.+?)\s+(?:{joined})\b", text, re.IGNORECASE)
    if prefixed:
        title = strip_course_prefix(cleanup_value(prefixed.group("title")))
        if title:
            return title

    # "X <word> banao/create/..."  ->  "normalization notes upload" style
    verbed = re.search(rf"(?P<title>.+?)\s+(?:{joined})\s+(?:banao|create|upload|post|add)", text, re.IGNORECASE)
    if verbed:
        title = strip_course_prefix(cleanup_value(verbed.group("title")))
        if title:
            return title

    # Explicit colon form: "<word>: X" or "<word> banao: X"
    coloned = re.search(rf"(?:{joined})\s+(?:banao|create|upload|post|add)?\s*:\s*(?P<title>.+?){stop}", text, re.IGNORECASE)
    if coloned:
        title = strip_course_prefix(cleanup_value(coloned.group("title")))
        if title:
            return title

    return ""


def extract_announcement_message(text: str) -> str:
    colon = re.search(r"(?:announcement|announce|notice)[^:]*:\s*(?P<message>.+)$", text, re.IGNORECASE)
    if colon:
        return cleanup_value(colon.group("message"))

    match = re.search(
        r"(?:announcement|announce|notice)\s+(?:post|karo|create)?\s*(?P<message>.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return cleanup_value(match.group("message"))
    return ""


def extract_generated_topic(text: str, kind: str) -> str:
    # Stop the topic at connectors ("and upload it to ..."), course markers,
    # or field labels so free-form phrasings like
    # "generate an assignment in normalization and upload it to databases class"
    # yield just "normalization".
    stop = r"(?:\.|,| and | & | deadline| due| marks| points| upload| post| for | to | in class| class\b|$)"
    patterns = [
        rf"(?:generate|create|make|prepare)\s+(?:an?\s+|the\s+|ai\s+)?{kind}\s+(?:for|on|about|in|regarding)\s+(?P<topic>.+?){stop}",
        rf"{kind}\s+(?:for|on|about|in|regarding)\s+(?P<topic>.+?){stop}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            topic = cleanup_value(match.group("topic"))
            if topic:
                return topic
    return ""


def extract_field(text: str, names: list[str]) -> str:
    joined = "|".join(re.escape(name) for name in names)
    boundary = (
        r"(?=\.|,|\s+(?:deadline|due|due date|marks|points|max points|"
        r"instructions|description|title|topic|file|attach|attachment)\b|$)"
    )
    match = re.search(
        rf"(?:{joined})\s*:?\s*(?P<value>.+?){boundary}",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return cleanup_value(match.group("value"))


def extract_attachment_query(text: str) -> str:
    drive_value = extract_field(
        text,
        [
            "attach from google drive",
            "attach from drive",
            "drive file",
            "google drive file",
        ],
    )
    if drive_value:
        return f"drive:{drive_value}"
    return extract_field(text, ["attach", "file", "attachment"])


def extract_inline_deadline(text: str) -> str:
    match = re.search(
        r"(?:deadline|due)\s+(?P<value>.+?)(?:\.|,|\s+marks|\s+points|\s+instructions|$)",
        text,
        re.IGNORECASE,
    )
    return cleanup_value(match.group("value")) if match else ""


def extract_inline_marks(text: str) -> int | None:
    match = re.search(r"(?:marks|points|max points)\s*:?\s*(?P<marks>\d+)", text, re.IGNORECASE)
    return int(match.group("marks")) if match else None


def strip_course_prefix(value: str) -> str:
    return re.sub(r"^.+?\s+(?:mein|me|main|for)\s+", "", value, flags=re.IGNORECASE).strip()


def cleanup_value(value: str) -> str:
    cleaned = value.strip(" :.-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def render_preview(command: ParsedCommand, selected_course: str = "", file_name: str = "") -> str:
    if not command.is_complete:
        missing = ", ".join(command.missing_fields)
        return f"I need these details before I can continue: {missing}."

    course = selected_course or command.course
    if command.intent == "ai_generate":
        marks = str(command.marks) if command.marks is not None else "Auto"
        deadline = command.deadline or "Not needed"
        kind = command.generated_kind.replace("_", " ").title()
        return (
            "Please review this AI-generated draft:\n\n"
            f"Course: {course}\n"
            f"Type: {kind}\n"
            f"Topic: {command.title}\n"
            f"Deadline: {deadline}\n"
            f"Marks: {marks}\n"
            f"Draft:\n{command.description or 'Draft will be generated before posting.'}\n\n"
            "Reply:\n"
            "1 = Create in Classroom\n"
            "2 = Save as draft\n"
            "3 = Cancel"
        )
    if command.intent == "assignment":
        marks = str(command.marks) if command.marks is not None else "Not set"
        instructions = command.description or "Not set"
        files = file_name or "No attachment"
        return (
            "Please confirm:\n\n"
            f"Course: {course}\n"
            "Type: Assignment\n"
            f"Title: {command.title}\n"
            f"Instructions: {instructions}\n"
            f"Deadline: {command.deadline}\n"
            f"Marks: {marks}\n"
            f"Files: {files}\n\n"
            "Reply:\n"
            "1 = Publish\n"
            "2 = Save as draft\n"
            "3 = Cancel"
        )

    if command.intent == "material":
        description = command.description or "Not set"
        files = file_name or "No attachment"
        return (
            "Please confirm:\n\n"
            f"Course: {course}\n"
            "Type: Study Material\n"
            f"Title: {command.title}\n"
            f"Description: {description}\n"
            f"Files: {files}\n\n"
            "Reply:\n"
            "1 = Post\n"
            "2 = Cancel"
        )

    return (
        "Please confirm:\n\n"
        f"Course: {course}\n"
        "Type: Announcement\n"
        f"Message: {command.title}\n\n"
        "Reply:\n"
        "1 = Post\n"
        "2 = Cancel"
    )
