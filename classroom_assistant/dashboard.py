from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .database import Database
from .rag_assistant.store import RagStore
from .whatsapp_notifier import WhatsAppNotifier


class DashboardServer:
    def __init__(self, database: Database, rag_store: RagStore, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.database = database
        self.rag_store = rag_store
        self.host = host
        self.port = port

    def serve(self) -> None:
        database = self.database
        rag_store = self.rag_store

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path
                if path not in {"/", "/dashboard"}:
                    self.send_error(404)
                    return
                body = render_dashboard(database, rag_store)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format, *args):
                return

        server = ThreadingHTTPServer((self.host, self.port), Handler)
        print(f"Dashboard running: http://{self.host}:{self.port}")
        server.serve_forever()


def render_dashboard(database: Database, rag_store: RagStore) -> str:
    teachers = database.list_teachers()
    teacher = teachers[0] if teachers else None
    teacher_id = int(teacher["id"]) if teacher else 0
    phone = str(teacher["phone"]) if teacher else ""
    courses = database.list_courses_by_teacher_id(teacher_id) if teacher else []
    assignments = database.latest_assignments(teacher_id, limit=10) if teacher else []
    materials = database.latest_materials(teacher_id, limit=10) if teacher else []
    announcements = database.latest_announcements(teacher_id, limit=10) if teacher else []
    documents = rag_store.list_documents(phone) if phone else []
    errors = database.latest_error_logs(limit=10)
    outbox = WhatsAppNotifier().list_queued(limit=10)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Classroom Assistant Dashboard</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f7f8fa; color: #1f2937; }}
    header {{ background: #12343b; color: white; padding: 18px 28px; }}
    main {{ padding: 24px; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 18px; }}
    section {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    h1 {{ margin: 0; font-size: 22px; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #edf0f2; text-align: left; padding: 8px; vertical-align: top; }}
    th {{ color: #52616b; font-weight: 600; }}
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
  <header><h1>Google Classroom Assistant Dashboard</h1><div>{escape(phone or "No teacher configured")}</div></header>
  <main>
    {section("Courses", table(courses, ["name", "section", "state"]))}
    {section("Assignments", table(assignments, ["title", "course_name", "state", "due_at"]))}
    {section("Materials", table(materials, ["title", "course_name", "state"]))}
    {section("Announcements", table(announcements, ["text", "course_name", "state"]))}
    {section("RAG Documents", table(documents, ["id", "title", "category", "status", "chunk_count"]))}
    {section("Errors", table(errors, ["created_at", "action", "error_type", "message"]))}
    {section("WhatsApp Outbox", table(outbox, ["created_at", "phone", "reason"]))}
  </main>
</body>
</html>"""


def section(title: str, content: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{content}</section>"


def table(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return '<div class="muted">No records yet.</div>'
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def escape(value: str) -> str:
    return html.escape(value, quote=True)
