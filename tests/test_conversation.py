from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.command_parser import CommandParser
from classroom_assistant.database import Database
from classroom_assistant.date_parser import parse_deadline
from classroom_assistant.workflow import WorkflowService

PHONE = "+923018083053"


class NumericDateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 6, 12, 0)

    def test_slash_date_day_first(self) -> None:
        parsed = parse_deadline("7/7/2026 5pm", now=self.now)
        self.assertEqual(parsed.due_date, {"year": 2026, "month": 7, "day": 7})
        self.assertEqual(parsed.due_time, {"hours": 17, "minutes": 0})

    def test_dash_date_with_time(self) -> None:
        parsed = parse_deadline("07-07-2026 5:30 pm", now=self.now)
        self.assertEqual(parsed.due_date, {"year": 2026, "month": 7, "day": 7})
        self.assertEqual(parsed.due_time, {"hours": 17, "minutes": 30})

    def test_day_first_disambiguation(self) -> None:
        parsed = parse_deadline("25/12/2026", now=self.now)
        self.assertEqual(parsed.due_date, {"year": 2026, "month": 12, "day": 25})

    def test_invalid_date_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_deadline("15/13/2026", now=self.now)


class TitleExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = CommandParser()

    def test_topic_marker_on(self) -> None:
        parsed = self.parser.parse("make an assignment on Joins for databases deadline 9/7/2026 5pm")
        assert parsed is not None
        self.assertEqual(parsed.title, "Joins")

    def test_no_topic_leaves_title_empty(self) -> None:
        parsed = self.parser.parse("create an assignment for operating system class")
        assert parsed is not None
        self.assertEqual(parsed.title, "")
        self.assertIn("title", parsed.missing_fields)


class SlotFillingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.sqlite")
        self.database.initialize()
        controller = AccessController(self.database)
        teacher = controller.add_teacher("Mr.Siddiq", PHONE)
        self.database.replace_courses(
            teacher.id,
            [
                {"id": "c-1", "name": "SE Databases", "section": "A", "state": "ACTIVE"},
                {"id": "c-2", "name": "SE Operating System", "section": "A", "state": "ACTIVE"},
            ],
        )
        self.workflow = WorkflowService(self.database)
        self.parser = CommandParser()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_multi_turn_fills_title_then_deadline(self) -> None:
        first = self.parser.parse("create an assignment for operating system class")
        assert first is not None
        ask = self.workflow.handle_command(PHONE, first, "create an assignment for operating system class")
        self.assertIn("SE Operating System", ask)
        self.assertIn("title", ask)

        step2 = self.workflow.continue_draft(PHONE, "Deadlock Handling")
        self.assertIsNotNone(step2)
        assert step2 is not None
        self.assertIn("Deadlock Handling", step2)
        self.assertIn("deadline", step2.lower())

        step3 = self.workflow.continue_draft(PHONE, "10 July 2026 5 pm")
        self.assertIsNotNone(step3)
        assert step3 is not None
        self.assertIn("Please confirm", step3)
        self.assertIn("Deadlock Handling", step3)
        self.assertIn("SE Operating System", step3)

    def test_labelled_follow_up_overrides_topic(self) -> None:
        first = self.parser.parse("generate an assignment in normalization and upload it to databases class")
        assert first is not None
        self.workflow.handle_command(
            PHONE, first, "generate an assignment in normalization and upload it to databases class"
        )
        result = self.workflow.continue_draft(PHONE, "topic name Database Management and deadline is 7/7/2026 5pm")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("Database Management", result)
        self.assertNotIn("normalization", result.lower())

    def test_unrelated_message_does_not_hijack_draft(self) -> None:
        first = self.parser.parse("create an assignment for operating system class")
        assert first is not None
        self.workflow.handle_command(PHONE, first, "create an assignment for operating system class")
        # A message with no fillable detail should be ignored by the draft.
        self.assertIsNone(self.workflow.continue_draft(PHONE, "thanks"))

    def test_complete_one_liner_goes_straight_to_preview(self) -> None:
        command = self.parser.parse("make an assignment on Joins for databases deadline 9/7/2026 5pm marks 15")
        assert command is not None
        result = self.workflow.handle_command(
            PHONE, command, "make an assignment on Joins for databases deadline 9/7/2026 5pm marks 15"
        )
        self.assertIn("Please confirm", result)
        self.assertIn("Joins", result)
        self.assertIn("SE Databases", result)


if __name__ == "__main__":
    unittest.main()
