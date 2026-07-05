from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from .access_control import normalize_phone
from .database import Database
from .file_receiver import MAX_FILE_SIZE_BYTES, SUPPORTED_EXTENSIONS, StagedFile
from .google_auth import GoogleAuthError, read_authorized_user_token


DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_FOLDER_NAME = "Classroom Assistant"
SUPPORTED_DRIVE_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.presentation",
}


@dataclass(frozen=True)
class UploadedDriveFile:
    id: str
    name: str
    web_view_link: str


class DriveService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upload_latest_staged_file(self, phone: str, course_folder_name: str = "") -> UploadedDriveFile:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        row = self.database.latest_staged_file(int(teacher["id"]))
        if row is None:
            raise GoogleAuthError("No staged file found. Send or search a file first.")

        staged = StagedFile(
            id=int(row["id"]),
            original_name=str(row["original_name"]),
            staged_path=Path(str(row["staged_path"])),
            mime_type=str(row["mime_type"]),
            size_bytes=int(row["size_bytes"]),
        )
        return self.upload_staged_file(int(teacher["id"]), staged, course_folder_name)

    def upload_staged_file(
        self,
        teacher_id: int,
        staged: StagedFile,
        course_folder_name: str = "",
    ) -> UploadedDriveFile:
        if not staged.staged_path.exists():
            raise GoogleAuthError(f"Staged file is missing: {staged.staged_path}")

        service = self._build_drive_service(teacher_id)
        root_folder_id = self._find_or_create_folder(service, ROOT_FOLDER_NAME)
        parent_id = root_folder_id
        if course_folder_name:
            parent_id = self._find_or_create_folder(service, course_folder_name, parent_id)

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise GoogleAuthError(
                "Google API dependencies are missing. Run: "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        media = MediaFileUpload(
            str(staged.staged_path),
            mimetype=staged.mime_type,
            resumable=True,
        )
        body = {
            "name": staged.original_name,
            "parents": [parent_id],
        }
        created = (
            service.files()
            .create(
                body=body,
                media_body=media,
                fields="id,name,webViewLink",
            )
            .execute()
        )
        uploaded = UploadedDriveFile(
            id=str(created.get("id", "")),
            name=str(created.get("name", staged.original_name)),
            web_view_link=str(created.get("webViewLink", "")),
        )
        self.database.record_uploaded_file(
            teacher_id=teacher_id,
            staged_file_id=staged.id,
            drive_file_id=uploaded.id,
            drive_web_link=uploaded.web_view_link,
            original_name=uploaded.name,
            mime_type=staged.mime_type,
        )
        self.database.mark_staged_file_status(staged.id, "uploaded")
        return uploaded

    def upload_local_file(
        self,
        phone: str,
        source_path: Path,
        folder_parts: list[str] | None = None,
        skip_existing: bool = True,
    ) -> UploadedDriveFile:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        if not source_path.exists() or not source_path.is_file():
            raise GoogleAuthError(f"File not found: {source_path}")

        extension = source_path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise GoogleAuthError(f"Unsupported file type. Please upload one of: {supported}")

        size = source_path.stat().st_size
        if size <= 0:
            raise GoogleAuthError(f"File is empty: {source_path.name}")
        if size > MAX_FILE_SIZE_BYTES:
            raise GoogleAuthError(f"File is too large: {source_path.name}. Maximum supported size is 25 MB.")

        mime_type = SUPPORTED_EXTENSIONS[extension]
        guessed_mime, _ = mimetypes.guess_type(source_path.name)
        if guessed_mime:
            mime_type = guessed_mime

        staged_file_id = self.database.record_staged_file(
            teacher_id=int(teacher["id"]),
            original_name=source_path.name,
            staged_path=str(source_path),
            mime_type=mime_type,
            size_bytes=size,
        )

        service = self._build_drive_service(int(teacher["id"]))
        parent_id = self._ensure_folder_path(service, folder_parts or [])
        if skip_existing:
            existing = self._find_file_in_folder(service, source_path.name, parent_id)
            if existing is not None:
                return existing

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise GoogleAuthError(
                "Google API dependencies are missing. Run: "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        media = MediaFileUpload(str(source_path), mimetype=mime_type, resumable=True)
        created = (
            service.files()
            .create(
                body={"name": source_path.name, "parents": [parent_id]},
                media_body=media,
                fields="id,name,webViewLink",
            )
            .execute()
        )
        uploaded = UploadedDriveFile(
            id=str(created.get("id", "")),
            name=str(created.get("name", source_path.name)),
            web_view_link=str(created.get("webViewLink", "")),
        )
        self.database.record_uploaded_file(
            teacher_id=int(teacher["id"]),
            staged_file_id=staged_file_id,
            drive_file_id=uploaded.id,
            drive_web_link=uploaded.web_view_link,
            original_name=uploaded.name,
            mime_type=mime_type,
        )
        self.database.mark_staged_file_status(staged_file_id, "uploaded")
        return uploaded

    def supported_files_in_tree(self, source_root: Path) -> list[Path]:
        if not source_root.exists() or not source_root.is_dir():
            raise GoogleAuthError(f"Source folder not found: {source_root}")
        files = [
            path
            for path in source_root.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        return sorted(files, key=lambda path: str(path.relative_to(source_root)).lower())

    def upload_local_tree(
        self,
        phone: str,
        source_root: Path,
        drive_base_folder: str,
        limit: int = 0,
    ) -> list[tuple[Path, UploadedDriveFile]]:
        files = self.supported_files_in_tree(source_root)
        if limit > 0:
            files = files[:limit]

        uploaded: list[tuple[Path, UploadedDriveFile]] = []
        for file_path in files:
            relative_parent = file_path.relative_to(source_root).parent
            folder_parts = [ROOT_FOLDER_NAME, drive_base_folder]
            if str(relative_parent) != ".":
                folder_parts.extend(relative_parent.parts)
            uploaded.append((file_path, self.upload_local_file(phone, file_path, folder_parts)))
        return uploaded

    def latest_uploaded_file(self, phone: str) -> UploadedDriveFile | None:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        row = self.database.latest_uploaded_file(int(teacher["id"]))
        if row is None:
            return None
        return UploadedDriveFile(
            id=str(row["drive_file_id"]),
            name=str(row["original_name"]),
            web_view_link=str(row["drive_web_link"]),
        )

    def list_files_in_folder(self, phone: str, folder_name: str, limit: int = 20) -> list[UploadedDriveFile]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        service = self._build_drive_service(int(teacher["id"]))
        folder_id = self._find_folder_by_name(service, folder_name)
        if not folder_id:
            raise GoogleAuthError(f"Drive folder not found: {folder_name}")

        mime_query = " or ".join(f"mimeType = '{mime_type}'" for mime_type in sorted(SUPPORTED_DRIVE_MIME_TYPES))
        response = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false and ({mime_query})",
                spaces="drive",
                fields="files(id,name,webViewLink,mimeType)",
                pageSize=limit,
                orderBy="name",
            )
            .execute()
        )
        return [
            UploadedDriveFile(
                id=str(file.get("id", "")),
                name=str(file.get("name", "")),
                web_view_link=str(file.get("webViewLink", "")),
            )
            for file in response.get("files", [])
        ]

    def list_folders(self, phone: str, limit: int = 100) -> list[str]:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        service = self._build_drive_service(int(teacher["id"]))
        response = (
            service.files()
            .list(
                q=f"mimeType = '{DRIVE_FOLDER_MIME}' and trashed = false",
                spaces="drive",
                fields="files(name)",
                pageSize=limit,
                orderBy="name",
            )
            .execute()
        )
        return [str(file.get("name", "")) for file in response.get("files", []) if file.get("name")]

    def folder_candidates_for_course(self, phone: str, course_name: str) -> list[str]:
        manual = drive_folder_candidates(course_name)
        try:
            folders = self.list_folders(phone)
        except GoogleAuthError:
            folders = []

        scored: list[tuple[int, str]] = []
        course_terms = normalized_name_terms(course_name)
        for folder in folders:
            folder_terms = normalized_name_terms(folder)
            if not folder_terms:
                continue
            overlap = len(set(course_terms) & set(folder_terms))
            contains_score = 3 if normalize_name(folder) in normalize_name(course_name) else 0
            reverse_contains_score = 3 if normalize_name(course_name).replace("se ", "") in normalize_name(folder) else 0
            score = overlap + contains_score + reverse_contains_score
            if score > 0:
                scored.append((score, folder))
        scored.sort(key=lambda pair: (-pair[0], pair[1].lower()))

        result = []
        for candidate in manual + [folder for _, folder in scored]:
            if candidate and candidate not in result:
                result.append(candidate)
        return result

    def find_file_by_name(self, phone: str, query: str, folder_name: str = "") -> UploadedDriveFile:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        cleaned = query.strip()
        if not cleaned:
            raise GoogleAuthError("Drive file name is missing.")

        service = self._build_drive_service(int(teacher["id"]))
        escaped = cleaned.replace("\\", "\\\\").replace("'", "\\'")
        mime_query = " or ".join(f"mimeType = '{mime_type}'" for mime_type in sorted(SUPPORTED_DRIVE_MIME_TYPES))
        query_parts = [
            f"name contains '{escaped}' "
            "and trashed = false "
            f"and ({mime_query})"
        ]
        if folder_name:
            folder_id = self._find_folder_by_name(service, folder_name)
            if not folder_id:
                raise GoogleAuthError(f"Drive folder not found: {folder_name}")
            query_parts.append(f"'{folder_id}' in parents")
        drive_query = " and ".join(query_parts)
        response = (
            service.files()
            .list(
                q=drive_query,
                spaces="drive",
                fields="files(id,name,webViewLink,mimeType)",
                pageSize=10,
            )
            .execute()
        )
        files = response.get("files", [])
        if not files:
            folder_note = f" in folder {folder_name}" if folder_name else ""
            raise GoogleAuthError(f"No supported Google Drive file found for: {cleaned}{folder_note}")
        if len(files) > 1:
            options = "\n".join(f"{index}. {item['name']}" for index, item in enumerate(files, start=1))
            raise GoogleAuthError(
                "I found multiple matching Drive files:\n"
                f"{options}\n"
                "Please send a more specific Drive file name."
            )

        file = files[0]
        return UploadedDriveFile(
            id=str(file.get("id", "")),
            name=str(file.get("name", cleaned)),
            web_view_link=str(file.get("webViewLink", "")),
        )

    def find_file_by_name_in_folders(
        self,
        phone: str,
        query: str,
        folder_names: list[str],
    ) -> UploadedDriveFile:
        errors = []
        for folder_name in folder_names:
            try:
                return self.find_file_by_name(phone, query, folder_name=folder_name)
            except GoogleAuthError as exc:
                errors.append(str(exc))
        try:
            return self.find_file_by_name(phone, query)
        except GoogleAuthError as exc:
            details = "\n".join(errors[-3:])
            if details:
                raise GoogleAuthError(f"{exc}\nTried class folders:\n{details}") from exc
            raise

    def _find_or_create_folder(self, service, name: str, parent_id: str = "") -> str:
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        query_parts = [
            f"name = '{escaped}'",
            f"mimeType = '{DRIVE_FOLDER_MIME}'",
            "trashed = false",
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
        query = " and ".join(query_parts)
        response = service.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=1).execute()
        files = response.get("files", [])
        if files:
            return str(files[0]["id"])

        body = {
            "name": name,
            "mimeType": DRIVE_FOLDER_MIME,
        }
        if parent_id:
            body["parents"] = [parent_id]
        created = service.files().create(body=body, fields="id").execute()
        return str(created["id"])

    def _find_folder_by_name(self, service, name: str) -> str:
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        response = (
            service.files()
            .list(
                q=(
                    f"name = '{escaped}' and "
                    f"mimeType = '{DRIVE_FOLDER_MIME}' and "
                    "trashed = false"
                ),
                spaces="drive",
                fields="files(id,name)",
                pageSize=1,
            )
            .execute()
        )
        files = response.get("files", [])
        return str(files[0]["id"]) if files else ""

    def _ensure_folder_path(self, service, folder_parts: list[str]) -> str:
        parent_id = ""
        parts = folder_parts or [ROOT_FOLDER_NAME]
        for folder_name in parts:
            cleaned = folder_name.strip()
            if not cleaned:
                continue
            parent_id = self._find_or_create_folder(service, cleaned, parent_id)
        return parent_id

    def _find_file_in_folder(self, service, name: str, parent_id: str) -> UploadedDriveFile | None:
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        response = (
            service.files()
            .list(
                q=f"name = '{escaped}' and '{parent_id}' in parents and trashed = false",
                spaces="drive",
                fields="files(id,name,webViewLink)",
                pageSize=1,
            )
            .execute()
        )
        files = response.get("files", [])
        if not files:
            return None
        file = files[0]
        return UploadedDriveFile(
            id=str(file.get("id", "")),
            name=str(file.get("name", name)),
            web_view_link=str(file.get("webViewLink", "")),
        )

    def _build_drive_service(self, teacher_id: int):
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

        return build("drive", "v3", credentials=credentials)


def normalize_name(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    return " ".join(cleaned.split())


def normalized_name_terms(value: str) -> list[str]:
    stopwords = {"a", "an", "the", "se", "class", "course"}
    return [term for term in normalize_name(value).split() if len(term) > 1 and term not in stopwords]


def drive_folder_candidates(course_display_name: str) -> list[str]:
    cleaned = course_display_name.replace("(A)", "").replace("(a)", "").strip()
    candidates = [cleaned]
    if cleaned.lower().startswith("se "):
        candidates.append(cleaned[3:].strip())
    if "database" in cleaned.lower():
        candidates.extend(["DataBases", "Databases", "Database"])
    if "operating system" in cleaned.lower():
        candidates.append("Operating System")
    if "software requirement engineering" in cleaned.lower():
        candidates.append("Software Requirement Engineering")

    result = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    return result
