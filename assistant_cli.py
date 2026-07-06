from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Documents (and Urdu/Arabic text) contain characters outside the Windows
# console's default cp1252 encoding. Force UTF-8 so printing an answer never
# crashes with UnicodeEncodeError (which previously killed `rag-ask`).
for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from classroom_assistant.access_control import AccessController, normalize_phone
from classroom_assistant.classroom_api import ClassroomService
from classroom_assistant.command_parser import CommandParser, ParsedCommand, render_preview
from classroom_assistant.database import Database
from classroom_assistant.dashboard import DashboardServer
from classroom_assistant.drive_service import DriveService
from classroom_assistant.file_receiver import FileReceiveError, FileReceiver, render_file_received
from classroom_assistant.google_auth import GoogleAuthError, GoogleAuthService
from classroom_assistant.local_file_search import LocalFileSearch, LocalFileSearchError
from classroom_assistant.rag_assistant.document_upload import RagDocumentUploader, RagUploadError
from classroom_assistant.rag_assistant.config import SUPPORTED_DOCUMENT_EXTENSIONS
from classroom_assistant.rag_assistant.generator import RagGenerationError, RagQuizGenerator
from classroom_assistant.rag_assistant.processor import RagProcessingError, RagProcessor
from classroom_assistant.rag_assistant.qa import RagQuestionAnswerer
from classroom_assistant.rag_assistant.store import RagStore
from classroom_assistant.reminder_service import ReminderService
from classroom_assistant.report_query import (
    is_deadline_query,
    is_due_today_query,
    is_report_query,
    resolve_named,
)
from classroom_assistant.security import TokenCipher, TokenSecurityError
from classroom_assistant.whatsapp_notifier import WhatsAppNotifier
from classroom_assistant.workflow import WorkflowService


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "data" / "classroom_assistant.sqlite"


def build_controller(db_path: Path) -> AccessController:
    database = Database(db_path)
    database.initialize()
    return AccessController(database)


