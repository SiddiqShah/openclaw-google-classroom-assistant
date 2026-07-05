# WhatsApp AI Assistant for Google Classroom

Learning project for building an OpenClaw-powered WhatsApp assistant that helps teachers manage Google Classroom.

## Current Status

The learning MVP now covers the full Classroom assistant flow:

- authorized WhatsApp teachers only
- Google OAuth + Classroom/Drive integration
- course sync and class selection
- assignment/material/announcement previews
- file upload from local disk or Google Drive
- multi-class posting
- deadline reminders and submission reports
- RAG document assistant with ChromaDB-backed vector search
- dashboard UI, debug logs, and outbound reminder outbox
- optional encrypted Google token storage

## Quick Start

From `C:\Users\SiddiqShah\.openclaw`:

```powershell
python projects\google-classroom-assistant\assistant_cli.py init-db
python projects\google-classroom-assistant\assistant_cli.py add-teacher --name "Mr. Siddiq" --phone "+923018083053" --google-email "bsse.233202025a@imsciences.edu.pk"
python projects\google-classroom-assistant\assistant_cli.py message --phone "+923018083053" --text "Hi"
python projects\google-classroom-assistant\assistant_cli.py message --phone "+923009999999" --text "Hi"
```

Run tests:

```powershell
python -m unittest discover -s projects\google-classroom-assistant\tests
```

## Google OAuth

Install Google dependencies:

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check the OAuth client file:

```powershell
python assistant_cli.py google-check
```

Connect the teacher Google account:

```powershell
python assistant_cli.py google-login --phone "+923018083053"
python assistant_cli.py google-status --phone "+923018083053"
python assistant_cli.py courses --phone "+923018083053"
python assistant_cli.py select-course --phone "+923018083053" 2
python assistant_cli.py selected-course --phone "+923018083053"
python assistant_cli.py parse "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
python assistant_cli.py message --phone "+923018083053" --text "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
python assistant_cli.py message --phone "+923018083053" --text "2"
python assistant_cli.py receive-file --phone "+923018083053" --path "C:\path\to\worksheet.pdf"
python assistant_cli.py find-file "Task Req def and specification"
python assistant_cli.py upload-latest-file --phone "+923018083053"
```

## Milestone Order

1. WhatsApp bot access control
2. Google OAuth login for teachers
3. Course sync and class selection
4. WhatsApp command parser
5. Assignment creation without file

See `docs\MILESTONE_1.md` for the current milestone details.

## RAG Extension

The project now includes a scaffold for:

```text
WhatsApp Classroom RAG + Assignment Assistant
```

RAG milestone docs:

```text
docs\RAG_MILESTONES.md
```

Initial CLI commands:

```powershell
python assistant_cli.py rag-init
python assistant_cli.py rag-upload --phone "+923018083053" --path "C:\path\to\chapter.txt" --category "Class 9 Biology"
python assistant_cli.py rag-documents --phone "+923018083053"
python assistant_cli.py rag-process --phone "+923018083053" --document-id 1
python assistant_cli.py rag-ask --phone "+923018083053" "What is this chapter about?"
```

Current RAG status:

- local document upload created
- TXT/DOCX extraction created
- PDF extraction added through `pypdf`
- chunking and chunk storage created
- SQLite metadata store created
- ChromaDB vector retrieval created with SQLite keyword fallback
- WhatsApp RAG commands created
- source references and PDF page numbers created
- document delete/reprocess controls created
- MCQ generation from docs can prepare a Classroom assignment preview

## Production Helpers

Run the local dashboard:

```powershell
python assistant_cli.py dashboard
```

Send or queue scheduled reminders:

```powershell
python assistant_cli.py reminder-job --send
python assistant_cli.py whatsapp-outbox
```

Generate a token encryption key:

```powershell
python assistant_cli.py security-key
```
