from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from classroom_assistant.access_control import AccessController, normalize_phone
from classroom_assistant.database import Database


class AccessControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.sqlite"
        self.database = Database(db_path)
        self.database.initialize()
        self.controller = AccessController(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_authorized_teacher_gets_menu(self) -> None:
        self.controller.add_teacher("Mr. Ali", "+92 300 1234567", "ali@example.com")

        reply = self.controller.handle_message("+923001234567", "Hi")

        self.assertIn("Welcome, Mr. Ali", reply)
        self.assertIn("Create Assignment", reply)

    def test_unknown_number_is_blocked(self) -> None:
        reply = self.controller.handle_message("+923009999999", "Hi")

        self.assertEqual(reply, "")

    def test_removed_teacher_is_blocked(self) -> None:
        self.controller.add_teacher("Mr. Ali", "+923001234567")

        removed = self.controller.remove_teacher_phone("+923001234567")
        reply = self.controller.handle_message("+923001234567", "Hi")

        self.assertTrue(removed)
        self.assertEqual(reply, "")

    def test_group_messages_are_blocked(self) -> None:
        self.controller.add_teacher("Mr. Ali", "+923001234567")

        reply = self.controller.handle_message("+923001234567", "Hi", channel_type="group")

        self.assertEqual(reply, "")

    def test_phone_normalization(self) -> None:
        self.assertEqual(normalize_phone("0092 300-1234567"), "+923001234567")


if __name__ == "__main__":
    unittest.main()
