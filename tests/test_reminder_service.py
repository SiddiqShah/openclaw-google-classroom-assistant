from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.database import Database
from classroom_assistant.reminder_service import ReminderService


class ReminderServiceTests(unittest.TestCase):
    def test_render_upcoming_deadlines(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Database(Path(temp) / "test.sqlite")
            database.initialize()
            teacher = AccessController(database).add_teacher("Mr.Siddiq", "+923018083053")
            database.replace_courses(
                teacher.id,
                [
                    {
                        "id": "course-1",
                        "name": "SE Software Requirement Engineering",
                        "section": "A",
                        "state": "ACTIVE",
                    }
                ],
            )
            database.record_assignment(
                teacher_id=teacher.id,
                google_course_id="course-1",
                google_coursework_id="work-1",
                title="Requirement Task",
                state="PUBLISHED",
                deadline_text="6 July 2026 5 PM",
                due_at="2026-07-06 17:00",
            )

            message = ReminderService(database).render_upcoming_deadlines(
                phone="+923018083053",
                now=datetime(2026, 7, 4, 12, 0),
            )

            self.assertIn("Upcoming deadlines", message)
            self.assertIn("Requirement Task", message)
            self.assertIn("in 2 days", message)


if __name__ == "__main__":
    unittest.main()
