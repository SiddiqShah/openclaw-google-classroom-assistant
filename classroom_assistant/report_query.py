"""Detect and resolve reporting / analytics questions from free-form teacher text.

Teachers phrase things differently ("assignment report of database class",
"how many students completed the assignment", "kitne students ne submit kiya").
Instead of hard-coding one exact phrase per feature, this module works in two
data-driven layers:

1. Intent detection uses small, clearly labelled keyword *sets* (easy to extend
   with more languages) plus question shape, rather than scattered string checks.
2. Course / assignment resolution matches the words in the message against the
   teacher's *own* Google Classroom courses and recorded assignments. Nothing
   about the class names is hard-coded, so it keeps working when new teachers
   with new classes are added.
"""

from __future__ import annotations

import re

# --- Vocabulary (extend these lists to support more phrasings / languages) ----

# Words that by themselves mean "give me a report / summary".
REPORT_WORDS = {
    "report",
    "summary",
    "status",
    "overview",
    "analytics",
    "stats",
    "statistics",
    "progress",
}

# Signals that a message is about submissions / completion of work.
SUBMISSION_WORDS = {
    "submit",
    "submitted",
    "submission",
    "submissions",
    "complete",
    "completed",
    "completion",
    "done",
    "finished",
    "turned",  # "turned in"
    "pending",
    "missing",
    "late",
    "graded",
    # Roman-Urdu / Hindi variants
    "jama",  # submitted
    "kiya",
    "kiye",
    "mukammal",  # completed
    "diya",
}

# Words hinting the message is about coursework at all.
WORK_WORDS = {
    "assignment",
    "assignments",
    "homework",
    "task",
    "tasks",
    "quiz",
    "quizzes",
    "work",
    "coursework",
}

# Quantity questions: "how many ...", "kitne ...".
QUANTIFIERS = {"how many", "how much", "kitne", "kitni", "kitna"}

# "who ..." style questions.
WHO_WORDS = {"who", "kaun", "kis"}

# Generic words that should never be treated as a class name when matching.
_STOPWORDS = {
    "the", "a", "an", "of", "for", "in", "on", "to", "me", "my", "mein", "meri",
    "class", "classes", "course", "courses", "subject", "subjects", "section",
    "se", "and", "report", "summary", "status", "give", "show", "generate",
    "how", "many", "much", "who", "which", "students", "student", "complete",
    "completed", "submit", "submitted", "submission", "submissions", "assignment",
    "assignments", "homework", "task", "did", "have", "has", "is", "are", "do",
    "does", "kitne", "kitni", "kaun", "kaun", "kis", "ne", "ka", "ki", "ke",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t]


def _contains_any(text: str, words: set[str]) -> bool:
    tokens = set(_tokens(text))
    lowered = text.lower()
    for word in words:
        if " " in word:
            if word in lowered:
                return True
        elif word in tokens:
            return True
    return False


def is_report_query(text: str) -> bool:
    """Return True when the message asks for a submission/completion report.

    Kept deliberately broad so different wordings resolve to the same feature,
    but narrow enough that it never swallows a genuine "create assignment"
    command (those carry a create verb and no report / question shape).
    """
    lowered = text.lower()

    # Explicit report/summary request, e.g. "assignment report of database class".
    if _contains_any(lowered, REPORT_WORDS) and _contains_any(lowered, WORK_WORDS | SUBMISSION_WORDS):
        return True

    has_submission_signal = _contains_any(lowered, SUBMISSION_WORDS) or _contains_any(lowered, WORK_WORDS)

    # Quantity questions, e.g. "how many students completed the assignment".
    if _contains_any(lowered, QUANTIFIERS) and has_submission_signal:
        return True

    # "who submitted ...", "who has not turned in ...".
    if _contains_any(lowered, WHO_WORDS) and _contains_any(lowered, SUBMISSION_WORDS):
        return True

    return False


def _significant(name: str) -> list[str]:
    return [t for t in _tokens(name) if t not in _STOPWORDS and len(t) >= 3]


def _token_matches(target_token: str, text_tokens: set[str]) -> bool:
    for token in text_tokens:
        if token == target_token:
            return True
        if len(token) >= 4 and len(target_token) >= 4 and (token in target_token or target_token in token):
            return True
    return False


def _acronym(name: str) -> str:
    return "".join(token[0] for token in _significant(name))


def resolve_named(candidates: list, text: str, name_of) -> object | None:
    """Pick the candidate whose name best overlaps the words in ``text``.

    ``name_of`` maps a candidate to its display name. Matching is token based and
    tolerant of singular/plural ("database" vs "Databases") and of acronyms the
    teacher forms from the class name itself ("OS" for Operating System, "SRE"
    for Software Requirement Engineering). Everything is derived from the
    teacher's real class / assignment names, so nothing is hard-coded.
    """
    text_tokens = set(_tokens(text))
    best = None
    best_score = 0
    for candidate in candidates:
        name = name_of(candidate)
        score = sum(1 for token in _significant(name) if _token_matches(token, text_tokens))
        acronym = _acronym(name)
        if len(acronym) >= 2 and acronym in text_tokens:
            score += 2
        if score > best_score:
            best_score = score
            best = candidate
    return best if best_score > 0 else None
