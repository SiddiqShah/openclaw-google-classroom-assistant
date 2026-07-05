from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .access_control import normalize_phone
from .database import Database
from .google_auth import GoogleAuthError


SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


class FileReceiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagedFile:
    id: int
    original_name: str
    staged_path: Path
    mime_type: str
    size_bytes: int


class FileReceiver:
    def __init__(self, database: Database, project_root: Path) -> None:
        self.database = database
        self.project_root = project_root
        self.staging_root = project_root / "data" / "staged_files"

    def receive(self, phone: str, source_path: Path, original_name: str | None = None) -> StagedFile:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        if not source_path.exists() or not source_path.is_file():
            raise FileReceiveError(f"File not found: {source_path}")

        filename = original_name or source_path.name
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise FileReceiveError(f"Unsupported file type. Please send one of: {supported}")

        size = source_path.stat().st_size
        if size <= 0:
            raise FileReceiveError("File is empty.")
        if size > MAX_FILE_SIZE_BYTES:
            raise FileReceiveError("File is too large. Maximum supported size is 25 MB.")

        mime_type = SUPPORTED_EXTENSIONS[extension]
        guessed_mime, _ = mimetypes.guess_type(filename)
        if guessed_mime and guessed_mime != mime_type:
            mime_type = guessed_mime

        teacher_dir = self.staging_root / f"teacher_{teacher['id']}"
        teacher_dir.mkdir(parents=True, exist_ok=True)
        staged_name = f"{uuid4().hex}{extension}"
        staged_path = teacher_dir / staged_name
        shutil.copy2(source_path, staged_path)

        file_id = self.database.record_staged_file(
            teacher_id=int(teacher["id"]),
            original_name=filename,
            staged_path=str(staged_path),
            mime_type=mime_type,
            size_bytes=size,
        )
        return StagedFile(
            id=file_id,
            original_name=filename,
            staged_path=staged_path,
            mime_type=mime_type,
            size_bytes=size,
        )

    def latest_for_teacher(self, phone: str) -> StagedFile | None:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")
        row = self.database.latest_staged_file(int(teacher["id"]))
        if row is None:
            return None
        return StagedFile(
            id=int(row["id"]),
            original_name=str(row["original_name"]),
            staged_path=Path(str(row["staged_path"])),
            mime_type=str(row["mime_type"]),
            size_bytes=int(row["size_bytes"]),
        )


def render_file_received(file: StagedFile) -> str:
    return (
        f"File received: {file.original_name}\n\n"
        "What do you want to do with this file?\n\n"
        "1. Attach to Assignment\n"
        "2. Upload as Study Material\n"
        "3. Cancel"
    )
