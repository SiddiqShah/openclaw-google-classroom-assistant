from __future__ import annotations

from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True)
class Teacher:
    id: int
    name: str
    phone: str
    google_email: str


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    message: str
    teacher: Teacher | None = None


class AccessController:
    def __init__(self, database: Database) -> None:
        self.database = database

    def add_teacher(self, name: str, phone: str, google_email: str = "") -> Teacher:
        normalized_phone = normalize_phone(phone)
        teacher_id = self.database.upsert_teacher(
            name=name.strip(),
            phone=normalized_phone,
            google_email=google_email.strip().lower(),
        )
        teacher = self.database.get_teacher_by_id(teacher_id)
        if teacher is None:
            raise RuntimeError("Teacher was not saved.")
        return Teacher(**teacher)

    def list_teachers(self) -> list[Teacher]:
        return [Teacher(**row) for row in self.database.list_teachers()]

    def remove_teacher_phone(self, phone: str) -> bool:
        return self.database.deactivate_teacher_phone(normalize_phone(phone))

    def authorize(self, phone: str, channel_type: str = "dm") -> AuthorizationResult:
        if channel_type != "dm":
            return AuthorizationResult(
                allowed=False,
                message=(
                    "Sorry, Classroom Assistant works in private teacher DM only. "
                    "Please message the bot directly."
                ),
            )

        normalized_phone = normalize_phone(phone)
        row = self.database.get_teacher_by_phone(normalized_phone)
        if row is None:
            return AuthorizationResult(
                allowed=False,
                message=(
                    "Sorry, your number is not authorized to use this Classroom Assistant. "
                    "Please contact school admin."
                ),
            )

        teacher = Teacher(**row)
        return AuthorizationResult(
            allowed=True,
            message=f"Welcome, {teacher.name}. You are authorized.",
            teacher=teacher,
        )

    def handle_message(self, phone: str, text: str, channel_type: str = "dm") -> str:
        result = self.authorize(phone=phone, channel_type=channel_type)
        self.database.log_access_attempt(
            phone=normalize_phone(phone),
            channel_type=channel_type,
            message=text,
            allowed=result.allowed,
        )

        if not result.allowed:
            return ""

        return (
            f"{result.message}\n\n"
            "What do you want to do?\n\n"
            "1. Create Assignment\n"
            "2. Upload Study Material\n"
            "3. Post Announcement\n"
            "4. Check Deadlines\n"
            "5. Submission Report"
        )


def normalize_phone(phone: str) -> str:
    cleaned = "".join(char for char in phone if char.isdigit())
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    if len(cleaned) < 8:
        raise ValueError("Phone number is too short.")
    return f"+{cleaned}"
