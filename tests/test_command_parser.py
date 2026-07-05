from __future__ import annotations

import unittest

from classroom_assistant.command_parser import CommandParser, render_preview


class CommandParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = CommandParser()

    def test_assignment_parser_extracts_fields(self) -> None:
        parsed = self.parser.parse(
            "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.intent, "assignment")
        self.assertEqual(parsed.course, "SE Databases")
        self.assertEqual(parsed.title, "Python Loops")
        self.assertEqual(parsed.deadline, "15 July 2026 6 PM")
        self.assertEqual(parsed.marks, 25)
        self.assertTrue(parsed.is_complete)

    def test_assignment_missing_deadline(self) -> None:
        parsed = self.parser.parse("SE Databases mein Python Loops assignment banao")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("deadline", parsed.missing_fields)
        self.assertIn("deadline", render_preview(parsed))

    def test_material_parser(self) -> None:
        parsed = self.parser.parse("SE Databases mein normalization notes upload karo")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.intent, "material")
        self.assertEqual(parsed.course, "SE Databases")
        self.assertEqual(parsed.title, "normalization")

    def test_pdf_upload_is_material_even_when_attachment_contains_task(self) -> None:
        parsed = self.parser.parse(
            "SE Software Requirement Engineering mein pdf upload karo: "
            "Title: SRE INTRODUCTION Attach: Task Req def and specification"
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.intent, "material")
        self.assertEqual(parsed.course, "SE Software Requirement Engineering")
        self.assertEqual(parsed.title, "SRE INTRODUCTION")
        self.assertEqual(parsed.attachment_query, "Task Req def and specification")
        self.assertTrue(parsed.is_complete)

    def test_announcement_parser(self) -> None:
        parsed = self.parser.parse(
            "SE Databases mein announcement post karo: Kal class cancel hai"
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.intent, "announcement")
        self.assertEqual(parsed.course, "SE Databases")
        self.assertEqual(parsed.title, "Kal class cancel hai")

    def test_ai_quiz_parser(self) -> None:
        parsed = self.parser.parse(
            "Generate quiz for SE Software Requirement Engineering Topic: Use cases Deadline 10 July 2026 5 PM Marks 10"
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.intent, "ai_generate")
        self.assertEqual(parsed.generated_kind, "quiz")
        self.assertEqual(parsed.course, "SE Software Requirement Engineering")
        self.assertEqual(parsed.title, "Use cases")
        self.assertEqual(parsed.deadline, "10 July 2026 5 PM")
        self.assertEqual(parsed.marks, 10)

    def test_multi_class_course_text_is_kept_for_workflow(self) -> None:
        parsed = self.parser.parse(
            "SE Databases and SE Software Requirement Engineering mein announcement post karo: Submit projects today"
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.course, "SE Databases and SE Software Requirement Engineering")


if __name__ == "__main__":
    unittest.main()
