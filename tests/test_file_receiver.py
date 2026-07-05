from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.database import Database
from classroom_assistant.file_receiver import FileReceiveError, FileReceiver


class FileReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        self.database = Database(self.project_root / "data" / "test.sqlite")
        self.database.initialize()
        self.controller = AccessController(self.database)
        self.controller.add_teacher("Mr.Siddiq", "+923018083053")
        self.receiver = FileReceiver(self.database, self.project_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_receive_pdf_file(self) -> None:
        source = self.project_root / "worksheet.pdf"
        source.write_bytes(b"%PDF-1.4\nfake pdf")

        staged = self.receiver.receive("+923018083053", source)

        self.assertEqual(staged.original_name, "worksheet.pdf")
        self.assertTrue(staged.staged_path.exists())
        self.assertEqual(self.receiver.latest_for_teacher("+923018083053"), staged)

    def test_reject_unsupported_file(self) -> None:
        source = self.project_root / "image.jpg"
        source.write_bytes(b"fake image")

        with self.assertRaises(FileReceiveError):
            self.receiver.receive("+923018083053", source)


if __name__ == "__main__":
    unittest.main()
