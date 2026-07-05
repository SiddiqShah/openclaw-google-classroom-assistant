from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .config import MAX_DOCUMENT_SIZE_BYTES, RAG_UPLOAD_DIR, SUPPORTED_DOCUMENT_EXTENSIONS
from .store import RagStore


class RagUploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class UploadedRagDocument:
    id: int
    original_name: str
    stored_path: Path
    category: str


class RagDocumentUploader:
    def __init__(self, store: RagStore | None = None) -> None:
        self.store = store or RagStore()
        self.store.initialize()

    def upload(
        self,
        owner_phone: str,
        source_path: Path,
        category: str = "",
        title: str = "",
    ) -> UploadedRagDocument:
        if not source_path.exists() or not source_path.is_file():
            raise RagUploadError(f"Document not found: {source_path}")

        extension = source_path.suffix.lower()
        if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_DOCUMENT_EXTENSIONS))
            raise RagUploadError(f"Unsupported document type. Use one of: {supported}")

        size = source_path.stat().st_size
        if size <= 0:
            raise RagUploadError("Document is empty.")
        if size > MAX_DOCUMENT_SIZE_BYTES:
            raise RagUploadError("Document is too large. Maximum supported size is 25 MB.")

        owner_dir = RAG_UPLOAD_DIR / owner_phone.replace("+", "")
        owner_dir.mkdir(parents=True, exist_ok=True)
        stored_path = owner_dir / f"{uuid4().hex}{extension}"
        shutil.copy2(source_path, stored_path)

        document_id = self.store.record_document(
            owner_phone=owner_phone,
            title=title or source_path.stem,
            category=category,
            original_name=source_path.name,
            stored_path=str(stored_path),
        )
        return UploadedRagDocument(
            id=document_id,
            original_name=source_path.name,
            stored_path=stored_path,
            category=category,
        )

