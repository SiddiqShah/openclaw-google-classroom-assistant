from __future__ import annotations

import re
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree


class TextExtractionError(RuntimeError):
    pass


class TextExtractor:
    def extract(self, path: Path) -> str:
        return "\n\n".join(page["text"] for page in self.extract_pages(path))

    def extract_pages(self, path: Path) -> list[dict[str, int | None | str]]:
        extension = path.suffix.lower()
        if extension == ".txt":
            return [{"page_number": None, "text": clean_text(path.read_text(encoding="utf-8", errors="ignore"))}]
        if extension == ".pdf":
            return self._extract_pdf_pages(path)
        if extension == ".docx":
            return [{"page_number": None, "text": self._extract_docx(path)}]
        raise TextExtractionError(f"Unsupported document type: {extension}")

    def _extract_pdf_pages(self, path: Path) -> list[dict[str, int | None | str]]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise TextExtractionError(
                "PDF extraction needs pypdf. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            pages.append({"page_number": index, "text": clean_text(page.extract_text() or "")})
        return pages

    def _extract_docx(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise TextExtractionError(f"Could not read DOCX file: {path}") from exc

        try:
            root = ElementTree.fromstring(xml)
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text_nodes = [node.text or "" for node in root.findall(".//w:t", namespace)]
            return clean_text(" ".join(text_nodes))
        except ElementTree.ParseError:
            plain = re.sub(r"<[^>]+>", " ", xml.decode("utf-8", errors="ignore"))
            return clean_text(unescape(plain))


def clean_text(value: str) -> str:
    text = value.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
