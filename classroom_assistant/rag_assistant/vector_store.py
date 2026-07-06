from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .store import RagStore


class VectorStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: int
    document_id: int
    score: float


class HashEmbeddingFunction:
    def __call__(self, input):
        return [hash_embedding(text) for text in input]


def hash_embedding(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class ChromaVectorStore:
    def __init__(self, store: RagStore | None = None) -> None:
        self.store = store or RagStore()
        self.store.initialize()
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError as exc:
            raise VectorStoreUnavailable(
                "ChromaDB is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        chroma_dir = self.store.path.parent / "chroma"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(chroma_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name="classroom_rag_chunks",
            embedding_function=HashEmbeddingFunction(),
        )

    def reset(self) -> None:
        """Remove every entry from the collection.

        Used to clear stale embeddings left behind by an older database
        generation (chunk ids that no longer exist), which otherwise outrank and
        crowd out the current chunks and break vector search.
        """
        existing = self.collection.get()
        ids = existing.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)

    def close(self) -> None:
        system = getattr(self.client, "_system", None)
        stop = getattr(system, "stop", None)
        if callable(stop):
            stop()

    def index_document(self, document_id: int) -> int:
        document = self.store.get_document(document_id)
        if document is None:
            return 0
        chunks = self.store.list_chunks(document_id)
        if not chunks:
            return 0

        try:
            self.collection.delete(where={"document_id": int(document_id)})
        except Exception:
            pass

        ids = [f"chunk-{chunk['id']}" for chunk in chunks]
        self.collection.upsert(
            ids=ids,
            documents=[str(chunk["text"]) for chunk in chunks],
            metadatas=[
                {
                    "chunk_id": int(chunk["id"]),
                    "document_id": int(document_id),
                    "owner_phone": str(document["owner_phone"]),
                    "original_name": str(document["original_name"]),
                    "page_number": chunk.get("page_number") or 0,
                }
                for chunk in chunks
            ],
        )
        return len(chunks)

    def search(self, owner_phone: str, question: str, limit: int = 5) -> list[dict]:
        result = self.collection.query(
            query_texts=[question],
            n_results=limit,
            where={"owner_phone": owner_phone},
        )
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        if not ids:
            return []

        chunk_ids = [int(metadata["chunk_id"]) for metadata in metadatas]
        return self.store.get_chunks_by_ids(chunk_ids)
