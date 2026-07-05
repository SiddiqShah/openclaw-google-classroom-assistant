from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RagDocument:
    id: int
    owner_phone: str
    title: str
    category: str
    original_name: str
    stored_path: Path
    status: str


@dataclass(frozen=True)
class RagChunk:
    id: int
    document_id: int
    chunk_index: int
    text: str
    page_number: int | None = None


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    sources: list[str]

