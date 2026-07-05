from __future__ import annotations

from pathlib import Path


RAG_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "rag"
RAG_UPLOAD_DIR = RAG_DATA_DIR / "uploads"
RAG_INDEX_DIR = RAG_DATA_DIR / "indexes"
RAG_CHROMA_DIR = RAG_INDEX_DIR / "chroma"
RAG_DB_PATH = RAG_DATA_DIR / "rag.sqlite"

SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt"}
MAX_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024
