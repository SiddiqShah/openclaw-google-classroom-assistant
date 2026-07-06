from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class ParsedDeadline:
    due_date: dict[str, int]
    due_time: dict[str, int]


def parse_deadline(value: str, now: datetime | None = None) -> ParsedDeadline:
    now = now or datetime.now()
    text = value.strip().lower()

    parsed_date = parse_date(text, now.date())
    parsed_time = parse_time(text)
    if parsed_date is None:
        raise ValueError(f"Could not understand deadline date: {value}")
    if parsed_time is None:
        parsed_time = time(23, 59)

    return ParsedDeadline(
        due_date={"year": parsed_date.year, "month": parsed_date.month, "day": parsed_date.day},
        due_time={"hours": parsed_time.hour, "minutes": parsed_time.minute},
    )


def parse_date(text: str, today: date) -> date | None:
    iso = re.search(r"(?P<year>20\d{2})-(?P<month>\d{1,2})-(?P<day>\d{1,2})", text)
    if iso:
        return date(int(iso.group("year")), int(iso.group("month")), int(iso.group("day")))

    numeric = parse_numeric_date(text)
    if numeric is not None:
        return numeric

    month_name = re.search(
        r"(?P<day>\d{1,2})\s+(?P<month>[a-z]+)(?:\s+(?P<year>20\d{2}))?",
        text,
    )
    if month_name and month_name.group("month") in MONTHS:
        year = int(month_name.group("year") or today.year)
        candidate = date(year, MONTHS[month_name.group("month")], int(month_name.group("day")))
        if candidate < today and month_name.group("year") is None:
            candidate = date(year + 1, candidate.month, candidate.day)
        return candidate

    if "tomorrow" in text or "kal" in text:
        return today + timedelta(days=1)

    for name, weekday in WEEKDAYS.items():
        if name in text:
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    return None


def parse_numeric_date(text: str) -> date | None:
    """Parse slash / dash numeric dates like 7/7/2026, 07-07-2026, 2026/7/7.

    Day-first is assumed (the common local convention), but the parser
    disambiguates when one field is clearly out of range for a month.
    """
    ymd = re.search(r"\b(?P<year>20\d{2})[/.](?P<month>\d{1,2})[/.](?P<day>\d{1,2})\b", text)
    if ymd:
        return _safe_date(int(ymd.group("year")), int(ymd.group("month")), int(ymd.group("day")))

    dmy = re.search(r"\b(?P<a>\d{1,2})[/\-.](?P<b>\d{1,2})[/\-.](?P<year>\d{2,4})\b", text)
    if not dmy:
        return None

    a = int(dmy.group("a"))
    b = int(dmy.group("b"))
    year = int(dmy.group("year"))
    if year < 100:
        year += 2000

    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        day, month = b, a
    else:
        day, month = a, b  # default: day-first
    return _safe_date(year, month, day)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_time(text: str) -> time | None:
    meridiem = re.search(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)", text)
    if meridiem:
        hour = int(meridiem.group("hour"))
        minute = int(meridiem.group("minute") or 0)
        if meridiem.group("ampm") == "pm" and hour != 12:
            hour += 12
        if meridiem.group("ampm") == "am" and hour == 12:
            hour = 0
        return time(hour, minute)

    clock = re.search(r"\b(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\b", text)
    if clock:
        return time(int(clock.group("hour")), int(clock.group("minute")))

    return None
