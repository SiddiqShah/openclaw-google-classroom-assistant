from __future__ import annotations

import unittest

from assistant_cli import render_name_list


class SubmissionReportRenderingTests(unittest.TestCase):
    def test_render_name_list_limits_long_lists(self) -> None:
        names = [f"Student {index}" for index in range(1, 13)]

        rendered = render_name_list("Missing students", names, limit=10)

        self.assertIn("Missing students:", rendered)
        self.assertIn("- Student 1", rendered)
        self.assertIn("- Student 10", rendered)
        self.assertNotIn("- Student 11", rendered)
        self.assertIn("...and 2 more", rendered)

    def test_render_name_list_skips_empty_lists(self) -> None:
        self.assertEqual(render_name_list("Late students", []), "")


if __name__ == "__main__":
    unittest.main()
