from __future__ import annotations

from .models import RagAnswer
from .store import RagStore
from .vector_store import ChromaVectorStore, VectorStoreUnavailable


class RagQuestionAnswerer:
    def __init__(self, store: RagStore | None = None) -> None:
        self.store = store or RagStore()
        self.store.initialize()

    def answer(self, owner_phone: str, question: str, limit: int = 5) -> RagAnswer:
        vector_store = None
        try:
            vector_store = ChromaVectorStore(self.store)
            chunks = vector_store.search(owner_phone=owner_phone, question=question, limit=limit)
            retrieval_note = "local ChromaDB vector retrieval"
            if not chunks:
                chunks = self.store.search_chunks(owner_phone=owner_phone, question=question, limit=limit)
                retrieval_note = "local keyword retrieval fallback"
        except (VectorStoreUnavailable, Exception):
            chunks = self.store.search_chunks(owner_phone=owner_phone, question=question, limit=limit)
            retrieval_note = "local keyword retrieval fallback"
        finally:
            if vector_store is not None:
                vector_store.close()
        if not chunks:
            answer = "I could not find an answer in the uploaded documents yet."
            self.store.record_query(owner_phone, question, answer)
            return RagAnswer(answer=answer, sources=[])

        context_lines = []
        sources = []
        for chunk in chunks:
            source = str(chunk["original_name"])
            page_number = chunk.get("page_number")
            if page_number:
                source = f"{source}, page {page_number}"
            sources.append(source)
            context_lines.append(str(chunk["text"])[:900])

        answer = (
            "Based on the uploaded documents:\n\n"
            f"{summarize_context(question, context_lines)}\n\n"
            f"Confidence note: {retrieval_note}. Review the sources before using this as final."
        )
        self.store.record_query(owner_phone, question, answer)
        return RagAnswer(answer=answer, sources=dedupe(sources))


def summarize_context(question: str, context_lines: list[str]) -> str:
    joined = "\n\n".join(context_lines)
    if len(joined) <= 1200:
        return joined
    return joined[:1200].rstrip() + "..."


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