def cmd_init_db(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    print(f"Database ready: {database.path}")
    return 0


def cmd_add_teacher(args: argparse.Namespace) -> int:
    controller = build_controller(Path(args.db))
    teacher = controller.add_teacher(
        name=args.name,
        phone=args.phone,
        google_email=args.google_email,
    )
    print(f"Teacher authorized: {teacher.name} ({teacher.phone})")
    return 0


def cmd_list_teachers(args: argparse.Namespace) -> int:
    controller = build_controller(Path(args.db))
    teachers = controller.list_teachers()
    if not teachers:
        print("No authorized teachers yet.")
        return 0

    for index, teacher in enumerate(teachers, start=1):
        email = teacher.google_email or "Google account not connected"
        print(f"{index}. {teacher.name} - {teacher.phone} - {email}")
    return 0


def cmd_remove_teacher(args: argparse.Namespace) -> int:
    controller = build_controller(Path(args.db))
    removed = controller.remove_teacher_phone(args.phone)
    if removed:
        print(f"Teacher phone removed: {args.phone}")
        return 0
    print(f"No active teacher found for phone: {args.phone}")
    return 1


def cmd_check(args: argparse.Namespace) -> int:
    controller = build_controller(Path(args.db))
    result = controller.authorize(phone=args.phone, channel_type=args.channel)
    print(result.message)
    return 0 if result.allowed else 1


def cmd_message(args: argparse.Namespace) -> int:
    db_path = Path(args.db)
    controller = build_controller(db_path)
    auth_result = controller.authorize(phone=args.phone, channel_type=args.channel)
    if not auth_result.allowed:
        controller.database.log_access_attempt(
            phone=args.phone,
            channel_type=args.channel,
            message=args.text,
            allowed=False,
        )
        return 0

    routed = route_classroom_message(db_path=db_path, phone=args.phone, text=args.text)
    if routed:
        controller.database.log_access_attempt(
            phone=args.phone,
            channel_type=args.channel,
            message=args.text,
            allowed=True,
        )
        print(routed)
        return 0

    reply = controller.handle_message(
        phone=args.phone,
        text=args.text,
        channel_type=args.channel,
    )
    if reply:
        print(reply)
    return 0


def route_classroom_message(db_path: Path, phone: str, text: str) -> str | None:
    normalized = text.strip().lower()
    database = Database(db_path)
    database.initialize()
    classroom = ClassroomService(database)
    workflow = WorkflowService(database)
    reminders = ReminderService(database)
    file_receiver = FileReceiver(database=database, project_root=PROJECT_ROOT)

    rag_reply = route_rag_message(phone=phone, text=text, workflow=workflow)
    if rag_reply:
        return rag_reply

    try:
        confirmation_reply = workflow.handle_confirmation(phone=phone, reply=text)
    except GoogleAuthError as exc:
        database.log_error(phone=phone, action="confirm_action", error_type=type(exc).__name__, message=str(exc))
        return f"Could not complete action: {exc}"
    if confirmation_reply:
        return confirmation_reply

    file_match = re.search(r"^receive\s+file\s+(?P<path>.+)$", text.strip(), re.IGNORECASE)
    if file_match:
        source_path = Path(file_match.group("path").strip().strip('"'))
        try:
            staged = file_receiver.receive(phone=phone, source_path=source_path)
        except (GoogleAuthError, FileReceiveError) as exc:
            return f"Could not receive file: {exc}"
        return render_file_received(staged)

    if any(phrase in normalized for phrase in ["meri classes", "classes dikhao", "list classes", "show classes"]):
        try:
            courses = classroom.list_courses(phone=phone, sync=True)
        except GoogleAuthError as exc:
            return f"Could not list classes: {exc}"
        return render_course_list(courses)

    if is_report_query(normalized):
        return render_submission_report(
            database=database,
            classroom=classroom,
            phone=phone,
            query_text=text,
        )

    if looks_like_class_summary_question(normalized):
        try:
            courses = classroom.list_courses(phone=phone, sync=True)
        except GoogleAuthError as exc:
            return f"Could not check classes: {exc}"
        return render_class_summary(courses)

    if normalized.isdigit():
        try:
            selected = classroom.select_course(phone=phone, selector=normalized)
        except GoogleAuthError:
            selected = None
        if selected is not None:
            return (
                f"{selected.display_name} selected.\n"
                "Now you can create an assignment, upload material, or post an announcement."
            )
        menu_reply = handle_menu_choice(normalized, reminders, database, classroom, phone)
        if menu_reply:
            return menu_reply

    select_match = re.search(r"(?:class|course)\s+(.+?)\s+(?:select|choose|chuno|karo)", normalized)
    if not select_match:
        select_match = re.search(r"(?:select|choose|chuno)\s+(?:class|course)\s+(.+)", normalized)
    if select_match:
        selector = select_match.group(1).strip()
        try:
            selected = classroom.select_course(phone=phone, selector=selector)
        except GoogleAuthError as exc:
            return f"Could not select class: {exc}"
        return (
            f"{selected.display_name} selected.\n"
            "Ab aap assignment, material ya announcement create kar sakte hain."
        )

    if normalized in {"selected class", "current class", "class selected"}:
        try:
            selected = classroom.selected_course(phone=phone)
        except GoogleAuthError as exc:
            return f"Could not check selected class: {exc}"
        if selected is None:
            return "No class selected yet. Send: Meri classes dikhao"
        return f"Selected class: {selected.display_name}"

    if any(phrase in normalized for phrase in ["history", "activity", "activity log", "recent posts"]):
        return render_history(database=database, phone=phone)

    if any(phrase in normalized for phrase in ["debug logs", "error logs", "recent errors"]):
        return render_error_logs(database=database)

    if is_due_today_query(normalized):
        return reminders.render_due_today(phone=phone)

    if is_deadline_query(normalized):
        return reminders.render_upcoming_deadlines(phone=phone)

    parsed = CommandParser().parse(text)
    if parsed is None:
        # Not a fresh command: it may be the teacher answering a question we
        # asked earlier (e.g. supplying a missing topic or deadline).
        try:
            draft_reply = workflow.continue_draft(phone=phone, text=text)
        except GoogleAuthError as exc:
            database.log_error(phone=phone, action="continue_draft", error_type=type(exc).__name__, message=str(exc))
            return f"Could not continue: {exc}"
        return draft_reply

    try:
        return workflow.handle_command(phone=phone, command=parsed, text=text)
    except GoogleAuthError as exc:
        database.log_error(phone=phone, action="prepare_preview", error_type=type(exc).__name__, message=str(exc))
        return f"Could not prepare preview: {exc}"


def looks_like_class_summary_question(normalized: str) -> bool:
    return (
        ("how many" in normalized and "class" in normalized)
        or ("what" in normalized and "subject" in normalized)
        or "subjects we have" in normalized
        or "classes we have" in normalized
    )


def handle_menu_choice(
    normalized: str,
    reminders: ReminderService,
    database: Database,
    classroom: ClassroomService,
    phone: str,
) -> str | None:
    if normalized == "1":
        return (
            "Send assignment details like:\n"
            "SE Databases mein Normalization assignment banao. Deadline 20 July 2026 5 PM. Marks 20."
        )
    if normalized == "2":
        return (
            "Send material details like:\n"
            "SE Operating System mein material upload karo: Title: CPU Scheduling Attach from Drive: CPU Scheduling"
        )
    if normalized == "3":
        return (
            "Send announcement details like:\n"
            "SE Software Requirement Engineering mein announcement post karo: Tomorrow class is cancelled."
        )
    if normalized == "4":
        return reminders.render_upcoming_deadlines(phone=phone)
    if normalized == "5":
        return render_submission_report(database=database, classroom=classroom, phone=phone)
    return None


def route_rag_message(phone: str, text: str, workflow: WorkflowService) -> str | None:
    normalized = text.strip().lower()
    store = RagStore()
    store.initialize()

    if normalized in {"rag menu", "docs menu", "document menu"}:
        return (
            "RAG Document Assistant:\n\n"
            "1. Upload document from terminal: rag-upload\n"
            "2. Ask: Ask docs: your question\n"
            "3. List: List documents\n"
            "4. Reprocess: Reprocess document 1\n"
            "5. Delete: Delete document 1\n"
            "6. Generate MCQs: Create 10 MCQs from docs for Class Name Topic: Photosynthesis Deadline 20 July 2026 5 PM"
        )

    if normalized in {"list documents", "rag documents", "list docs"}:
        return render_rag_documents(store, phone)

    ask_match = re.search(r"^(?:ask docs|ask documents|rag ask)\s*:?\s*(?P<question>.+)$", text.strip(), re.IGNORECASE)
    if ask_match:
        answer = RagQuestionAnswerer(store).answer(owner_phone=phone, question=ask_match.group("question").strip())
        return render_rag_answer(answer)

    reprocess_all_match = re.search(r"^(?:reprocess|process)\s+all\s+(?:documents|docs)$", normalized)
    if reprocess_all_match:
        return process_rag_documents_for_reply(store, phone, all_documents=True)

    reprocess_latest_match = re.search(r"^(?:reprocess|process)\s+(?:latest|last)\s+(?:document|doc)$", normalized)
    if reprocess_latest_match:
        return process_rag_documents_for_reply(store, phone, latest=True)

    reprocess_match = re.search(r"^(?:reprocess|process)\s+(?:document|doc)\s+(?P<selector>.+)$", text.strip(), re.IGNORECASE)
    if reprocess_match:
        selector = reprocess_match.group("selector").strip()
        if selector.isdigit():
            return process_rag_documents_for_reply(store, phone, document_id=int(selector))
        return process_rag_documents_for_reply(store, phone, title=selector)

    delete_match = re.search(r"^delete\s+(?:document|doc)\s+(?P<id>\d+)$", normalized)
    if delete_match:
        deleted = store.delete_document(int(delete_match.group("id")), phone)
        return "Document deleted." if deleted else "Document not found."

    mcq_match = re.search(
        r"^(?:create|generate)\s+(?P<count>\d+)?\s*mcqs?\s+from\s+docs?\s+for\s+(?P<course>.+?)\s+"
        r"(?:topic|title)\s*:?\s*(?P<topic>.+?)(?:\s+deadline\s+(?P<deadline>.+?))?(?:\s+marks\s+(?P<marks>\d+))?$",
        text.strip(),
        re.IGNORECASE,
    )
    if mcq_match:
        count = int(mcq_match.group("count") or 10)
        topic = mcq_match.group("topic").strip()
        deadline = (mcq_match.group("deadline") or "").strip()
        marks_text = mcq_match.group("marks")
        marks = int(marks_text) if marks_text else count
        if not deadline:
            return "I need a deadline before I can prepare the Classroom assignment."
        try:
            instructions = RagQuizGenerator(store).generate_mcqs(phone, topic=topic, count=count)
        except RagGenerationError as exc:
            return f"Could not generate MCQs from documents: {exc}"

        command = ParsedCommand(
            intent="assignment",
            course=mcq_match.group("course").strip(),
            title=f"{topic} MCQ Quiz",
            deadline=deadline,
            marks=marks,
            description=instructions,
        )
        try:
            return workflow.save_preview(phone=phone, command=command)
        except GoogleAuthError as exc:
            return f"Could not prepare Classroom preview from RAG: {exc}"

    return None


def render_rag_answer(answer) -> str:
    if not answer.sources:
        return answer.answer
    sources = "\n".join(f"{index}. {source}" for index, source in enumerate(answer.sources, start=1))
    return f"{answer.answer}\n\nAnswer based on:\n{sources}"


def render_rag_documents(store: RagStore, phone: str) -> str:
    documents = store.list_documents(phone)
    if not documents:
        return "No RAG documents uploaded yet."
    lines = ["RAG documents:"]
    for index, document in enumerate(documents, start=1):
        category = document["category"] or "No category"
        chunk_count = document.get("chunk_count", 0)
        lines.append(
            f"{index}. ID {document['id']} | {document['title']} | {category} | "
            f"{document['status']} | chunks: {chunk_count}"
        )
    return "\n".join(lines)


def process_rag_documents_for_reply(
    store: RagStore,
    phone: str,
    document_id: int | None = None,
    title: str = "",
    latest: bool = False,
    all_documents: bool = False,
) -> str:
    try:
        results = process_rag_documents(
            store=store,
            phone=phone,
            document_id=document_id,
            title=title,
            latest=latest,
            all_documents=all_documents,
        )
    except RagProcessingError as exc:
        return f"Could not reprocess document: {exc}"
    if not results:
        return "No matching RAG documents found."
    lines = ["RAG processing complete:"]
    for document, chunk_count in results:
        lines.append(f"- ID {document['id']} | {document['title']} | chunks indexed: {chunk_count}")
    return "\n".join(lines)


def process_rag_documents(
    store: RagStore,
    phone: str,
    document_id: int | None = None,
    title: str = "",
    latest: bool = False,
    all_documents: bool = False,
) -> list[tuple[dict, int]]:
    if all_documents:
        documents = store.find_documents(phone)
    elif latest:
        latest_document = store.latest_document(phone)
        documents = [latest_document] if latest_document else []
    elif title:
        documents = store.find_documents(phone, title)
        if len(documents) > 1:
            options = "\n".join(f"- ID {item['id']} | {item['title']} | {item['original_name']}" for item in documents[:5])
            raise RagProcessingError(f"I found multiple matching documents:\n{options}\nUse a more specific title.")
    elif document_id is not None:
        document = store.get_document(document_id, phone)
        documents = [document] if document else []
    else:
        latest_document = store.latest_document(phone, status="uploaded") or store.latest_document(phone)
        documents = [latest_document] if latest_document else []

    if not documents:
        raise RagProcessingError("No matching RAG document found. Run rag-documents first or use --all/--latest/--title.")

    processor = RagProcessor(store)
    results = []
    for document in documents:
        if document is None:
            continue
        chunk_count = processor.process_document(int(document["id"]), phone)
        results.append((document, chunk_count))
    return results


def render_history(database: Database, phone: str) -> str:
    teacher = database.get_teacher_by_phone(normalize_phone(phone))
    if teacher is None:
        return "Teacher phone is not authorized."

    teacher_id = int(teacher["id"])
    assignments = database.latest_assignments(teacher_id, limit=3)
    materials = database.latest_materials(teacher_id, limit=3)
    announcements = database.latest_announcements(teacher_id, limit=3)

    lines = ["Recent Classroom activity:"]
    if not assignments and not materials and not announcements:
        lines.append("No posted activity found yet.")
        return "\n".join(lines)

    if assignments:
        lines.append("")
        lines.append("Assignments:")
        for item in assignments:
            course = item.get("course_name") or item.get("google_course_id")
            lines.append(f"- {item['title']} | {course} | {item['state']}")
    if materials:
        lines.append("")
        lines.append("Materials:")
        for item in materials:
            course = item.get("course_name") or item.get("google_course_id")
            lines.append(f"- {item['title']} | {course} | {item['state']}")
    if announcements:
        lines.append("")
        lines.append("Announcements:")
        for item in announcements:
            course = item.get("course_name") or item.get("google_course_id")
            text = str(item["text"])
            lines.append(f"- {text[:60]} | {course} | {item['state']}")
    return "\n".join(lines)


def render_error_logs(database: Database, limit: int = 10) -> str:
    errors = database.latest_error_logs(limit=limit)
    if not errors:
        return "No recent errors logged."

    lines = ["Recent errors:"]
    for item in errors:
        lines.append(
            f"- {item['created_at']} | {item['action']} | {item['error_type']} | {item['message']}"
        )
    return "\n".join(lines)


def render_submission_report(
    database: Database,
    classroom: ClassroomService,
    phone: str,
    query_text: str = "",
) -> str:
    teacher = database.get_teacher_by_phone(normalize_phone(phone))
    if teacher is None:
        return "Teacher phone is not authorized."

    assignments = database.latest_assignments(int(teacher["id"]), limit=50)
    if not assignments:
        return "No created assignment found yet. Create an assignment first, then ask for a submission report."

    # Resolve the class the teacher named (if any) against their real courses,
    # then scope the assignment list to it. Nothing here is hard-coded to a
    # particular class name, so it works for any teacher.
    matched_course = _match_report_course(classroom, phone, query_text)
    if matched_course is not None:
        scoped = [a for a in assignments if str(a["google_course_id"]) == matched_course.id]
        if not scoped:
            return (
                f"No assignment found yet for {matched_course.display_name}. "
                "Create or sync an assignment for that class first, then ask for a report."
            )
        assignments = scoped

    # Resolve which assignment the teacher meant; fall back to the latest one.
    target = resolve_named(assignments, query_text, name_of=lambda a: str(a["title"]))
    if target is None:
        target = assignments[0]

    try:
        submissions = classroom.list_submissions(
            phone=phone,
            course_id=str(target["google_course_id"]),
            coursework_id=str(target["google_coursework_id"]),
        )
    except GoogleAuthError as exc:
        return f"Could not fetch submission report: {exc}"

    try:
        student_names = classroom.list_students(phone=phone, course_id=str(target["google_course_id"]))
        roster_note = ""
    except GoogleAuthError as exc:
        student_names = {}
        roster_note = f"\n\nStudent names unavailable: {exc}"

    submitted_states = {"TURNED_IN", "RETURNED"}
    total = len(submissions)
    submitted = sum(1 for item in submissions if item["state"] in submitted_states)
    missing = max(total - submitted, 0)
    late = sum(1 for item in submissions if item["late"] == "True")
    course = target.get("course_name") or target.get("google_course_id")
    missing_names = [
        student_names.get(item["userId"], item["userId"])
        for item in submissions
        if item["state"] not in submitted_states
    ]
    late_names = [
        student_names.get(item["userId"], item["userId"])
        for item in submissions
        if item["late"] == "True"
    ]
    missing_block = render_name_list("Missing students", missing_names)
    late_block = render_name_list("Late students", late_names)
    return (
        f"{target['title']} Submission Report\n\n"
        f"Course: {course}\n"
        f"Completed: {submitted} of {total} students submitted\n"
        f"Not turned in: {missing}\n"
        f"Late: {late}"
        f"{missing_block}"
        f"{late_block}"
        f"{roster_note}"
    )


def _match_report_course(classroom: ClassroomService, phone: str, query_text: str):
    if not query_text:
        return None
    try:
        courses = classroom.list_courses(phone=phone, sync=False)
    except GoogleAuthError:
        return None
    return resolve_named(courses, query_text, name_of=lambda c: c.display_name)


def render_name_list(title: str, names: list[str], limit: int = 10) -> str:
    if not names:
        return ""
    visible = names[:limit]
    lines = ["", "", f"{title}:"]
    lines.extend(f"- {name}" for name in visible)
    remaining = len(names) - len(visible)
    if remaining > 0:
        lines.append(f"...and {remaining} more")
    return "\n".join(lines)


def render_course_list(courses: list) -> str:
    if not courses:
        return "No active Google Classroom courses found for this teacher."

    lines = ["Your Google Classroom classes:", ""]
    for index, course in enumerate(courses, start=1):
        lines.append(f"{index}. {course.display_name}")
    lines.append("")
    lines.append("Reply with class number or class name.")
    return "\n".join(lines)


def render_class_summary(courses: list) -> str:
    if not courses:
        return "You currently have 0 active Google Classroom classes."

    lines = [f"You currently have {len(courses)} active Google Classroom class(es):", ""]
    for index, course in enumerate(courses, start=1):
        subject = clean_subject_name(course.display_name)
        lines.append(f"{index}. {course.display_name} - Subject: {subject}")
    return "\n".join(lines)


def clean_subject_name(display_name: str) -> str:
    subject = display_name.replace("(A)", "").replace("(a)", "").strip()
    if subject.lower().startswith("se "):
        subject = subject[3:].strip()
    return subject or display_name


def build_google_auth_service(db_path: Path) -> GoogleAuthService:
    database = Database(db_path)
    database.initialize()
    return GoogleAuthService(database=database, project_root=PROJECT_ROOT)


def cmd_google_check(args: argparse.Namespace) -> int:
    service = build_google_auth_service(Path(args.db))
    result = service.check_credentials_file()
    print(result.message)
    print(f"Path: {result.path}")
    print(f"Client type: {result.client_type}")
    return 0 if result.valid else 1


def cmd_google_login(args: argparse.Namespace) -> int:
    service = build_google_auth_service(Path(args.db))
    try:
        status = service.login(phone=args.phone)
    except GoogleAuthError as exc:
        print(f"Google login failed: {exc}")
        return 1

    print(status.message)
    print(f"Teacher: {status.teacher_name} ({status.teacher_phone})")
    print(f"Configured email: {status.configured_email or 'not set'}")
    print("Scopes:")
    for scope in status.scopes:
        print(f"- {scope}")
    return 0


def cmd_google_status(args: argparse.Namespace) -> int:
    service = build_google_auth_service(Path(args.db))
    try:
        status = service.status(phone=args.phone)
    except GoogleAuthError as exc:
        print(f"Google status failed: {exc}")
        return 1

    print(status.message)
    print(f"Teacher: {status.teacher_name} ({status.teacher_phone})")
    print(f"Configured email: {status.configured_email or 'not set'}")
    print(f"Connected: {'yes' if status.connected else 'no'}")
    print(f"Token encryption: {'enabled' if TokenCipher().enabled else 'disabled'}")
    if status.connected:
        print("Scopes:")
        for scope in status.scopes:
            print(f"- {scope}")
    return 0 if status.connected else 1


def cmd_security_key(args: argparse.Namespace) -> int:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("cryptography is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        return 1
    print(Fernet.generate_key().decode("utf-8"))
    return 0


def cmd_encrypt_token(args: argparse.Namespace) -> int:
    service = build_google_auth_service(Path(args.db))
    try:
        status = service.status(phone=args.phone)
    except GoogleAuthError as exc:
        print(f"Google status failed: {exc}")
        return 1
    if not status.connected or not status.token_path:
        print("Google account is not connected yet.")
        return 1
    cipher = TokenCipher()
    if not cipher.enabled:
        print(f"Set {TokenCipher.ENV_KEY} before encrypting an existing token.")
        return 1
    token_path = Path(status.token_path)
    try:
        token_json = cipher.read_token(token_path)
        cipher.write_token(token_path, token_json)
    except TokenSecurityError as exc:
        print(f"Could not encrypt token: {exc}")
        return 1
    print(f"Encrypted token: {token_path}")
    return 0


def cmd_courses(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    service = ClassroomService(database)
    try:
        courses = service.list_courses(phone=args.phone, sync=True)
    except GoogleAuthError as exc:
        print(f"Could not list courses: {exc}")
        return 1

    if not courses:
        print("No active Google Classroom courses found for this teacher.")
        return 0

    print("Your Google Classroom classes:")
    for index, course in enumerate(courses, start=1):
        print(f"{index}. {course.display_name}")
    return 0


def cmd_select_course(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    service = ClassroomService(database)
    try:
        selected = service.select_course(phone=args.phone, selector=args.selector)
    except GoogleAuthError as exc:
        print(f"Could not select class: {exc}")
        return 1

    print(f"{selected.display_name} selected.")
    return 0


def cmd_selected_course(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    service = ClassroomService(database)
    try:
        selected = service.selected_course(phone=args.phone)
    except GoogleAuthError as exc:
        print(f"Could not check selected class: {exc}")
        return 1

    if selected is None:
        print("No class selected yet.")
        return 1

    print(f"Selected class: {selected.display_name}")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    parsed = CommandParser().parse(args.text)
    if parsed is None:
        print("No Classroom command detected.")
        return 1
    print(render_preview(parsed))
    return 0


def cmd_create_assignment(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    service = ClassroomService(database)
    try:
        course = service.selected_course(args.phone)
        if course is None:
            print("No class selected yet.")
            return 1
        created = service.create_assignment(
            phone=args.phone,
            course_id=course.id,
            title=args.title,
            description=args.description,
            deadline=args.deadline,
            max_points=args.marks,
            state="DRAFT" if args.draft else "PUBLISHED",
        )
    except (GoogleAuthError, ValueError) as exc:
        print(f"Could not create assignment: {exc}")
        return 1

    state = "draft" if args.draft else "published"
    print(f"Assignment {state}: {created['title']}")
    if created.get("alternateLink"):
        print(f"Link: {created['alternateLink']}")
    return 0


def cmd_receive_file(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    receiver = FileReceiver(database=database, project_root=PROJECT_ROOT)
    try:
        staged = receiver.receive(
            phone=args.phone,
            source_path=Path(args.path),
            original_name=args.name,
        )
    except (GoogleAuthError, FileReceiveError) as exc:
        print(f"Could not receive file: {exc}")
        return 1

    print(render_file_received(staged))
    print(f"\nStaged file ID: {staged.id}")
    print(f"Staged path: {staged.staged_path}")
    return 0


def cmd_latest_file(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    receiver = FileReceiver(database=database, project_root=PROJECT_ROOT)
    try:
        staged = receiver.latest_for_teacher(args.phone)
    except GoogleAuthError as exc:
        print(f"Could not check latest file: {exc}")
        return 1

    if staged is None:
        print("No staged file found.")
        return 1

    print(f"Latest file: {staged.original_name}")
    print(f"Size: {staged.size_bytes} bytes")
    print(f"Staged path: {staged.staged_path}")
    return 0


def cmd_upload_latest_file(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    classroom = ClassroomService(database)

    course_folder = args.course_folder
    if not course_folder:
        try:
            selected = classroom.selected_course(args.phone)
        except GoogleAuthError as exc:
            print(f"Could not check selected class: {exc}")
            return 1
        course_folder = selected.display_name if selected else ""

    try:
        uploaded = drive.upload_latest_staged_file(args.phone, course_folder_name=course_folder)
    except GoogleAuthError as exc:
        print(f"Could not upload file to Drive: {exc}")
        return 1

    print("File uploaded successfully.")
    print(f"File: {uploaded.name}")
    print(f"Drive file ID: {uploaded.id}")
    if uploaded.web_view_link:
        print(f"Link: {uploaded.web_view_link}")
    return 0


def cmd_upload_folder_to_drive(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    source_root = Path(args.source)
    base_folder = args.drive_folder or source_root.name
    try:
        files = drive.supported_files_in_tree(source_root)
    except GoogleAuthError as exc:
        print(f"Could not scan folder: {exc}")
        return 1

    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print("No supported files found. Supported: .pdf, .pptx, .docx")
        return 0

    print(f"Source: {source_root}")
    print(f"Drive folder: {base_folder}")
    print(f"Supported files: {len(files)}")
    for index, file_path in enumerate(files[:20], start=1):
        relative = file_path.relative_to(source_root)
        print(f"{index}. {relative}")
    if len(files) > 20:
        print(f"...and {len(files) - 20} more")

    if args.dry_run:
        print("Dry run only. Add --execute to upload these files.")
        return 0
    if not args.execute:
        print("Nothing uploaded. Use --execute to confirm upload.")
        return 1

    uploaded_count = 0
    for file_path in files:
        relative_parent = file_path.relative_to(source_root).parent
        folder_parts = ["Classroom Assistant", base_folder]
        if str(relative_parent) != ".":
            folder_parts.extend(relative_parent.parts)
        try:
            uploaded = drive.upload_local_file(args.phone, file_path, folder_parts)
        except GoogleAuthError as exc:
            print(f"FAILED: {file_path.name} | {exc}")
            continue
        uploaded_count += 1
        print(f"UPLOADED: {file_path.relative_to(source_root)} -> {uploaded.web_view_link or uploaded.id}")

    print(f"Upload complete. Uploaded: {uploaded_count}/{len(files)}")
    return 0 if uploaded_count == len(files) else 1


def cmd_latest_drive_file(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    try:
        uploaded = drive.latest_uploaded_file(args.phone)
    except GoogleAuthError as exc:
        print(f"Could not check latest Drive file: {exc}")
        return 1
    if uploaded is None:
        print("No Drive upload found.")
        return 1
    print(f"Latest Drive file: {uploaded.name}")
    print(f"Drive file ID: {uploaded.id}")
    if uploaded.web_view_link:
        print(f"Link: {uploaded.web_view_link}")
    return 0


def cmd_find_drive_file(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    try:
        file = drive.find_file_by_name(phone=args.phone, query=args.query, folder_name=args.folder)
    except GoogleAuthError as exc:
        print(f"Could not find Drive file: {exc}")
        return 1

    print(f"Drive file found: {file.name}")
    print(f"Drive file ID: {file.id}")
    if file.web_view_link:
        print(f"Link: {file.web_view_link}")
    return 0


def cmd_list_drive_folder(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    try:
        files = drive.list_files_in_folder(phone=args.phone, folder_name=args.folder, limit=args.limit)
    except GoogleAuthError as exc:
        print(f"Could not list Drive folder: {exc}")
        return 1
    if not files:
        print(f"No supported files found in Drive folder: {args.folder}")
        return 0
    print(f"Drive folder: {args.folder}")
    for index, file in enumerate(files, start=1):
        print(f"{index}. {file.name}")
    return 0


def cmd_list_drive_folders(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    drive = DriveService(database)
    try:
        folders = drive.list_folders(phone=args.phone, limit=args.limit)
    except GoogleAuthError as exc:
        print(f"Could not list Drive folders: {exc}")
        return 1
    if not folders:
        print("No Google Drive folders found.")
        return 0
    print("Google Drive folders:")
    for index, folder in enumerate(folders, start=1):
        print(f"{index}. {folder}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    print(render_history(database=database, phone=args.phone))
    return 0


def cmd_submission_report(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    classroom = ClassroomService(database)
    print(render_submission_report(database=database, classroom=classroom, phone=args.phone))
    return 0


def cmd_deadline_reminders(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    reminders = ReminderService(database)
    print(reminders.render_upcoming_deadlines(phone=args.phone, days=args.days))
    return 0


def cmd_due_today(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    reminders = ReminderService(database)
    print(reminders.render_due_today(phone=args.phone))
    return 0


def cmd_reminder_job(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    reminders = ReminderService(database)
    teachers = database.list_teachers()
    if not teachers:
        print("No teachers configured.")
        return 0

    for teacher in teachers:
        phone = str(teacher["phone"])
        message = (
            f"Teacher: {teacher['name']} ({phone})\n"
            f"{reminders.render_due_today(phone=phone)}\n\n"
            f"{reminders.render_upcoming_deadlines(phone=phone, days=args.days)}"
        )
        if args.send:
            result = WhatsAppNotifier().send(phone, message)
            print(f"{phone}: {result.message}")
            continue
        print(f"Teacher: {teacher['name']} ({phone})")
        print(reminders.render_due_today(phone=phone))
        print("")
        print(reminders.render_upcoming_deadlines(phone=phone, days=args.days))
        print("")
    return 0


def cmd_whatsapp_outbox(args: argparse.Namespace) -> int:
    messages = WhatsAppNotifier().list_queued(limit=args.limit)
    if not messages:
        print("WhatsApp outbox is empty.")
        return 0
    print("Queued WhatsApp messages:")
    for item in messages:
        print(f"- {item['created_at']} | {item['phone']} | {item['reason']}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    rag_store = RagStore()
    rag_store.initialize()
    DashboardServer(database=database, rag_store=rag_store, host=args.host, port=args.port).serve()
    return 0


def cmd_debug_logs(args: argparse.Namespace) -> int:
    database = Database(Path(args.db))
    database.initialize()
    print(render_error_logs(database=database, limit=args.limit))
    return 0


def cmd_find_file(args: argparse.Namespace) -> int:
    try:
        matches = LocalFileSearch().search(args.query)
    except LocalFileSearchError as exc:
        print(f"Could not search files: {exc}")
        return 1

    if not matches:
        print(f"No supported file found for: {args.query}")
        return 1

    for index, match in enumerate(matches[: args.limit], start=1):
        print(f"{index}. {match.path}")
    return 0


def cmd_rag_init(args: argparse.Namespace) -> int:
    store = RagStore()
    store.initialize()
    print(f"RAG database ready: {store.path}")
    return 0


def cmd_rag_upload(args: argparse.Namespace) -> int:
    try:
        uploaded = RagDocumentUploader().upload(
            owner_phone=args.phone,
            source_path=Path(args.path),
            category=args.category,
            title=args.title,
        )
    except RagUploadError as exc:
        print(f"Could not upload RAG document: {exc}")
        return 1

    print("RAG document uploaded.")
    print(f"Document ID: {uploaded.id}")
    print(f"File: {uploaded.original_name}")
    print(f"Category: {uploaded.category or 'Not set'}")
    return 0


def cmd_rag_upload_folder(args: argparse.Namespace) -> int:
    source = Path(args.path)
    if not source.exists() or not source.is_dir():
        print(f"RAG folder not found: {source}")
        return 1

    store = RagStore()
    store.initialize()
    uploader = RagDocumentUploader(store)
    files = [
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
    ]
    files = sorted(files, key=lambda path: str(path.relative_to(source)).lower())
    if args.limit > 0:
        files = files[: args.limit]
    if not files:
        print("No supported RAG documents found. Supported: PDF, DOCX, TXT.")
        return 0

    uploaded_documents = []
    skipped = []
    for file_path in files:
        category = args.category or source.name
        if args.keep_subfolders:
            relative_parent = file_path.relative_to(source).parent
            if str(relative_parent) != ".":
                category = f"{category}/{relative_parent.as_posix()}"
        duplicate = store.find_duplicate_document(args.phone, file_path.name, category)
        if duplicate and not args.reupload:
            skipped.append(duplicate)
            print(f"SKIPPED: ID {duplicate['id']} | {file_path.name} | already uploaded")
            uploaded_documents.append(duplicate)
            continue
        try:
            uploaded = uploader.upload(
                owner_phone=args.phone,
                source_path=file_path,
                category=category,
                title=file_path.stem,
            )
        except RagUploadError as exc:
            print(f"FAILED: {file_path.name} | {exc}")
            continue
        document = store.get_document(uploaded.id, args.phone)
        if document:
            uploaded_documents.append(document)
        print(f"UPLOADED: ID {uploaded.id} | {file_path.relative_to(source)}")

    if args.process:
        processor = RagProcessor(store)
        for document in uploaded_documents:
            try:
                chunk_count = processor.process_document(int(document["id"]), args.phone)
            except RagProcessingError as exc:
                print(f"PROCESS FAILED: ID {document['id']} | {document['title']} | {exc}")
                continue
            print(f"PROCESSED: ID {document['id']} | {document['title']} | chunks: {chunk_count}")

    print(f"Folder RAG upload complete. Files seen: {len(files)} | skipped existing: {len(skipped)}")
    return 0


def cmd_rag_documents(args: argparse.Namespace) -> int:
    store = RagStore()
    store.initialize()
    documents = store.list_documents(args.phone)
    if not documents:
        print("No RAG documents uploaded yet.")
        return 0

    print("RAG documents:")
    for index, document in enumerate(documents, start=1):
        category = document["category"] or "No category"
        chunk_count = document.get("chunk_count", 0)
        print(
            f"{index}. ID {document['id']} | {document['title']} | {category} | "
            f"{document['status']} | chunks: {chunk_count} | {document['original_name']}"
        )
    return 0


def cmd_rag_ask(args: argparse.Namespace) -> int:
    answer = RagQuestionAnswerer().answer(owner_phone=args.phone, question=args.question)
    print(answer.answer)
    if answer.sources:
        print("")
        print("Sources:")
        for source in answer.sources:
            print(f"- {source}")
    return 0


def cmd_rag_process(args: argparse.Namespace) -> int:
    store = RagStore()
    store.initialize()
    try:
        results = process_rag_documents(
            store=store,
            phone=args.phone,
            document_id=args.document_id,
            title=args.title,
            latest=args.latest,
            all_documents=args.all,
        )
    except RagProcessingError as exc:
        print(f"Could not process RAG document: {exc}")
        return 1

    for document, chunk_count in results:
        print(f"RAG document processed: ID {document['id']} | {document['title']} | chunks indexed: {chunk_count}")
    return 0


def cmd_rag_reindex(args: argparse.Namespace) -> int:
    from classroom_assistant.rag_assistant.vector_store import ChromaVectorStore, VectorStoreUnavailable

    store = RagStore()
    store.initialize()
    documents = store.all_documents()
    if not documents:
        print("No RAG documents to reindex.")
        return 0

    try:
        vector_store = ChromaVectorStore(store)
    except VectorStoreUnavailable as exc:
        print(f"Vector store unavailable: {exc}")
        return 1

    try:
        vector_store.reset()
        total_chunks = 0
        indexed = 0
        for document in documents:
            count = vector_store.index_document(int(document["id"]))
            total_chunks += count
            if count:
                indexed += 1
            print(f"Reindexed: ID {document['id']} | {document['title']} | chunks: {count}")
    finally:
        vector_store.close()

    print(f"\nVector index rebuilt: {indexed}/{len(documents)} document(s), {total_chunks} chunks.")
    return 0


def cmd_rag_delete(args: argparse.Namespace) -> int:
    store = RagStore()
    store.initialize()
    deleted = store.delete_document(args.document_id, args.phone)
    if not deleted:
        print("RAG document not found.")
        return 1
    print("RAG document deleted.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Classroom WhatsApp assistant.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create database tables.")
    init_db.set_defaults(func=cmd_init_db)

    add_teacher = subparsers.add_parser("add-teacher", help="Authorize a teacher phone number.")
    add_teacher.add_argument("--name", required=True)
    add_teacher.add_argument("--phone", required=True)
    add_teacher.add_argument("--google-email", default="")
    add_teacher.set_defaults(func=cmd_add_teacher)

    list_teachers = subparsers.add_parser("list-teachers", help="List authorized teachers.")
    list_teachers.set_defaults(func=cmd_list_teachers)

    remove_teacher = subparsers.add_parser("remove-teacher", help="Remove a teacher phone authorization.")
    remove_teacher.add_argument("--phone", required=True)
    remove_teacher.set_defaults(func=cmd_remove_teacher)

    check = subparsers.add_parser("check", help="Check whether a sender is authorized.")
    check.add_argument("--phone", required=True)
    check.add_argument("--channel", default="dm", choices=["dm", "group"])
    check.set_defaults(func=cmd_check)

    message = subparsers.add_parser("message", help="Simulate a WhatsApp message.")
    message.add_argument("--phone", required=True)
    message.add_argument("--text", required=True)
    message.add_argument("--channel", default="dm", choices=["dm", "group"])
    message.set_defaults(func=cmd_message)

    google_check = subparsers.add_parser("google-check", help="Validate Google OAuth credentials file.")
    google_check.set_defaults(func=cmd_google_check)

    google_login = subparsers.add_parser("google-login", help="Connect a teacher Google account.")
    google_login.add_argument("--phone", required=True)
    google_login.set_defaults(func=cmd_google_login)

    google_status = subparsers.add_parser("google-status", help="Show teacher Google connection status.")
    google_status.add_argument("--phone", required=True)
    google_status.set_defaults(func=cmd_google_status)

    security_key = subparsers.add_parser("security-key", help="Generate a Fernet key for token encryption.")
    security_key.set_defaults(func=cmd_security_key)

    encrypt_token = subparsers.add_parser("encrypt-token", help="Encrypt an existing Google token file.")
    encrypt_token.add_argument("--phone", required=True)
    encrypt_token.set_defaults(func=cmd_encrypt_token)

    courses = subparsers.add_parser("courses", help="List Google Classroom courses for a teacher.")
    courses.add_argument("--phone", required=True)
    courses.set_defaults(func=cmd_courses)

    select_course = subparsers.add_parser("select-course", help="Select a Google Classroom course.")
    select_course.add_argument("--phone", required=True)
    select_course.add_argument("selector", help="Course number or course name.")
    select_course.set_defaults(func=cmd_select_course)

    selected_course = subparsers.add_parser("selected-course", help="Show selected Google Classroom course.")
    selected_course.add_argument("--phone", required=True)
    selected_course.set_defaults(func=cmd_selected_course)

    parse = subparsers.add_parser("parse", help="Parse a Classroom command and show preview.")
    parse.add_argument("text")
    parse.set_defaults(func=cmd_parse)

    create_assignment = subparsers.add_parser("create-assignment", help="Create assignment in selected course.")
    create_assignment.add_argument("--phone", required=True)
    create_assignment.add_argument("--title", required=True)
    create_assignment.add_argument("--deadline", required=True)
    create_assignment.add_argument("--marks", type=int)
    create_assignment.add_argument("--description", default="")
    create_assignment.add_argument("--draft", action="store_true")
    create_assignment.set_defaults(func=cmd_create_assignment)

    receive_file = subparsers.add_parser("receive-file", help="Stage a received WhatsApp file.")
    receive_file.add_argument("--phone", required=True)
    receive_file.add_argument("--path", required=True)
    receive_file.add_argument("--name")
    receive_file.set_defaults(func=cmd_receive_file)

    latest_file = subparsers.add_parser("latest-file", help="Show latest staged teacher file.")
    latest_file.add_argument("--phone", required=True)
    latest_file.set_defaults(func=cmd_latest_file)

    upload_latest_file = subparsers.add_parser("upload-latest-file", help="Upload latest staged file to Google Drive.")
    upload_latest_file.add_argument("--phone", required=True)
    upload_latest_file.add_argument("--course-folder", default="")
    upload_latest_file.set_defaults(func=cmd_upload_latest_file)

    upload_folder_to_drive = subparsers.add_parser(
        "upload-folder-to-drive",
        help="Upload supported files from a local folder tree to Google Drive folders.",
    )
    upload_folder_to_drive.add_argument("--phone", required=True)
    upload_folder_to_drive.add_argument(
        "--source",
        default=r"C:\Users\SiddiqShah\Documents\University_6th_Sem",
    )
    upload_folder_to_drive.add_argument("--drive-folder", default="University_6th_Sem")
    upload_folder_to_drive.add_argument("--limit", type=int, default=0)
    upload_folder_to_drive.add_argument("--dry-run", action="store_true")
    upload_folder_to_drive.add_argument("--execute", action="store_true")
    upload_folder_to_drive.set_defaults(func=cmd_upload_folder_to_drive)

    latest_drive_file = subparsers.add_parser("latest-drive-file", help="Show latest uploaded Drive file.")
    latest_drive_file.add_argument("--phone", required=True)
    latest_drive_file.set_defaults(func=cmd_latest_drive_file)

    find_drive_file = subparsers.add_parser("find-drive-file", help="Search Google Drive for a supported file.")
    find_drive_file.add_argument("--phone", required=True)
    find_drive_file.add_argument("--folder", default="")
    find_drive_file.add_argument("query")
    find_drive_file.set_defaults(func=cmd_find_drive_file)

    list_drive_folder = subparsers.add_parser("list-drive-folder", help="List supported files in a Google Drive folder.")
    list_drive_folder.add_argument("--phone", required=True)
    list_drive_folder.add_argument("--folder", required=True)
    list_drive_folder.add_argument("--limit", type=int, default=20)
    list_drive_folder.set_defaults(func=cmd_list_drive_folder)

    list_drive_folders = subparsers.add_parser("list-drive-folders", help="List Google Drive folders.")
    list_drive_folders.add_argument("--phone", required=True)
    list_drive_folders.add_argument("--limit", type=int, default=100)
    list_drive_folders.set_defaults(func=cmd_list_drive_folders)

    history = subparsers.add_parser("history", help="Show recent Classroom activity.")
    history.add_argument("--phone", required=True)
    history.set_defaults(func=cmd_history)

    submission_report = subparsers.add_parser("submission-report", help="Show latest assignment submission report.")
    submission_report.add_argument("--phone", required=True)
    submission_report.set_defaults(func=cmd_submission_report)

    deadline_reminders = subparsers.add_parser("deadline-reminders", help="Show upcoming assignment deadlines.")
    deadline_reminders.add_argument("--phone", required=True)
    deadline_reminders.add_argument("--days", type=int, default=7)
    deadline_reminders.set_defaults(func=cmd_deadline_reminders)

    due_today = subparsers.add_parser("due-today", help="Show assignments due today.")
    due_today.add_argument("--phone", required=True)
    due_today.set_defaults(func=cmd_due_today)

    reminder_job = subparsers.add_parser("reminder-job", help="Run scheduled reminder output for all teachers.")
    reminder_job.add_argument("--days", type=int, default=7)
    reminder_job.add_argument("--send", action="store_true", help="Send reminders via webhook or queue outbox.")
    reminder_job.set_defaults(func=cmd_reminder_job)

    whatsapp_outbox = subparsers.add_parser("whatsapp-outbox", help="Show queued outbound WhatsApp messages.")
    whatsapp_outbox.add_argument("--limit", type=int, default=20)
    whatsapp_outbox.set_defaults(func=cmd_whatsapp_outbox)

    dashboard = subparsers.add_parser("dashboard", help="Run local dashboard UI.")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=cmd_dashboard)

    debug_logs = subparsers.add_parser("debug-logs", help="Show recent assistant error logs.")
    debug_logs.add_argument("--limit", type=int, default=10)
    debug_logs.set_defaults(func=cmd_debug_logs)

    find_file = subparsers.add_parser("find-file", help="Search allowed local folder for a supported file.")
    find_file.add_argument("query")
    find_file.add_argument("--limit", type=int, default=5)
    find_file.set_defaults(func=cmd_find_file)

    rag_init = subparsers.add_parser("rag-init", help="Create RAG database tables.")
    rag_init.set_defaults(func=cmd_rag_init)

    rag_upload = subparsers.add_parser("rag-upload", help="Upload a document into the local RAG store.")
    rag_upload.add_argument("--phone", required=True)
    rag_upload.add_argument("--path", required=True)
    rag_upload.add_argument("--category", default="")
    rag_upload.add_argument("--title", default="")
    rag_upload.set_defaults(func=cmd_rag_upload)

    rag_upload_folder = subparsers.add_parser("rag-upload-folder", help="Upload a folder of documents into RAG.")
    rag_upload_folder.add_argument("--phone", required=True)
    rag_upload_folder.add_argument("--path", required=True)
    rag_upload_folder.add_argument("--category", default="")
    rag_upload_folder.add_argument("--limit", type=int, default=0)
    rag_upload_folder.add_argument("--process", action="store_true")
    rag_upload_folder.add_argument("--reupload", action="store_true")
    rag_upload_folder.add_argument("--keep-subfolders", action="store_true")
    rag_upload_folder.set_defaults(func=cmd_rag_upload_folder)

    rag_documents = subparsers.add_parser("rag-documents", help="List uploaded RAG documents.")
    rag_documents.add_argument("--phone", required=True)
    rag_documents.set_defaults(func=cmd_rag_documents)

    rag_process = subparsers.add_parser("rag-process", help="Extract text and index chunks for a RAG document.")
    rag_process.add_argument("--phone", required=True)
    rag_process.add_argument("--document-id", type=int)
    rag_process.add_argument("--title", default="")
    rag_process.add_argument("--latest", action="store_true")
    rag_process.add_argument("--all", action="store_true")
    rag_process.set_defaults(func=cmd_rag_process)

    rag_reindex = subparsers.add_parser("rag-reindex", help="Rebuild the vector index from current chunks (fixes stale/orphaned embeddings).")
    rag_reindex.set_defaults(func=cmd_rag_reindex)

    rag_delete = subparsers.add_parser("rag-delete", help="Delete a RAG document and its chunks.")
    rag_delete.add_argument("--phone", required=True)
    rag_delete.add_argument("--document-id", type=int, required=True)
    rag_delete.set_defaults(func=cmd_rag_delete)

    rag_ask = subparsers.add_parser("rag-ask", help="Ask a placeholder RAG question.")
    rag_ask.add_argument("--phone", required=True)
    rag_ask.add_argument("question")
    rag_ask.set_defaults(func=cmd_rag_ask)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
