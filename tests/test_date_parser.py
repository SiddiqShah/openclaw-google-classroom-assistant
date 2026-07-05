from __future__ import annotations

import unittest
from datetime import datetime

from classroom_assistant.date_parser import parse_deadline


class DateParserTests(unittest.TestCase):
    def test_parse_named_month_deadline(self) -> None:
        parsed = parse_deadline("15 July 2026 6 PM", now=datetime(2026, 7, 4, 12, 0))

        self.assertEqual(parsed.due_date, {"year": 2026, "month": 7, "day": 15})
        self.assertEqual(parsed.due_time, {"hours": 18, "minutes": 0})

    def test_parse_weekday_deadline(self) -> None:
        parsed = parse_deadline("Friday 5 PM", now=datetime(2026, 7, 4, 12, 0))

        self.assertEqual(parsed.due_date, {"year": 2026, "month": 7, "day": 10})
        self.assertEqual(parsed.due_time, {"hours": 17, "minutes": 0})


if __name__ == "__main__":
    unittest.main()
