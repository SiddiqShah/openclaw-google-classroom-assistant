from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from classroom_assistant.rag_assistant.chunking import chunk_text
from classroom_assistant.rag_assistant.document_upload import RagDocumentUploader
from classroom_assistant.rag_assistant.generator import RagQuizGenerator
from classroom_assistant.rag_assistant.processor import RagProcessor
from classroom_assistant.rag_assistant.qa import RagQuestionAnswerer
from classroom_assistant.rag_assistant.store import RagStore
from classroom_assistant.rag_assistant.text_extraction import TextExtractor


class RagScaffoldTests(unittest.TestCase):
    def test_chunk_text_uses_overlap(self) -> None:
        text = " ".join(f"word{index}" for index in range(20))

        chunks = chunk_text(text, max_words=10, overlap_words=2)

        self.assertEqual(len(chunks), 3)
        self.assertIn("word8", chunks[1])

    def test_extract_txt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "notes.txt"
            path.write_text("hello classroom rag", encoding="utf-8")

            extracted = TextExtractor().extract(path)

            self.assertEqual(extracted, "hello classroom rag")

    def test_extract_docx(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "notes.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    """
                    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                      <w:body><w:p><w:r><w:t>Hello DOCX RAG</w:t></w:r></w:p></w:body>
                    </w:document>
                    """,
                )

            extracted = TextExtractor().extract(path)

            self.assertEqual(extracted, "Hello DOCX RAG")

    def test_upload_document_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "chapter.txt"
            source.write_text("chapter text", encoding="utf-8")
            store = RagStore(Path(temp) / "rag.sqlite")
            uploader = RagDocumentUploader(store)

            uploaded = uploader.upload("+923018083053", source, category="Class 9 Biology")
            documents = store.list_documents("+923018083053")

            self.assertEqual(uploaded.original_name, "chapter.txt")
            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0]["category"], "Class 9 Biology")

    def test_process_and_answer_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "chapter.txt"
            source.write_text(
                "Photosynthesis is the process plants use to make food using sunlight and carbon dioxide.",
                encoding="utf-8",
            )
            store = RagStore(Path(temp) / "rag.sqlite")
            uploader = RagDocumentUploader(store)
            uploaded = uploader.upload("+923018083053", source, category="Class 9 Biology")

            chunk_count = RagProcessor(store).process_document(uploaded.id, "+923018083053")
            answer = RagQuestionAnswerer(store).answer("+923018083053", "What is photosynthesis?")

            self.assertEqual(chunk_count, 1)
            self.assertIn("Photosynthesis", answer.answer)
            self.assertEqual(answer.sources, ["chapter.txt"])

    def test_delete_document_removes_it_from_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "chapter.txt"
            source.write_text("chapter text", encoding="utf-8")
            store = RagStore(Path(temp) / "rag.sqlite")
            uploaded = RagDocumentUploader(store).upload("+923018083053", source)

            deleted = store.delete_document(uploaded.id, "+923018083053")
            documents = store.list_documents("+923018083053")

            self.assertTrue(deleted)
            self.assertEqual(documents, [])

    def test_generate_mcqs_from_indexed_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "chapter.txt"
            source.write_text(
                "Photosynthesis lets plants make food. Chlorophyll captures sunlight.",
                encoding="utf-8",
            )
            store = RagStore(Path(temp) / "rag.sqlite")
            uploaded = RagDocumentUploader(store).upload("+923018083053", source)
            RagProcessor(store).process_document(uploaded.id, "+923018083053")

            generated = RagQuizGenerator(store).generate_mcqs("+923018083053", "photosynthesis", count=3)

            self.assertIn("1. Which option", generated)
            self.assertIn("3. Which option", generated)
            self.assertIn("Sources:", generated)


if __name__ == "__main__":
    unittest.main()
