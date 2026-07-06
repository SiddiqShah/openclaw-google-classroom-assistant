from __future__ import annotations

import unittest
from dataclasses import dataclass

from assistant_cli import render_submission_report
from classroom_assistant.command_parser import CommandParser
from classroom_assistant.report_query import (
    is_deadline_query,
    is_due_today_query,
    is_report_query,
    resolve_named,
)


@dataclass
class FakeCourse:
    id: str
    display_name: str


class ReportDetectionTests(unittest.TestCase):
    def test_report_phrasings_are_detected(self) -> None:
        for text in [
            "generate the assignment report of database class",
            "how many student complete the assignment",
            "who submitted the OS assignment",
            "kitne students ne assignment submit kiya",
            "submission report for Databases",
            "assignment status of software engineering",
        ]:
            self.assertTrue(is_report_query(text), text)

    def test_create_commands_are_not_reports(self) -> None:
        for text in [
            "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25.",
            "SE Databases mein normalization notes upload karo",
            "Generate quiz for SE SRE Topic: Use cases Deadline 10 July 2026 5 PM Marks 10",
            "how many classes do i have",
            "meri classes dikhao",
        ]:
            self.assertFalse(is_report_query(text), text)

    def test_parser_does_not_treat_reports_as_create_commands(self) -> None:
        parser = CommandParser()
        for text in [
            "generate the assignment report of database class",
            "how many student complete the assignment",
        ]:
            self.assertIsNone(parser.parse(text), text)


class DeadlineQueryTests(unittest.TestCase):
    def test_free_form_deadline_questions(self) -> None:
        for text in [
            "check all the classes and give me the submission deadlines",
            "give me the submission deadlines",
            "show deadlines",
            "upcoming deadlines",
            "reminders",
            "what are my deadlines",
            "when are assignments due",
            "due soon",
        ]:
            self.assertTrue(is_deadline_query(text), text)

    def test_create_commands_are_not_deadline_queries(self) -> None:
        for text in [
            "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM.",
            "make an assignment on Joins for databases deadline 9/7/2026 5pm",
            "meri classes dikhao",
        ]:
            self.assertFalse(is_deadline_query(text), text)

    def test_bare_draft_answers_are_not_deadline_queries(self) -> None:
        # A follow-up answer supplying a date must reach the draft, not the
        # deadline-reminder path.
        self.assertFalse(is_deadline_query("tomorrow 5pm"))
        self.assertFalse(is_deadline_query("10 July 2026 5 pm"))

    def test_due_today(self) -> None:
        for text in ["due today", "deadlines today", "what is due today"]:
            self.assertTrue(is_due_today_query(text), text)
        self.assertFalse(is_due_today_query("upcoming deadlines"))


class ResolveNamedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.courses = [
            FakeCourse("1", "SE Databases"),
            FakeCourse("2", "SE Operating System"),
            FakeCourse("3", "SE Software Requirement Engineering"),
        ]

    def _resolve(self, text: str):
        return resolve_named(self.courses, text, name_of=lambda c: c.display_name)

    def test_matches_plural_and_partial(self) -> None:
        self.assertEqual(self._resolve("report of database class").id, "1")

    def test_matches_acronym(self) -> None:
        self.assertEqual(self._resolve("who submitted the OS assignment").id, "2")
        self.assertEqual(self._resolve("sre assignment status").id, "3")

    def test_returns_none_without_a_match(self) -> None:
        self.assertIsNone(self._resolve("how many students submitted"))


class FakeDatabase:
    def __init__(self, assignments: list[dict]) -> None:
        self._assignments = assignments

    def get_teacher_by_phone(self, phone: str) -> dict:
        return {"id": 1}

    def latest_assignments(self, teacher_id: int, limit: int = 10) -> list[dict]:
        return list(self._assignments)


class FakeClassroom:
    def __init__(self, courses: list[FakeCourse], submissions: dict, students: dict) -> None:
        self._courses = courses
        self._submissions = submissions
        self._students = students
        self.reported_course_id = ""

    def list_courses(self, phone: str, sync: bool = False) -> list[FakeCourse]:
        return list(self._courses)

    def list_submissions(self, phone: str, course_id: str, coursework_id: str) -> list[dict]:
        self.reported_course_id = course_id
        return self._submissions[course_id]

    def list_students(self, phone: str, course_id: str) -> dict:
        return self._students.get(course_id, {})


class SubmissionReportTests(unittest.TestCase):
    def _fakes(self):
        assignments = [
            {
                "google_course_id": "2",
                "google_coursework_id": "cw-os",
                "title": "Deadlock Assignment",
                "course_name": "SE Operating System",
            },
            {
                "google_course_id": "1",
                "google_coursework_id": "cw-db",
                "title": "Normalization Assignment",
                "course_name": "SE Databases",
            },
        ]
        courses = [FakeCourse("1", "SE Databases"), FakeCourse("2", "SE Operating System")]
        submissions = {
            "1": [
                {"userId": "s1", "state": "TURNED_IN", "late": "False"},
                {"userId": "s2", "state": "CREATED", "late": "False"},
                {"userId": "s3", "state": "TURNED_IN", "late": "True"},
            ],
            "2": [{"userId": "s9", "state": "CREATED", "late": "False"}],
        }
        students = {"1": {"s1": "Ali", "s2": "Sara", "s3": "Bilal"}}
        return FakeDatabase(assignments), FakeClassroom(courses, submissions, students)

    def test_report_scopes_to_named_course(self) -> None:
        database, classroom = self._fakes()
        report = render_submission_report(
            database=database,
            classroom=classroom,
            phone="+1234567890",
            query_text="how many students completed the database assignment",
        )
        # Must target the Databases course, not the most-recent (OS) assignment.
        self.assertEqual(classroom.reported_course_id, "1")
        self.assertIn("Normalization Assignment", report)
        self.assertIn("Completed: 2 of 3 students submitted", report)
        self.assertIn("Late: 1", report)
        self.assertIn("Sara", report)  # missing student listed by name

    def test_report_without_course_uses_latest_assignment(self) -> None:
        database, classroom = self._fakes()
        report = render_submission_report(
            database=database,
            classroom=classroom,
            phone="+1234567890",
            query_text="submission report",
        )
        self.assertEqual(classroom.reported_course_id, "2")
        self.assertIn("Deadlock Assignment", report)


if __name__ == "__main__":
    unittest.main()
