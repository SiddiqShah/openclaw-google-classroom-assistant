from __future__ import annotations

import json
from dataclasses import asdict
from dataclasses import replace
from pathlib import Path

from .access_control import normalize_phone
from .classroom_api import ClassroomService
from .command_parser import ParsedCommand, render_preview
from .content_generator import ContentGenerator
from .conversation import fill_missing_text_fields, recompute_missing
from .database import Database
from .drive_service import DriveService
from .file_receiver import FileReceiver
from .file_receiver import StagedFile
from .google_auth import GoogleAuthError
from .local_file_search import LocalFileSearch, LocalFileSearchError
from .report_query import resolve_named


class WorkflowService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.classroom = ClassroomService(database)
        self.drive = DriveService(database)
        self.file_receiver = FileReceiver(database, project_root=Path(__file__).resolve().parents[1])
        self.file_search = LocalFileSearch()
        self.generator = ContentGenerator()

    def handle_command(self, phone: str, command: ParsedCommand, text: str = "") -> str:
        """Entry point for a freshly parsed command.

        Resolves the class dynamically from the teacher's real course list, then
        either builds a preview (all details present) or remembers the request as
        a draft and asks for what is still missing.
        """
        # A fresh command abandons any half-finished one from before.
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is not None:
            stale = self.database.get_awaiting_action(int(teacher["id"]))
            if stale is not None:
                self.database.update_pending_action_status(int(stale["id"]), "expired")

        command = self._resolve_course_from_text(phone, command, text)
        command = recompute_missing(command)
        if command.is_complete:
            return self.save_preview(phone, command)
        self._store_draft(phone, command)
        return self._ask_for_missing(command)

    def continue_draft(self, phone: str, text: str) -> str | None:
        """Merge a follow-up message into a waiting draft, if there is one.

        Returns None when there is no draft or the message added nothing, so the
        caller can fall back to normal routing.
        """
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            return None
        draft_row = self.database.get_awaiting_action(int(teacher["id"]))
        if draft_row is None:
            return None

        command = self._command_from_payload(json.loads(str(draft_row["payload_json"])))

        # Resolve the class first: if this reply supplied the class, a bare
        # message should not also be taken as the title.
        with_course = self._resolve_course_from_text(phone, command, text)
        course_filled = not command.course and bool(with_course.course)
        with_course = recompute_missing(with_course)

        merged = fill_missing_text_fields(with_course, text, allow_bare_title=not course_filled)
        if not self._added_detail(command, merged):
            return None  # nothing new -> not an answer to our question

        merged = recompute_missing(merged)
        self.database.update_pending_action_status(int(draft_row["id"]), "superseded")
        if merged.is_complete:
            return self.save_preview(phone, merged)
        self._store_draft(phone, merged)
        return self._ask_for_missing(merged)

    def _added_detail(self, before: ParsedCommand, after: ParsedCommand) -> bool:
        return (
            before.course != after.course
            or before.title != after.title
            or before.deadline != after.deadline
            or before.marks != after.marks
        )

    def _resolve_course_from_text(self, phone: str, command: ParsedCommand, text: str) -> ParsedCommand:
        try:
            courses = self.classroom.list_courses(phone=phone, sync=False)
        except GoogleAuthError:
            return command
        if not courses:
            return command

        # Leave explicit multi-class and "all classes" selections untouched.
        if command.course and len(split_course_selectors(command.course)) > 1:
            return command
        if command.course.strip().lower() in {"all", "all classes", "all courses"}:
            return command

        match = None
        if command.course:
            match = resolve_named(courses, command.course, name_of=lambda c: c.display_name)
        if match is None and text:
            match = resolve_named(courses, text, name_of=lambda c: c.display_name)
        if match is not None:
            return replace(command, course=match.display_name)
        return command

    def _store_draft(self, phone: str, command: ParsedCommand) -> None:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        self.database.create_draft_action(
            teacher_id=int(teacher["id"]),
            action_type=command.intent,
            payload_json=json.dumps(asdict(command)),
        )

    def _command_from_payload(self, payload: dict) -> ParsedCommand:
        fields = {
            "intent": str(payload.get("intent", "")),
            "course": str(payload.get("course", "")),
            "title": str(payload.get("title", "")),
            "deadline": str(payload.get("deadline", "")),
            "marks": payload.get("marks"),
            "description": str(payload.get("description", "")),
            "attachment_query": str(payload.get("attachment_query", "")),
            "generated_kind": str(payload.get("generated_kind", "")),
            "missing_fields": list(payload.get("missing_fields", [])),
        }
        return ParsedCommand(**fields)

    def _ask_for_missing(self, command: ParsedCommand) -> str:
        labels = {
            "course": "class name",
            "title": "assignment title",
            "topic": "topic",
            "message": "announcement message",
            "deadline": "deadline (e.g. 7 July 2026 5 PM)",
        }
        wanted = ", ".join(labels.get(field, field) for field in command.missing_fields)

        known = []
        if command.course:
            known.append(f"Class: {command.course}")
        if command.title:
            known.append(f"Topic: {command.title}")
        if command.deadline:
            known.append(f"Deadline: {command.deadline}")
        if command.marks is not None:
            known.append(f"Marks: {command.marks}")

        lines = []
        if known:
            lines.append("Got it so far:")
            lines.extend(f"- {item}" for item in known)
            lines.append("")
        lines.append(f"Please also send the {wanted}.")
        return "\n".join(lines)

    def save_preview(self, phone: str, command: ParsedCommand) -> str:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        if command.intent == "ai_generate":
            draft = self.generator.generate(command.generated_kind, command.title, command.marks)
            command = replace(
                command,
                title=draft.title,
                marks=draft.marks,
                description=draft.instructions,
            )

        courses = self._resolve_courses(phone, command.course)
        payload = asdict(command)
        payload["courses"] = [
            {"id": course.id, "display_name": course.display_name}
            for course in courses
        ]
        payload["course_id"] = courses[0].id
        payload["course_display_name"] = ", ".join(course.display_name for course in courses)
        file_name = ""
        if command.attachment_query:
            if command.attachment_query.lower().startswith("drive:"):
                drive_query = command.attachment_query.split(":", 1)[1].strip()
                drive_file = self.drive.find_file_by_name_in_folders(
                    phone,
                    drive_query,
                    self._drive_folder_candidates_for_payload(phone, payload),
                )
                payload["drive_file_id"] = drive_file.id
                payload["drive_file_name"] = drive_file.name
                payload["drive_file_link"] = drive_file.web_view_link
                file_name = f"{drive_file.name} (Google Drive)"
            else:
                try:
                    match = self.file_search.find_one(command.attachment_query)
                    staged = self.file_receiver.receive(phone, match.path)
                except LocalFileSearchError as exc:
                    raise GoogleAuthError(str(exc)) from exc
                payload["staged_file_id"] = staged.id
                payload["staged_file_name"] = staged.original_name
                payload["staged_file_path"] = str(staged.staged_path)
                payload["staged_file_mime_type"] = staged.mime_type
                payload["staged_file_size_bytes"] = staged.size_bytes
                file_name = staged.original_name
        self.database.create_pending_action(
            teacher_id=int(teacher["id"]),
            action_type=command.intent,
            payload_json=json.dumps(payload),
        )
        return render_preview(command, selected_course=payload["course_display_name"], file_name=file_name)

    def handle_confirmation(self, phone: str, reply: str) -> str | None:
        normalized = reply.strip().lower()
        if normalized not in {"1", "2", "3", "publish", "draft", "cancel"}:
            return None

        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        pending = self.database.get_latest_pending_action(int(teacher["id"]))
        if pending is None:
            return None

        if normalized in {"3", "cancel"}:
            self.database.update_pending_action_status(int(pending["id"]), "cancelled")
            return "Cancelled. Nothing was posted to Google Classroom."

        payload = json.loads(str(pending["payload_json"]))
        action_type = str(pending["action_type"])
        if action_type == "assignment":
            return self._confirm_assignment(phone, int(teacher["id"]), int(pending["id"]), payload, normalized)
        if action_type == "ai_generate":
            return self._confirm_generated_draft(phone, int(teacher["id"]), int(pending["id"]), payload, normalized)
        if action_type == "material":
            return self._confirm_material(phone, int(teacher["id"]), int(pending["id"]), payload, normalized)
        if action_type == "announcement":
            return self._confirm_announcement(phone, int(pending["id"]), payload, normalized)
        return "This pending action is not supported anymore. Please send the details again."

    def _confirm_assignment(
        self,
        phone: str,
        teacher_id: int,
        pending_id: int,
        payload: dict,
        normalized: str,
    ) -> str:
        state = "PUBLISHED" if normalized in {"1", "publish"} else "DRAFT"
        uploaded = self._upload_staged_file_if_present(teacher_id, payload)
        drive_file_id = uploaded.id if uploaded else str(payload.get("drive_file_id", ""))
        file_name = uploaded.name if uploaded else str(payload.get("drive_file_name", ""))
        created_items = []
        for course in self._payload_courses(payload):
            created_items.append(
                self.classroom.create_assignment(
                    phone=phone,
                    course_id=str(course["id"]),
                    title=str(payload["title"]),
                    description=str(payload.get("description", "")),
                    deadline=str(payload["deadline"]),
                    max_points=payload.get("marks"),
                    state=state,
                    drive_file_id=drive_file_id,
                    share_mode=str(payload.get("share_mode", "VIEW")),
                )
            )
        self.database.update_pending_action_status(pending_id, "completed")

        action = "posted" if state == "PUBLISHED" else "saved as draft"
        file_line = f"\nFile: {file_name}" if file_name else ""
        posted_lines = "\n".join(
            f"- {course['display_name']}: {created['title']}"
            for course, created in zip(self._payload_courses(payload), created_items)
        )
        return (
            f"Done. Assignment {action} in {len(created_items)} class(es).\n"
            f"{posted_lines}{file_line}"
        )

    def _confirm_material(
        self,
        phone: str,
        teacher_id: int,
        pending_id: int,
        payload: dict,
        normalized: str,
    ) -> str:
        if normalized not in {"1", "publish", "post"}:
            self.database.update_pending_action_status(pending_id, "cancelled")
            return "Cancelled. Nothing was posted to Google Classroom."

        uploaded = self._upload_staged_file_if_present(teacher_id, payload)
        drive_file_id = uploaded.id if uploaded else str(payload.get("drive_file_id", ""))
        file_name = uploaded.name if uploaded else str(payload.get("drive_file_name", ""))
        created_items = []
        for course in self._payload_courses(payload):
            created_items.append(
                self.classroom.create_material(
                    phone=phone,
                    course_id=str(course["id"]),
                    title=str(payload["title"]),
                    description=str(payload.get("description", "")),
                    state="PUBLISHED",
                    drive_file_id=drive_file_id,
                )
            )
        self.database.update_pending_action_status(pending_id, "completed")

        file_line = f"\nFile: {file_name}" if file_name else ""
        posted_lines = "\n".join(
            f"- {course['display_name']}: {created['title']}"
            for course, created in zip(self._payload_courses(payload), created_items)
        )
        return (
            f"Done. Study material posted in {len(created_items)} class(es).\n"
            f"{posted_lines}{file_line}"
        )

    def _confirm_announcement(
        self,
        phone: str,
        pending_id: int,
        payload: dict,
        normalized: str,
    ) -> str:
        if normalized not in {"1", "publish", "post"}:
            self.database.update_pending_action_status(pending_id, "cancelled")
            return "Cancelled. Nothing was posted to Google Classroom."

        created_items = []
        for course in self._payload_courses(payload):
            created_items.append(
                self.classroom.create_announcement(
                    phone=phone,
                    course_id=str(course["id"]),
                    text=str(payload["title"]),
                    state="PUBLISHED",
                )
            )
        self.database.update_pending_action_status(pending_id, "completed")

        posted_lines = "\n".join(
            f"- {course['display_name']}: {created['text']}"
            for course, created in zip(self._payload_courses(payload), created_items)
        )
        return (
            f"Done. Announcement posted in {len(created_items)} class(es).\n"
            f"{posted_lines}"
        )

    def _confirm_generated_draft(
        self,
        phone: str,
        teacher_id: int,
        pending_id: int,
        payload: dict,
        normalized: str,
    ) -> str:
        if normalized in {"3", "cancel"}:
            self.database.update_pending_action_status(pending_id, "cancelled")
            return "Cancelled. Nothing was posted to Google Classroom."
        if payload.get("generated_kind") == "rubric":
            return self._confirm_generated_rubric(phone, pending_id, payload, normalized)
        return self._confirm_assignment(phone, teacher_id, pending_id, payload, normalized)

    def _confirm_generated_rubric(
        self,
        phone: str,
        pending_id: int,
        payload: dict,
        normalized: str,
    ) -> str:
        state = "PUBLISHED" if normalized in {"1", "publish"} else "DRAFT"
        created_items = []
        for course in self._payload_courses(payload):
            created_items.append(
                self.classroom.create_material(
                    phone=phone,
                    course_id=str(course["id"]),
                    title=str(payload["title"]),
                    description=str(payload.get("description", "")),
                    state=state,
                    drive_file_id="",
                )
            )
        self.database.update_pending_action_status(pending_id, "completed")
        action = "posted" if state == "PUBLISHED" else "saved as draft"
        posted_lines = "\n".join(
            f"- {course['display_name']}: {created['title']}"
            for course, created in zip(self._payload_courses(payload), created_items)
        )
        return f"Done. Rubric {action} in {len(created_items)} class(es).\n{posted_lines}"

    def _upload_staged_file_if_present(self, teacher_id: int, payload: dict):
        if not payload.get("staged_file_id"):
            return None
        staged = StagedFile(
            id=int(payload["staged_file_id"]),
            original_name=str(payload.get("staged_file_name", "attachment")),
            staged_path=Path(str(payload["staged_file_path"])),
            mime_type=str(payload.get("staged_file_mime_type", "")),
            size_bytes=int(payload.get("staged_file_size_bytes", 0)),
        )
        return self.drive.upload_staged_file(
            teacher_id=teacher_id,
            staged=staged,
            course_folder_name=str(payload.get("course_display_name", "")),
        )

    def _resolve_courses(self, phone: str, course_name: str):
        if course_name:
            if course_name.strip().lower() in {"all", "all classes", "all courses"}:
                courses = self.classroom.list_courses(phone, sync=False)
                if not courses:
                    raise GoogleAuthError("No active Google Classroom courses found.")
                return courses
            selectors = split_course_selectors(course_name)
            return [self.classroom.select_course(phone, selector) for selector in selectors]
        selected = self.classroom.selected_course(phone)
        if selected is None:
            raise GoogleAuthError("No class selected. Send: Meri classes dikhao")
        return [selected]

    def _payload_courses(self, payload: dict) -> list[dict[str, str]]:
        courses = payload.get("courses")
        if courses:
            return [{"id": str(course["id"]), "display_name": str(course["display_name"])} for course in courses]
        return [{"id": str(payload["course_id"]), "display_name": str(payload["course_display_name"])}]

    def _drive_folder_candidates_for_payload(self, phone: str, payload: dict) -> list[str]:
        result = []
        for course in self._payload_courses(payload):
            for candidate in self.drive.folder_candidates_for_course(phone, str(course["display_name"])):
                if candidate and candidate not in result:
                    result.append(candidate)
        return result


def split_course_selectors(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned:
        return []
    if cleaned.lower() in {"all", "all classes", "all courses"}:
        return [cleaned]
    parts = [
        part.strip()
        for part in cleaned.replace("&", " and ").replace(",", " and ").split(" and ")
        if part.strip()
    ]
    return parts or [cleaned]

