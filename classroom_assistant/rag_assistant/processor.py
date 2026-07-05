from __future__ import annotations

from pathlib import Path

from .chunking import chunk_text
from .store import RagStore
from .text_extraction import TextExtractor, TextExtractionError
from .vector_store import ChromaVectorStore, VectorStoreUnavailable


class RagProcessingError(RuntimeError):
    pass


class RagProcessor:
    def __init__(self, store: RagStore | None = None, extractor: TextExtractor | None = None) -> None:
        self.store = store or RagStore()
        self.store.initialize()
        self.extractor = extractor or TextExtractor()

    def process_document(self, document_id: int, owner_phone: str = "") -> int:
        document = self.store.get_document(document_id=document_id, owner_phone=owner_phone)
        if document is None:
            raise RagProcessingError(f"RAG document not found: {document_id}")

        try:
            pages = self.extractor.extract_pages(Path(str(document["stored_path"])))
        except TextExtractionError as exc:
            self.store.update_document_status(document_id, "error")
            raise RagProcessingError(str(exc)) from exc

        chunks = []
        chunk_index = 1
        for page in pages:
            for chunk in chunk_text(str(page["text"])):
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "page_number": page.get("page_number"),
                        "text": chunk,
                    }
                )
                chunk_index += 1
        self.store.replace_chunks(document_id, chunks)
        self.store.update_document_status(document_id, "indexed")
        vector_store = None
        try:
            vector_store = ChromaVectorStore(self.store)
            vector_store.index_document(document_id)
        except (VectorStoreUnavailable, Exception):
            pass
        finally:
            if vector_store is not None:
                vector_store.close()
        return len(chunks)
