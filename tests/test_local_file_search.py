from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from classroom_assistant.local_file_search import LocalFileSearch


class LocalFileSearchTests(unittest.TestCase):
    def test_find_supported_file_by_partial_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "Task Req def and specification.pdf"
            target.write_bytes(b"%PDF-1.4")
            (root / "ignore.jpg").write_bytes(b"jpg")

            match = LocalFileSearch(root).find_one("Task Req def and specification")

            self.assertEqual(match.path, target)


if __name__ == "__main__":
    unittest.main()
