from __future__ import annotations

import json
import os
from pathlib import Path


class TokenSecurityError(RuntimeError):
    pass


class TokenCipher:
    ENV_KEY = "CLASSROOM_ASSISTANT_TOKEN_KEY"

    def __init__(self) -> None:
        self.key = os.environ.get(self.ENV_KEY, "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.key)

    def encrypt_text(self, value: str) -> str:
        if not self.enabled:
            return value
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise TokenSecurityError(
                "Token encryption needs cryptography. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc
        encrypted = Fernet(self.key.encode("utf-8")).encrypt(value.encode("utf-8")).decode("utf-8")
        return json.dumps({"encrypted": True, "scheme": "fernet", "payload": encrypted})

    def decrypt_text(self, value: str) -> str:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return value
        if not isinstance(payload, dict) or not payload.get("encrypted"):
            return value
        if not self.enabled:
            raise TokenSecurityError(f"Encrypted token found but {self.ENV_KEY} is not set.")
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise TokenSecurityError(
                "Token decryption needs cryptography. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
            ) from exc
        return Fernet(self.key.encode("utf-8")).decrypt(str(payload["payload"]).encode("utf-8")).decode("utf-8")

    def write_token(self, path: Path, token_json: str) -> None:
        path.write_text(self.encrypt_text(token_json), encoding="utf-8")

    def read_token(self, path: Path) -> str:
        return self.decrypt_text(path.read_text(encoding="utf-8"))
