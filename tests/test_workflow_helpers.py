from __future__ import annotations

import unittest

from classroom_assistant.workflow import split_course_selectors


class WorkflowHelperTests(unittest.TestCase):
    def test_split_course_selectors(self) -> None:
        selectors = split_course_selectors("SE Databases and SE SRE, SE OS")

        self.assertEqual(selectors, ["SE Databases", "SE SRE", "SE OS"])


if __name__ == "__main__":
    unittest.main()
