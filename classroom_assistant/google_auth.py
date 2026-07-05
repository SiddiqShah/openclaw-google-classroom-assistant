from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .access_control import normalize_phone
from .database import Database
from .security import TokenCipher, TokenSecurityError


CLASSROOM_READONLY_SCOPE = "https://www.googleapis.com/auth/classroom.courses.readonly"
CLASSROOM_COURSEWORK_SCOPE = "https://www.googleapis.com/auth/classroom.coursework.students"
CLASSROOM_MATERIALS_SCOPE = "https://www.googleapis.com/auth/classroom.courseworkmaterials"
CLASSROOM_ANNOUNCEMENTS_SCOPE = "https://www.googleapis.com/auth/classroom.announcements"
CLASSROOM_ROSTERS_READONLY_SCOPE = "https://www.googleapis.com/auth/classroom.rosters.readonly"
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DEFAULT_SCOPES = [
    CLASSROOM_READONLY_SCOPE,
    CLASSROOM_COURSEWORK_SCOPE,
    CLASSROOM_MATERIALS_SCOPE,
    CLASSROOM_ANNOUNCEMENTS_SCOPE,
    CLASSROOM_ROSTERS_READONLY_SCOPE,
    DRIVE_FILE_SCOPE,
    DRIVE_READONLY_SCOPE,
]


class GoogleAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class CredentialCheck:
    path: Path
    valid: bool
    client_type: str
    message: str


@dataclass(frozen=True)
class GoogleConnectionStatus:
    teacher_name: str
    teacher_phone: str
    configured_email: str
    connected: bool
    token_path: str
    scopes: list[str]
    message: str


class GoogleAuthService:
    def __init__(self, database: Database, project_root: Path) -> None:
        self.database = database
        self.project_root = project_root
        self.credentials_path = project_root / "secrets" / "google_oauth_client.json"
        self.token_dir = project_root / "secrets" / "tokens"
        self.token_cipher = TokenCipher()

    def check_credentials_file(self) -> CredentialCheck:
        if not self.credentials_path.exists():
            alternate = self.project_root / "secrets" / "google_oauth_client.json.json"
            if alternate.exists():
                return CredentialCheck(
                    path=alternate,
                    valid=False,
                    client_type="unknown",
                    message=(
                        "Credentials file exists with .json.json extension. "
                        "Rename/copy it to secrets/google_oauth_client.json."
                    ),
                )
            return CredentialCheck(
                path=self.credentials_path,
                valid=False,
                client_type="missing",
                message="Missing secrets/google_oauth_client.json.",
            )

        try:
            data = json.loads(self.credentials_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return CredentialCheck(
                path=self.credentials_path,
                valid=False,
                client_type="invalid-json",
                message=f"Credentials JSON is invalid: {exc}",
            )

        if "installed" in data:
            client_type = "installed"
            required = ["client_id", "client_secret", "auth_uri", "token_uri"]
            missing = [key for key in required if not data["installed"].get(key)]
            if missing:
                return CredentialCheck(
                    path=self.credentials_path,
                    valid=False,
                    client_type=client_type,
                    message=f"Desktop OAuth credentials missing fields: {', '.join(missing)}.",
                )
            return CredentialCheck(
                path=self.credentials_path,
                valid=True,
                client_type=client_type,
                message="Desktop OAuth credentials file is ready.",
            )

        if "web" in data:
            return CredentialCheck(
                path=self.credentials_path,
                valid=False,
                client_type="web",
                message="This is a Web OAuth client. Create/download a Desktop app OAuth client instead.",
            )

        return CredentialCheck(
            path=self.credentials_path,
            valid=False,
            client_type="unknown",
            message="Credentials JSON does not contain an installed Desktop OAuth client.",
        )

    def login(self, phone: str, scopes: list[str] | None = None) -> GoogleConnectionStatus:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized. Add the teacher before Google login.")

        credential_check = self.check_credentials_file()
        if not credential_check.valid:
            raise GoogleAuthError(credential_check.message)

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise GoogleAuthError(
                "Google OAuth dependencies are missing. Run: "
                ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc

        selected_scopes = scopes or DEFAULT_SCOPES
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_path),
            scopes=selected_scopes,
        )
        credentials = flow.run_local_server(port=0)

        self.token_dir.mkdir(parents=True, exist_ok=True)
        token_path = self.token_dir / f"teacher_{teacher['id']}.json"
        self.token_cipher.write_token(token_path, credentials.to_json())

        self.database.upsert_google_token(
            teacher_id=int(teacher["id"]),
            token_path=str(token_path),
            scopes=" ".join(selected_scopes),
            connected_email=str(teacher.get("google_email", "")),
        )

        return self.status(phone)

    def status(self, phone: str) -> GoogleConnectionStatus:
        teacher = self.database.get_teacher_by_phone(normalize_phone(phone))
        if teacher is None:
            raise GoogleAuthError("Teacher phone is not authorized.")

        token = self.database.get_google_token_by_teacher_id(int(teacher["id"]))
        if token is None:
            return GoogleConnectionStatus(
                teacher_name=str(teacher["name"]),
                teacher_phone=str(teacher["phone"]),
                configured_email=str(teacher.get("google_email", "")),
                connected=False,
                token_path="",
                scopes=[],
                message="Google account is not connected yet.",
            )

        token_path = Path(str(token["token_path"]))
        connected = token_path.exists()
        scopes = str(token["scopes"]).split()
        message = "Google account connected." if connected else "Google token record exists, but token file is missing."
        return GoogleConnectionStatus(
            teacher_name=str(teacher["name"]),
            teacher_phone=str(teacher["phone"]),
            configured_email=str(teacher.get("google_email", "")),
            connected=connected,
            token_path=str(token_path),
            scopes=scopes,
            message=message,
        )


def read_authorized_user_token(token_path: Path) -> str:
    try:
        return TokenCipher().read_token(token_path)
    except TokenSecurityError as exc:
        raise GoogleAuthError(str(exc)) from exc
