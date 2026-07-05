from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .access_control import normalize_phone
from .database import Database
from .date_parser import parse_deadline
from .google_auth import GoogleAuthError, read_authorized_user_token


@dataclass(frozen=True)
class Course:
    id: str
    name: str
    section: str
    state: str

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.section})" if self.section else self.name


class ClassroomService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def sync_courses(self, phone: str) -> list[Course]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        service = self._build_google_service(int(teacher["id"]))
        response = (
            service.courses()
            .list(teacherId="me", courseStates=["ACTIVE"], pageSize=50)
            .execute()
        )

        courses = [
            Course(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                section=str(item.get("section", "")),
                state=str(item.get("courseState", "")),
            )
            for item in response.get("courses", [])
        ]
        self.database.replace_courses(
            int(teacher["id"]),
            [
                {
                    "id": course.id,
                    "name": course.name,
                    "section": course.section,
                    "state": course.state,
                }
                for course in courses
            ],
        )
        return courses

    def list_cached_courses(self, phone: str) -> list[Course]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        return [
            Course(
                id=str(row["id"]),
                name=str(row["name"]),
                section=str(row["section"]),
                state=str(row["state"]),
            )
            for row in self.database.list_courses_by_teacher_id(int(teacher["id"]))
        ]

    def list_courses(self, phone: str, sync: bool = False) -> list[Course]:
        if sync:
            return self.sync_courses(phone)
        cached = self.list_cached_courses(phone)
        return cached or self.sync_courses(phone)

    def select_course(self, phone: str, selector: str) -> Course:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        courses = self.list_cached_courses(phone)
        if not courses:
            courses = self.sync_courses(phone)
        if not courses:
            raise GoogleAuthError("No active Google Classroom courses found.")

        selected = self._match_course(courses, selector)
        self.database.select_course(int(teacher["id"]), selected.id)
        return selected

    def selected_course(self, phone: str) -> Course | None:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        row = self.database.get_selected_course(int(teacher["id"]))
        if row is None:
            return None
        return Course(
            id=str(row["id"]),
            name=str(row["name"]),
            section=str(row["section"]),
            state=str(row["state"]),
        )

    def _match_course(self, courses: list[Course], selector: str) -> Course:
        cleaned = selector.strip()
        if cleaned.isdigit():
            index = int(cleaned)
            if 1 <= index <= len(courses):
                return courses[index - 1]
            raise GoogleAuthError(f"Class number {index} is not in the course list.")

        lowered = cleaned.lower()
        matches = [
            course
            for course in courses
            if lowered in course.name.lower() or lowered in course.display_name.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            options = "\n".join(
                f"{index}. {course.display_name}" for index, course in enumerate(matches, start=1)
            )
            raise GoogleAuthError(f"I found multiple matching classes:\n{options}\nPlease reply with the class number.")
        raise GoogleAuthError(f"I could not find a class matching: {selector}")

    def create_assignment(
        self,
        phone: str,
        course_id: str,
        title: str,
        description: str,
        deadline: str,
        max_points: int | None,
        state: str,
        drive_file_id: str = "",
        share_mode: str = "VIEW",
    ) -> dict[str, str]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        due = parse_deadline(deadline)
        body: dict[str, object] = {
            "title": title,
            "description": description,
            "workType": "ASSIGNMENT",
            "state": state,
            "dueDate": due.due_date,
            "dueTime": due.due_time,
        }
        if max_points is not None:
            body["maxPoints"] = max_points
        if drive_file_id:
            body["materials"] = [
                {
                    "driveFile": {
                        "driveFile": {"id": drive_file_id},
                        "shareMode": share_mode,
                    }
                }
            ]

        service = self._build_google_service(int(teacher["id"]))
        created = service.courses().courseWork().create(courseId=course_id, body=body).execute()
        self.database.record_assignment(
            teacher_id=int(teacher["id"]),
            google_course_id=course_id,
            google_coursework_id=str(created.get("id", "")),
            title=str(created.get("title", title)),
            state=str(created.get("state", state)),
            alternate_link=str(created.get("alternateLink", "")),
            deadline_text=deadline,
            due_at=self._due_datetime_iso(due),
        )
        return {
            "id": str(created.get("id", "")),
            "title": str(created.get("title", title)),
            "state": str(created.get("state", state)),
            "alternateLink": str(created.get("alternateLink", "")),
        }

    def create_material(
        self,
        phone: str,
        course_id: str,
        title: str,
        description: str,
        state: str,
        drive_file_id: str = "",
    ) -> dict[str, str]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        body: dict[str, object] = {
            "title": title,
            "description": description,
            "state": state,
        }
        if drive_file_id:
            body["materials"] = [
                {
                    "driveFile": {
                        "driveFile": {"id": drive_file_id},
                        "shareMode": "VIEW",
                    }
                }
            ]

        service = self._build_google_service(int(teacher["id"]))
        created = service.courses().courseWorkMaterials().create(courseId=course_id, body=body).execute()
        self.database.record_material(
            teacher_id=int(teacher["id"]),
            google_course_id=course_id,
            google_material_id=str(created.get("id", "")),
            title=str(created.get("title", title)),
            state=str(created.get("state", state)),
            alternate_link=str(created.get("alternateLink", "")),
        )
        return {
            "id": str(created.get("id", "")),
            "title": str(created.get("title", title)),
            "state": str(created.get("state", state)),
            "alternateLink": str(created.get("alternateLink", "")),
        }

    def create_announcement(
        self,
        phone: str,
        course_id: str,
        text: str,
        state: str,
    ) -> dict[str, str]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        body: dict[str, object] = {
            "text": text,
            "state": state,
        }
        service = self._build_google_service(int(teacher["id"]))
        created = service.courses().announcements().create(courseId=course_id, body=body).execute()
        self.database.record_announcement(
            teacher_id=int(teacher["id"]),
            google_course_id=course_id,
            google_announcement_id=str(created.get("id", "")),
            text=str(created.get("text", text)),
            state=str(created.get("state", state)),
            alternate_link=str(created.get("alternateLink", "")),
        )
        return {
            "id": str(created.get("id", "")),
            "text": str(created.get("text", text)),
            "state": str(created.get("state", state)),
            "alternateLink": str(created.get("alternateLink", "")),
        }

    def list_submissions(self, phone: str, course_id: str, coursework_id: str) -> list[dict[str, str]]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        service = self._build_google_service(int(teacher["id"]))
        submissions: list[dict[str, str]] = []
        page_token = ""
        try:
            while True:
                response = (
                    service.courses()
                    .courseWork()
                    .studentSubmissions()
                    .list(
                        courseId=course_id,
                        courseWorkId=coursework_id,
                        pageSize=100,
                        pageToken=page_token or None,
                    )
                    .execute()
                )
                submissions.extend(
                    {
                        "id": str(item.get("id", "")),
                        "userId": str(item.get("userId", "")),
                        "state": str(item.get("state", "")),
                        "late": str(bool(item.get("late", False))),
                    }
                    for item in response.get("studentSubmissions", [])
                )
                page_token = str(response.get("nextPageToken", ""))
                if not page_token:
                    break
        except Exception as exc:
            raise GoogleAuthError(
                "Google Classroom could not return submissions for this assignment yet. "
                "Make sure the assignment is published in a class with students."
            ) from exc
        return submissions

    def list_students(self, phone: str, course_id: str) -> dict[str, str]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        service = self._build_google_service(int(teacher["id"]))
        students: dict[str, str] = {}
        page_token = ""
        try:
            while True:
                request = service.courses().students().list(
                    courseId=course_id,
                    pageSize=100,
                    pageToken=page_token or None,
                )
                response = request.execute()
                for item in response.get("students", []):
                    profile = item.get("profile", {})
                    name = profile.get("name", {})
                    full_name = str(name.get("fullName", "")).strip()
                    email = str(profile.get("emailAddress", "")).strip()
                    user_id = str(item.get("userId", ""))
                    label = full_name or email or user_id
                    if user_id:
                        students[user_id] = label
                page_token = str(response.get("nextPageToken", ""))
                if not page_token:
                    break
        except Exception as exc:
            raise GoogleAuthError(
                "Google Classroom could not return the student roster. "
                "Run google-login again and approve roster access."
            ) from exc
        return students

    def _build_google_service(self, teacher_id: int):
        token = self.database.get_google_token_by_teacher_id(teacher_id)
        if token is None:
            raise GoogleAuthError("Google account is not connected yet.")

        token_path = Path(str(token["token_path"]))
        if not token_path.exists():
            raise GoogleAuthError("Google token file is missing. Run google-login again.")

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise GoogleAuthError(
                "Google API dependencies are missing. Run: "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        scopes = str(token["scopes"]).split()
        credentials = Credentials.from_authorized_user_info(
            json.loads(read_authorized_user_token(token_path)),
            scopes=scopes,
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            from .security import TokenCipher

            TokenCipher().write_token(token_path, credentials.to_json())

        return build("classroom", "v1", credentials=credentials)

    def _due_datetime_iso(self, due) -> str:
        due_date = due.due_date
        due_time = due.due_time
        return datetime(
            int(due_date["year"]),
            int(due_date["month"]),
            int(due_date["day"]),
            int(due_time.get("hours", 23)),
            int(due_time.get("minutes", 59)),
        ).strftime("%Y-%m-%d %H:%M")
