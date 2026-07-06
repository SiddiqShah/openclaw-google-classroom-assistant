from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.executescript(
                """
                create table if not exists teachers (
                    id integer primary key autoincrement,
                    name text not null,
                    google_email text not null default '',
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists teacher_whatsapp_numbers (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    phone text not null unique,
                    is_active integer not null default 1,
                    created_at text not null default current_timestamp
                );

                create table if not exists access_logs (
                    id integer primary key autoincrement,
                    phone text not null,
                    channel_type text not null,
                    message text not null,
                    allowed integer not null,
                    created_at text not null default current_timestamp
                );

                create table if not exists google_oauth_tokens (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    token_path text not null,
                    scopes text not null,
                    connected_email text not null default '',
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp,
                    unique(teacher_id)
                );

                create table if not exists courses (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    google_course_id text not null,
                    name text not null,
                    section text not null default '',
                    state text not null default '',
                    last_synced_at text not null default current_timestamp,
                    unique(teacher_id, google_course_id)
                );

                create table if not exists teacher_course_selection (
                    teacher_id integer primary key references teachers(id) on delete cascade,
                    google_course_id text not null,
                    selected_at text not null default current_timestamp
                );

                create table if not exists pending_actions (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    action_type text not null,
                    payload_json text not null,
                    status text not null default 'pending',
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists assignments (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    google_course_id text not null,
                    google_coursework_id text not null,
                    title text not null,
                    state text not null,
                    alternate_link text not null default '',
                    created_at text not null default current_timestamp
                );

                create table if not exists materials (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    google_course_id text not null,
                    google_material_id text not null,
                    title text not null,
                    state text not null,
                    alternate_link text not null default '',
                    created_at text not null default current_timestamp
                );

                create table if not exists announcements (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    google_course_id text not null,
                    google_announcement_id text not null,
                    text text not null,
                    state text not null,
                    alternate_link text not null default '',
                    created_at text not null default current_timestamp
                );

                create table if not exists staged_files (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    original_name text not null,
                    staged_path text not null,
                    mime_type text not null,
                    size_bytes integer not null,
                    status text not null default 'staged',
                    created_at text not null default current_timestamp
                );

                create table if not exists uploaded_files (
                    id integer primary key autoincrement,
                    teacher_id integer not null references teachers(id) on delete cascade,
                    staged_file_id integer not null references staged_files(id),
                    drive_file_id text not null,
                    drive_web_link text not null default '',
                    original_name text not null,
                    mime_type text not null,
                    created_at text not null default current_timestamp
                );

                create table if not exists error_logs (
                    id integer primary key autoincrement,
                    phone text not null default '',
                    action text not null,
                    error_type text not null,
                    message text not null,
                    created_at text not null default current_timestamp
                );
                """
            )
            self._ensure_column(connection, "assignments", "deadline_text", "text not null default ''")
            self._ensure_column(connection, "assignments", "due_at", "text not null default ''")
            connection.commit()

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        columns = connection.execute(f"pragma table_info({table_name})").fetchall()
        if any(str(column["name"]) == column_name for column in columns):
            return
        connection.execute(f"alter table {table_name} add column {column_name} {definition}")

    def upsert_teacher(self, name: str, phone: str, google_email: str = "") -> int:
        with closing(self.connect()) as connection:
            existing = connection.execute(
                """
                select t.id
                from teachers t
                join teacher_whatsapp_numbers n on n.teacher_id = t.id
                where n.phone = ?
                """,
                (phone,),
            ).fetchone()

            if existing:
                teacher_id = int(existing["id"])
                connection.execute(
                    """
                    update teachers
                    set name = ?, google_email = ?, updated_at = current_timestamp
                    where id = ?
                    """,
                    (name, google_email, teacher_id),
                )
                connection.commit()
                return teacher_id

            cursor = connection.execute(
                "insert into teachers (name, google_email) values (?, ?)",
                (name, google_email),
            )
            teacher_id = int(cursor.lastrowid)
            connection.execute(
                "insert into teacher_whatsapp_numbers (teacher_id, phone) values (?, ?)",
                (teacher_id, phone),
            )
            connection.commit()
            return teacher_id

    def get_teacher_by_id(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select t.id, t.name, n.phone, t.google_email
                from teachers t
                join teacher_whatsapp_numbers n on n.teacher_id = t.id
                where t.id = ? and n.is_active = 1
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_teacher_by_phone(self, phone: str) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select t.id, t.name, n.phone, t.google_email
                from teachers t
                join teacher_whatsapp_numbers n on n.teacher_id = t.id
                where n.phone = ? and n.is_active = 1
                """,
                (phone,),
            ).fetchone()
        return dict(row) if row else None

    def list_teachers(self) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select t.id, t.name, n.phone, t.google_email
                from teachers t
                join teacher_whatsapp_numbers n on n.teacher_id = t.id
                where n.is_active = 1
                order by t.name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def deactivate_teacher_phone(self, phone: str) -> bool:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                update teacher_whatsapp_numbers
                set is_active = 0
                where phone = ? and is_active = 1
                """,
                (phone,),
            )
            connection.commit()
            return cursor.rowcount > 0

    def upsert_google_token(
        self,
        teacher_id: int,
        token_path: str,
        scopes: str,
        connected_email: str = "",
    ) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                insert into google_oauth_tokens (teacher_id, token_path, scopes, connected_email)
                values (?, ?, ?, ?)
                on conflict(teacher_id) do update set
                    token_path = excluded.token_path,
                    scopes = excluded.scopes,
                    connected_email = excluded.connected_email,
                    updated_at = current_timestamp
                """,
                (teacher_id, token_path, scopes, connected_email),
            )
            connection.commit()

    def get_google_token_by_teacher_id(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select teacher_id, token_path, scopes, connected_email, updated_at
                from google_oauth_tokens
                where teacher_id = ?
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def replace_courses(self, teacher_id: int, courses: list[dict[str, str]]) -> None:
        with closing(self.connect()) as connection:
            connection.execute("delete from courses where teacher_id = ?", (teacher_id,))
            connection.executemany(
                """
                insert into courses (teacher_id, google_course_id, name, section, state)
                values (?, ?, ?, ?, ?)
                """,
                [
                    (
                        teacher_id,
                        course["id"],
                        course["name"],
                        course.get("section", ""),
                        course.get("state", ""),
                    )
                    for course in courses
                ],
            )
            connection.commit()

    def list_courses_by_teacher_id(self, teacher_id: int) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select google_course_id as id, name, section, state, last_synced_at
                from courses
                where teacher_id = ?
                order by courses.id
                """,
                (teacher_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def select_course(self, teacher_id: int, google_course_id: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                insert into teacher_course_selection (teacher_id, google_course_id)
                values (?, ?)
                on conflict(teacher_id) do update set
                    google_course_id = excluded.google_course_id,
                    selected_at = current_timestamp
                """,
                (teacher_id, google_course_id),
            )
            connection.commit()

    def get_selected_course(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select c.google_course_id as id, c.name, c.section, c.state, s.selected_at
                from teacher_course_selection s
                join courses c
                  on c.teacher_id = s.teacher_id
                 and c.google_course_id = s.google_course_id
                where s.teacher_id = ?
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_pending_action(self, teacher_id: int, action_type: str, payload_json: str) -> int:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                update pending_actions
                set status = 'expired', updated_at = current_timestamp
                where teacher_id = ? and status = 'pending'
                """,
                (teacher_id,),
            )
            cursor = connection.execute(
                """
                insert into pending_actions (teacher_id, action_type, payload_json)
                values (?, ?, ?)
                """,
                (teacher_id, action_type, payload_json),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def create_draft_action(self, teacher_id: int, action_type: str, payload_json: str) -> int:
        """Store a half-finished command that is waiting for more details."""
        with closing(self.connect()) as connection:
            connection.execute(
                """
                update pending_actions
                set status = 'expired', updated_at = current_timestamp
                where teacher_id = ? and status = 'awaiting'
                """,
                (teacher_id,),
            )
            cursor = connection.execute(
                """
                insert into pending_actions (teacher_id, action_type, payload_json, status)
                values (?, ?, ?, 'awaiting')
                """,
                (teacher_id, action_type, payload_json),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_awaiting_action(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select id, teacher_id, action_type, payload_json, status, created_at
                from pending_actions
                where teacher_id = ? and status = 'awaiting'
                order by id desc
                limit 1
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_pending_action(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select id, teacher_id, action_type, payload_json, status, created_at
                from pending_actions
                where teacher_id = ? and status = 'pending'
                order by id desc
                limit 1
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_pending_action_status(self, action_id: int, status: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                update pending_actions
                set status = ?, updated_at = current_timestamp
                where id = ?
                """,
                (status, action_id),
            )
            connection.commit()

    def record_assignment(
        self,
        teacher_id: int,
        google_course_id: str,
        google_coursework_id: str,
        title: str,
        state: str,
        alternate_link: str = "",
        deadline_text: str = "",
        due_at: str = "",
    ) -> int:
        with closing(self.connect()) as connection:
            self._ensure_column(connection, "assignments", "deadline_text", "text not null default ''")
            self._ensure_column(connection, "assignments", "due_at", "text not null default ''")
            cursor = connection.execute(
                """
                insert into assignments (
                    teacher_id, google_course_id, google_coursework_id, title, state,
                    alternate_link, deadline_text, due_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    teacher_id,
                    google_course_id,
                    google_coursework_id,
                    title,
                    state,
                    alternate_link,
                    deadline_text,
                    due_at,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_material(
        self,
        teacher_id: int,
        google_course_id: str,
        google_material_id: str,
        title: str,
        state: str,
        alternate_link: str = "",
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into materials (
                    teacher_id, google_course_id, google_material_id, title, state, alternate_link
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (teacher_id, google_course_id, google_material_id, title, state, alternate_link),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_announcement(
        self,
        teacher_id: int,
        google_course_id: str,
        google_announcement_id: str,
        text: str,
        state: str,
        alternate_link: str = "",
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into announcements (
                    teacher_id, google_course_id, google_announcement_id, text, state, alternate_link
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (teacher_id, google_course_id, google_announcement_id, text, state, alternate_link),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def latest_assignments(self, teacher_id: int, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select a.id, a.google_course_id, a.google_coursework_id, a.title, a.state,
                       a.alternate_link, a.deadline_text, a.due_at, a.created_at,
                       c.name as course_name, c.section
                from assignments a
                left join courses c
                  on c.teacher_id = a.teacher_id
                 and c.google_course_id = a.google_course_id
                where a.teacher_id = ?
                order by a.id desc
                limit ?
                """,
                (teacher_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def upcoming_assignments(self, teacher_id: int, now_iso: str, until_iso: str) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            self._ensure_column(connection, "assignments", "deadline_text", "text not null default ''")
            self._ensure_column(connection, "assignments", "due_at", "text not null default ''")
            rows = connection.execute(
                """
                select a.id, a.google_course_id, a.google_coursework_id, a.title, a.state,
                       a.alternate_link, a.deadline_text, a.due_at, a.created_at,
                       c.name as course_name, c.section
                from assignments a
                left join courses c
                  on c.teacher_id = a.teacher_id
                 and c.google_course_id = a.google_course_id
                where a.teacher_id = ?
                  and a.due_at != ''
                  and a.due_at >= ?
                  and a.due_at <= ?
                order by a.due_at asc, a.id asc
                """,
                (teacher_id, now_iso, until_iso),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_materials(self, teacher_id: int, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select m.id, m.google_course_id, m.google_material_id, m.title, m.state,
                       m.alternate_link, m.created_at, c.name as course_name, c.section
                from materials m
                left join courses c
                  on c.teacher_id = m.teacher_id
                 and c.google_course_id = m.google_course_id
                where m.teacher_id = ?
                order by m.id desc
                limit ?
                """,
                (teacher_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_announcements(self, teacher_id: int, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select a.id, a.google_course_id, a.google_announcement_id, a.text, a.state,
                       a.alternate_link, a.created_at, c.name as course_name, c.section
                from announcements a
                left join courses c
                  on c.teacher_id = a.teacher_id
                 and c.google_course_id = a.google_course_id
                where a.teacher_id = ?
                order by a.id desc
                limit ?
                """,
                (teacher_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_access_logs(self, phone: str, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select phone, channel_type, message, allowed, created_at
                from access_logs
                where phone = ?
                order by id desc
                limit ?
                """,
                (phone, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_staged_file(
        self,
        teacher_id: int,
        original_name: str,
        staged_path: str,
        mime_type: str,
        size_bytes: int,
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into staged_files (teacher_id, original_name, staged_path, mime_type, size_bytes)
                values (?, ?, ?, ?, ?)
                """,
                (teacher_id, original_name, staged_path, mime_type, size_bytes),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def latest_staged_file(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select id, original_name, staged_path, mime_type, size_bytes, status, created_at
                from staged_files
                where teacher_id = ? and status = 'staged'
                order by id desc
                limit 1
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_staged_file_status(self, staged_file_id: int, status: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                "update staged_files set status = ? where id = ?",
                (status, staged_file_id),
            )
            connection.commit()

    def record_uploaded_file(
        self,
        teacher_id: int,
        staged_file_id: int,
        drive_file_id: str,
        drive_web_link: str,
        original_name: str,
        mime_type: str,
    ) -> int:
        with closing(self.connect()) as connection:
            cursor = connection.execute(
                """
                insert into uploaded_files (
                    teacher_id, staged_file_id, drive_file_id, drive_web_link, original_name, mime_type
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (teacher_id, staged_file_id, drive_file_id, drive_web_link, original_name, mime_type),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def latest_uploaded_file(self, teacher_id: int) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                select id, staged_file_id, drive_file_id, drive_web_link, original_name, mime_type, created_at
                from uploaded_files
                where teacher_id = ?
                order by id desc
                limit 1
                """,
                (teacher_id,),
            ).fetchone()
        return dict(row) if row else None

    def log_access_attempt(self, phone: str, channel_type: str, message: str, allowed: bool) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                insert into access_logs (phone, channel_type, message, allowed)
                values (?, ?, ?, ?)
                """,
                (phone, channel_type, message, int(allowed)),
            )
            connection.commit()

    def log_error(self, phone: str, action: str, error_type: str, message: str) -> None:
        with closing(self.connect()) as connection:
            connection.execute(
                """
                insert into error_logs (phone, action, error_type, message)
                values (?, ?, ?, ?)
                """,
                (phone, action, error_type, message),
            )
            connection.commit()

    def latest_error_logs(self, limit: int = 10) -> list[dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                select phone, action, error_type, message, created_at
                from error_logs
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
