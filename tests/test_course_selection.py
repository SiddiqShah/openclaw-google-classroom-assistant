from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.classroom_api import ClassroomService
from classroom_assistant.database import Database


class CourseSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.sqlite")
        self.database.initialize()
        self.controller = AccessController(self.database)
        self.teacher = self.controller.add_teacher("Mr.Siddiq", "+923018083053")
        self.database.replace_courses(
            self.teacher.id,
            [
                {
                    "id": "course-1",
                    "name": "SE Databases",
                    "section": "A",
                    "state": "ACTIVE",
                },
                {
                    "id": "course-2",
                    "name": "SE Operating System",
                    "section": "A",
                    "state": "ACTIVE",
                },
            ],
        )
        self.service = ClassroomService(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_select_course_by_number(self) -> None:
        selected = self.service.select_course("+923018083053", "2")

        self.assertEqual(selected.name, "SE Operating System")
        self.assertEqual(self.service.selected_course("+923018083053"), selected)

    def test_select_course_by_name(self) -> None:
        selected = self.service.select_course("+923018083053", "databases")

        self.assertEqual(selected.name, "SE Databases")


if __name__ == "__main__":
    unittest.main()
