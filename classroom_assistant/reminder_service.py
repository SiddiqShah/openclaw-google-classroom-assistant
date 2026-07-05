from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .access_control import normalize_phone
from .database import Database


@dataclass(frozen=True)
class ReminderWindow:
    now: datetime
    days: int

    @property
    def until(self) -> datetime:
        return self.now + timedelta(days=self.days)


class ReminderService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def render_upcoming_deadlines(
        self,
        phone: str,
        days: int = 7,
        now: datetime | None = None,
    ) -> str:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            return "Teacher phone is not authorized."

        window = ReminderWindow(now=now or datetime.now(), days=days)
        assignments = self.database.upcoming_assignments(
            teacher_id=int(teacher["id"]),
            now_iso=window.now.strftime("%Y-%m-%d %H:%M"),
            until_iso=window.until.strftime("%Y-%m-%d %H:%M"),
        )
        if not assignments:
            return f"No assignment deadlines found in the next {days} days."

        lines = [f"Upcoming deadlines in the next {days} days:", ""]
        for assignment in assignments:
            due_at = self._parse_due_at(str(assignment["due_at"]))
            course = assignment.get("course_name") or assignment.get("google_course_id")
            label = self._relative_label(due_at, window.now)
            lines.append(
                f"- {assignment['title']} | {course} | {label} at {due_at.strftime('%d %b %Y, %I:%M %p')}"
            )
        return "\n".join(lines)

    def render_due_today(self, phone: str, now: datetime | None = None) -> str:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            return "Teacher phone is not authorized."

        current = now or datetime.now()
        end_of_day = current.replace(hour=23, minute=59, second=0, microsecond=0)
        assignments = self.database.upcoming_assignments(
            teacher_id=int(teacher["id"]),
            now_iso=current.strftime("%Y-%m-%d %H:%M"),
            until_iso=end_of_day.strftime("%Y-%m-%d %H:%M"),
        )
        if not assignments:
            return "No assignments are due today."

        lines = ["Assignments due today:", ""]
        for assignment in assignments:
            due_at = self._parse_due_at(str(assignment["due_at"]))
            course = assignment.get("course_name") or assignment.get("google_course_id")
            lines.append(f"- {assignment['title']} | {course} | {due_at.strftime('%I:%M %p')}")
        return "\n".join(lines)

    def _parse_due_at(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")

    def _relative_label(self, due_at: datetime, now: datetime) -> str:
        due_date = due_at.date()
        today = now.date()
        if due_date == today:
            return "today"
        if due_date == today + timedelta(days=1):
            return "tomorrow"
        days_left = (due_date - today).days
        return f"in {days_left} days"
