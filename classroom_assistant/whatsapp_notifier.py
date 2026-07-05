from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


OUTBOX_PATH = Path(__file__).resolve().parents[1] / "data" / "outbox" / "whatsapp_outbox.jsonl"


@dataclass(frozen=True)
class WhatsAppSendResult:
    sent: bool
    queued: bool
    message: str


class WhatsAppNotifier:
    WEBHOOK_ENV = "OPENCLAW_WHATSAPP_SEND_WEBHOOK"

    def __init__(self, outbox_path: Path = OUTBOX_PATH) -> None:
        self.outbox_path = outbox_path

    def send(self, phone: str, text: str) -> WhatsAppSendResult:
        webhook = os.environ.get(self.WEBHOOK_ENV, "").strip()
        payload = {"to": phone, "text": text}
        if webhook:
            try:
                request = urllib.request.Request(
                    webhook,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    response.read()
                return WhatsAppSendResult(sent=True, queued=False, message="Sent via webhook.")
            except Exception as exc:
                self.queue(phone, text, reason=f"webhook failed: {exc}")
                return WhatsAppSendResult(sent=False, queued=True, message=f"Webhook failed; queued: {exc}")

        self.queue(phone, text, reason="webhook not configured")
        return WhatsAppSendResult(sent=False, queued=True, message="Queued; webhook not configured.")

    def queue(self, phone: str, text: str, reason: str) -> None:
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.outbox_path.write_text("", encoding="utf-8") if not self.outbox_path.exists() else None
        with self.outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "phone": phone,
                        "text": text,
                        "reason": reason,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                    }
                )
                + "\n"
            )

    def list_queued(self, limit: int = 20) -> list[dict]:
        if not self.outbox_path.exists():
            return []
        lines = self.outbox_path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]
