from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.database import Database


class DriveDatabaseTests(unittest.TestCase):
    def test_record_latest_uploaded_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Database(Path(temp) / "test.sqlite")
            database.initialize()
            teacher = AccessController(database).add_teacher("Mr.Siddiq", "+923018083053")
            staged_id = database.record_staged_file(
                teacher_id=teacher.id,
                original_name="worksheet.pdf",
                staged_path=str(Path(temp) / "worksheet.pdf"),
                mime_type="application/pdf",
                size_bytes=10,
            )

            database.record_uploaded_file(
                teacher_id=teacher.id,
                staged_file_id=staged_id,
                drive_file_id="drive-123",
                drive_web_link="https://drive.google.com/file/d/drive-123/view",
                original_name="worksheet.pdf",
                mime_type="application/pdf",
            )

            latest = database.latest_uploaded_file(teacher.id)

            self.assertIsNotNone(latest)
            assert latest is not None
            self.assertEqual(latest["drive_file_id"], "drive-123")


if __name__ == "__main__":
    unittest.main()
