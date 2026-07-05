from __future__ import annotations

import re

from .store import RagStore


class RagGenerationError(RuntimeError):
    pass


class RagQuizGenerator:
    def __init__(self, store: RagStore | None = None) -> None:
        self.store = store or RagStore()
        self.store.initialize()

    def generate_mcqs(self, owner_phone: str, topic: str, count: int = 10) -> str:
        chunks = self.store.search_chunks(owner_phone=owner_phone, question=topic, limit=5)
        if not chunks:
            raise RagGenerationError("No matching indexed document chunks found. Upload and process a document first.")

        context = " ".join(str(chunk["text"]) for chunk in chunks)
        sentences = split_sentences(context)
        if not sentences:
            raise RagGenerationError("The indexed document does not contain enough text to generate MCQs.")

        questions = []
        for index in range(1, count + 1):
            sentence = sentences[(index - 1) % len(sentences)]
            keyword = choose_keyword(sentence) or topic
            questions.append(
                "\n".join(
                    [
                        f"{index}. Which option best relates to {keyword}?",
                        f"   A. {sentence[:110]}",
                        "   B. A concept not discussed in the uploaded document",
                        "   C. An unrelated classroom rule",
                        "   D. None of the above",
                        "   Answer: A",
                    ]
                )
            )

        sources = []
        for chunk in chunks:
            source = str(chunk["original_name"])
            if chunk.get("page_number"):
                source = f"{source}, page {chunk['page_number']}"
            if source not in sources:
                sources.append(source)

        return (
            f"MCQs generated from uploaded documents for topic: {topic}\n\n"
            + "\n\n".join(questions)
            + "\n\nSources:\n"
            + "\n".join(f"- {source}" for source in sources)
            + "\n\nTeacher note: Review the generated MCQs before publishing."
        )


def split_sentences(value: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", value) if sentence.strip()]
    if sentences:
        return sentences
    return [value.strip()] if value.strip() else []


def choose_keyword(sentence: str) -> str:
    words = [
        word.strip(".,:;!?()[]{}\"'")
        for word in sentence.split()
        if len(word.strip(".,:;!?()[]{}\"'")) > 5
    ]
    return words[0] if words else ""
