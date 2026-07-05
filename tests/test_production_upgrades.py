from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from classroom_assistant.dashboard import render_dashboard
from classroom_assistant.database import Database
from classroom_assistant.rag_assistant.document_upload import RagDocumentUploader
from classroom_assistant.rag_assistant.processor import RagProcessor
from classroom_assistant.rag_assistant.qa import RagQuestionAnswerer
from classroom_assistant.rag_assistant.store import RagStore
from classroom_assistant.rag_assistant.text_extraction import TextExtractor
from classroom_assistant.security import TokenCipher, TokenSecurityError
from classroom_assistant.whatsapp_notifier import WhatsAppNotifier


class ProductionUpgradeTests(unittest.TestCase):
    def test_token_cipher_encrypts_and_decrypts_token_json(self) -> None:
        old_key = os.environ.get(TokenCipher.ENV_KEY)
        os.environ[TokenCipher.ENV_KEY] = Fernet.generate_key().decode("utf-8")
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "token.json"
                token_json = '{"token": "secret"}'

                TokenCipher().write_token(path, token_json)
                raw = path.read_text(encoding="utf-8")

                self.assertIn('"encrypted": true', raw)
                self.assertNotIn('"secret"', raw)
                self.assertEqual(TokenCipher().read_token(path), token_json)
        finally:
            if old_key is None:
                os.environ.pop(TokenCipher.ENV_KEY, None)
            else:
                os.environ[TokenCipher.ENV_KEY] = old_key

    def test_encrypted_token_requires_key(self) -> None:
        old_key = os.environ.get(TokenCipher.ENV_KEY)
        os.environ[TokenCipher.ENV_KEY] = Fernet.generate_key().decode("utf-8")
        try:
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "token.json"
                TokenCipher().write_token(path, '{"token": "secret"}')
                os.environ.pop(TokenCipher.ENV_KEY, None)

                with self.assertRaises(TokenSecurityError):
                    TokenCipher().read_token(path)
        finally:
            if old_key is None:
                os.environ.pop(TokenCipher.ENV_KEY, None)
            else:
                os.environ[TokenCipher.ENV_KEY] = old_key

    def test_whatsapp_notifier_queues_when_webhook_is_missing(self) -> None:
        old_webhook = os.environ.pop(WhatsAppNotifier.WEBHOOK_ENV, None)
        try:
            with tempfile.TemporaryDirectory() as temp:
                notifier = WhatsAppNotifier(outbox_path=Path(temp) / "outbox.jsonl")

                result = notifier.send("+923018083053", "Reminder message")
                queued = notifier.list_queued()

                self.assertFalse(result.sent)
                self.assertTrue(result.queued)
                self.assertEqual(queued[0]["phone"], "+923018083053")
                self.assertEqual(queued[0]["text"], "Reminder message")
        finally:
            if old_webhook is not None:
                os.environ[WhatsAppNotifier.WEBHOOK_ENV] = old_webhook

    def test_dashboard_renders_core_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Database(Path(temp) / "classroom.sqlite")
            database.initialize()
            rag_store = RagStore(Path(temp) / "rag.sqlite")
            rag_store.initialize()

            html = render_dashboard(database, rag_store)

            self.assertIn("Google Classroom Assistant Dashboard", html)
            self.assertIn("Courses", html)
            self.assertIn("RAG Documents", html)
            self.assertIn("WhatsApp Outbox", html)

    def test_selectable_pdf_text_is_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "selectable.pdf"
            write_selectable_pdf(path, "Selectable PDF text for classroom RAG.")

            extracted = TextExtractor().extract(path)

            self.assertIn("Selectable PDF text", extracted)

    def test_chromadb_vector_retrieval_answers_indexed_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "chapter.txt"
            source.write_text(
                "Chlorophyll captures sunlight during photosynthesis. Roots absorb water.",
                encoding="utf-8",
            )
            store = RagStore(Path(temp) / "rag.sqlite")
            uploaded = RagDocumentUploader(store).upload("+923018083053", source)

            RagProcessor(store).process_document(uploaded.id, "+923018083053")
            answer = RagQuestionAnswerer(store).answer("+923018083053", "What captures sunlight?")

            self.assertIn("Chlorophyll", answer.answer)
            self.assertIn("ChromaDB", answer.answer)


def write_selectable_pdf(path: Path, text: str) -> None:
    content = f"BT /F1 18 Tf 72 720 Td ({escape_pdf_text(text)}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(pdf))


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


if __name__ == "__main__":
    unittest.main()
