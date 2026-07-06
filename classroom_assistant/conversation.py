"""Multi-turn slot filling.

When a teacher's first message is missing details, the assistant keeps the
half-finished request as a draft and merges the *next* message into it, instead
of forgetting the context (which is why a follow-up like
"topic name Database Management and deadline is 7/7/2026 5pm" used to fall
through to the generic menu).

Extraction here is intentionally label-light: teachers phrase answers in their
own words, so we accept "topic is X", "X", "deadline 7/7/2026", a bare date, and
similar, rather than a fixed syntax.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .command_parser import (
    ParsedCommand,
    cleanup_value,
    extract_inline_marks,
    normalize_spaces,
)
from .date_parser import parse_date
from datetime import date

# Label words that introduce a value, stripped from the front of an answer.
_LEADING_FILLERS = re.compile(
    r"^(?:the|is|are|will be|would be|name|named|called|about|on|for|by|:|=)\s+",
    re.IGNORECASE,
)

# Where a captured value should stop (next field / connector).
_VALUE_STOP = r"(?:\s+and\b|\s*[,.;]|\s+deadline\b|\s+due\b|\s+marks?\b|\s+points?\b|$)"

# Greetings / acknowledgements that are never a field value on their own.
# (Extend this list to add more languages.)
_IGNORE_ANSWERS = {
    "hi", "hello", "hey", "salam", "assalam", "assalam o alaikum", "aoa",
    "thanks", "thank you", "thankyou", "shukriya", "ok", "okay", "k",
    "yes", "yeah", "yep", "no", "nope", "hmm", "hmmm", "cancel", "stop",
    "start", "menu", "help", "done", "good", "great", "nice",
}


def _clean_answer(value: str) -> str:
    previous = None
    value = cleanup_value(value)
    while value != previous:
        previous = value
        value = _LEADING_FILLERS.sub("", value).strip()
    return cleanup_value(value)


def _labelled_title(text: str) -> str:
    labelled = re.search(
        rf"\b(?:topic|title|name|subject|message)\b\s*(?:name|is|:)?\s*(?P<v>.+?){_VALUE_STOP}",
        text,
        re.IGNORECASE,
    )
    return _clean_answer(labelled.group("v")) if labelled else ""


def extract_title_answer(text: str, whole_if_bare: bool) -> str:
    labelled = _labelled_title(text)
    if labelled:
        return labelled
    if (
        whole_if_bare
        and normalize_spaces(text).lower() not in _IGNORE_ANSWERS
        and not _looks_like_date(text)
        and not text.strip().isdigit()
        and not re.search(r"\bmarks?\b|\bpoints?\b", text, re.IGNORECASE)
    ):
        return _clean_answer(text)
    return ""


def _labelled_deadline(text: str) -> str:
    labelled = re.search(
        rf"\b(?:deadline|due\s*date|due|submit by|last date)\b\s*(?:is|:|by)?\s*(?P<v>.+?){_VALUE_STOP}",
        text,
        re.IGNORECASE,
    )
    return _clean_answer(labelled.group("v")) if labelled else ""


def extract_deadline_answer(text: str) -> str:
    labelled = _labelled_deadline(text)
    if labelled:
        return labelled
    # Bare date / time answer, e.g. "7/7/2026 5pm" or "tomorrow 5pm".
    if _looks_like_date(text):
        return normalize_spaces(text)
    return ""


def _looks_like_date(text: str) -> bool:
    lowered = text.lower()
    if parse_date(lowered, date(2000, 1, 1)) is not None:
        return True
    return bool(re.search(r"\btomorrow\b|\bkal\b|\btoday\b|\baaj\b", lowered))


def fill_missing_text_fields(
    command: ParsedCommand, text: str, allow_bare_title: bool = True
) -> ParsedCommand:
    """Return ``command`` with any still-missing text fields taken from ``text``.

    Course resolution is handled by the caller (it needs the teacher's real
    class list), so this covers title/topic, deadline and marks only.
    ``allow_bare_title`` lets the caller suppress the "treat the whole message as
    the title" fallback when the same message was already used to fill the class.
    """
    text = normalize_spaces(text)
    missing = set(command.missing_fields)
    updates: dict[str, object] = {}

    # An explicitly labelled value ("topic is X") overrides what we had; a bare
    # answer only fills a field that is still missing.
    labelled_title = _labelled_title(text)
    if labelled_title:
        updates["title"] = labelled_title
    elif not command.title and (missing & {"title", "topic", "message"}):
        title = extract_title_answer(text, whole_if_bare=allow_bare_title)
        if title:
            updates["title"] = title

    labelled_deadline = _labelled_deadline(text)
    if labelled_deadline:
        updates["deadline"] = labelled_deadline
    elif not command.deadline and "deadline" in missing:
        deadline = extract_deadline_answer(text)
        if deadline:
            updates["deadline"] = deadline

    if command.marks is None:
        marks = extract_inline_marks(text)
        if marks is not None:
            updates["marks"] = marks

    if not updates:
        return command
    return replace(command, **updates)


def recompute_missing(command: ParsedCommand) -> ParsedCommand:
    """Rebuild ``missing_fields`` for a command after new values were merged in."""
    missing: list[str] = []
    if not command.course:
        missing.append("course")

    title_label = "topic" if command.intent == "ai_generate" else (
        "message" if command.intent == "announcement" else "title"
    )
    if not command.title:
        missing.append(title_label)

    needs_deadline = command.intent == "assignment" or (
        command.intent == "ai_generate" and command.generated_kind in {"assignment", "quiz"}
    )
    if needs_deadline and not command.deadline:
        missing.append("deadline")

    return replace(command, missing_fields=missing)
