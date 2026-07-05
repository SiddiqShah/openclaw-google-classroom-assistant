from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from classroom_assistant.access_control import AccessController
from classroom_assistant.database import Database
from classroom_assistant.google_auth import GoogleAuthService


class GoogleAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name)
        (self.project_root / "secrets").mkdir()
        self.database = Database(self.project_root / "data" / "test.sqlite")
        self.database.initialize()
        self.controller = AccessController(self.database)
        self.service = GoogleAuthService(self.database, self.project_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_missing_credentials_file(self) -> None:
        result = self.service.check_credentials_file()

        self.assertFalse(result.valid)
        self.assertIn("Missing", result.message)

    def test_desktop_credentials_file_is_valid(self) -> None:
        credentials = {
            "installed": {
                "client_id": "fake-client-id",
                "client_secret": "fake-client-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        (self.project_root / "secrets" / "google_oauth_client.json").write_text(
            json.dumps(credentials),
            encoding="utf-8",
        )

        result = self.service.check_credentials_file()

        self.assertTrue(result.valid)
        self.assertEqual(result.client_type, "installed")

    def test_status_before_login(self) -> None:
        self.controller.add_teacher("Mr.Siddiq", "+923018083053", "bsse.233202025a@imsciences.edu.pk")

        status = self.service.status("+923018083053")

        self.assertFalse(status.connected)
        self.assertIn("not connected", status.message)


if __name__ == "__main__":
    unittest.main()
