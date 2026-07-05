# WhatsApp Bot Test Guide

This guide tests the Google Classroom Assistant from WhatsApp/OpenClaw.

## Before Testing

Restart OpenClaw after code changes so the WhatsApp bot reloads the Classroom-only skill.

Run this once from the project folder if Google asks for new permissions:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py google-login --phone "+923018083053"
```

Approve all requested Google Classroom and Drive permissions. This is required for:

- Assignments
- Study materials
- Announcements
- Drive file uploads
- Submission reports

Check the token:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py google-status --phone "+923018083053"
```

Optional token encryption before production:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py security-key
$env:CLASSROOM_ASSISTANT_TOKEN_KEY="paste-generated-key-here"
.\.venv\Scripts\python.exe assistant_cli.py encrypt-token --phone "+923018083053"
```

The scopes should include:

- `https://www.googleapis.com/auth/classroom.courses.readonly`
- `https://www.googleapis.com/auth/classroom.coursework.students`
- `https://www.googleapis.com/auth/classroom.courseworkmaterials`
- `https://www.googleapis.com/auth/classroom.announcements`
- `https://www.googleapis.com/auth/classroom.rosters.readonly`
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/drive.readonly`

## Test 1: List Classes

Send:

```text
Show classes
```

Expected response:

```text
Your Google Classroom classes:

1. SE Operating System (A)
2. SE Software Requirement Engineering (A)
3. SE Databases (A)

Reply with class number or class name.
```

Then send:

```text
2
```

Expected response:

```text
SE Software Requirement Engineering (A) selected.
Now you can create an assignment, upload material, or post an announcement.
```

## Test 2: Assignment Without File

Send:

```text
SE Software Requirement Engineering mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25.
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Assignment
Title: Python Loops
Instructions: Not set
Deadline: 15 July 2026 6 PM
Marks: 25
Files: No attachment

Reply:
1 = Publish
2 = Save as draft
3 = Cancel
```

Send `1` to publish, `2` to save as draft, or `3` to cancel.

## Test 3: Study Material / Lecture PDF

This searches inside:

```text
C:\Users\SiddiqShah\Documents\University_6th_Sem
```

Send:

```text
SE Software Requirement Engineering mein pdf upload karo:
Title: SRE INTRODUCTION
Attach: Task Req def and specification
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Study Material
Title: SRE INTRODUCTION
Description: Not set
Files: Task Req def and specification.pdf

Reply:
1 = Post
2 = Cancel
```

Send:

```text
1
```

Expected final response:

```text
Done. Study material posted in SE Software Requirement Engineering (A).
Title: SRE INTRODUCTION
File: Task Req def and specification.pdf
Link: ...
```

## Test 4: Assignment With Local File Attachment

Send:

```text
SE Software Requirement Engineering mein Requirement Task assignment banao. Deadline 20 July 2026 5 PM. Marks 20. Attach: Task Req def and specification
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Assignment
Title: Requirement Task
Instructions: Not set
Deadline: 20 July 2026 5 PM
Marks: 20
Files: Task Req def and specification.pdf

Reply:
1 = Publish
2 = Save as draft
3 = Cancel
```

Send `1` to publish.

## Test 5: Study Material From Existing Google Drive File

Use this when the file is already inside the teacher's Google Drive.

Send:

```text
SE Software Requirement Engineering mein material upload karo:
Title: SRE INTRODUCTION
Attach from Drive: Task Req def and specification
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Study Material
Title: SRE INTRODUCTION
Description: Not set
Files: Task Req def and specification.pdf (Google Drive)

Reply:
1 = Post
2 = Cancel
```

Send `1` to post.

## Test 6: Assignment With Existing Google Drive File

Send:

```text
SE Software Requirement Engineering mein Requirement Task assignment banao. Deadline 20 July 2026 5 PM. Marks 20. Attach from Drive: Task Req def and specification
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Assignment
Title: Requirement Task
Instructions: Not set
Deadline: 20 July 2026 5 PM
Marks: 20
Files: Task Req def and specification.pdf (Google Drive)

Reply:
1 = Publish
2 = Save as draft
3 = Cancel
```

## Test 7: Announcement

Send:

```text
SE Software Requirement Engineering mein announcement post karo: Tomorrow class is cancelled.
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Announcement
Message: Tomorrow class is cancelled

Reply:
1 = Post
2 = Cancel
```

Send `1` to post.

## Test 8: Multi-Class Posting

Use `and` or commas between class names.

Send:

```text
SE Databases and SE Software Requirement Engineering mein announcement post karo: Submit your project proposal today.
```

Expected preview:

```text
Please confirm:

Course: SE Databases, SE Software Requirement Engineering
Type: Announcement
Message: Submit your project proposal today

Reply:
1 = Post
2 = Cancel
```

Send `1` to post to both classes.

You can also use this style for assignments and materials:

```text
SE Databases and SE Software Requirement Engineering mein Requirement Task assignment banao. Deadline 20 July 2026 5 PM. Marks 20.
```

## Test 9: AI Draft Generation With Teacher Approval

Generate an assignment draft:

```text
Generate assignment for SE Software Requirement Engineering Topic: Use case diagram Deadline 20 July 2026 5 PM Marks 20
```

Generate a quiz draft:

```text
Generate quiz for SE Software Requirement Engineering Topic: Requirement elicitation Deadline 15 July 2026 5 PM Marks 10
```

Generate a rubric draft:

```text
Generate rubric for SE Software Requirement Engineering Topic: SRS document Marks 20
```

Expected response:

```text
Please review this AI-generated draft:

Course: SE Software Requirement Engineering
Type: Quiz
Topic: Requirement elicitation Quiz
Deadline: 15 July 2026 5 PM
Marks: 10
Draft:
...

Reply:
1 = Create in Classroom
2 = Save as draft
3 = Cancel
```

The teacher must approve before anything is posted.

## Test 10: Deadline Reminders

Reminder commands use assignments created through this assistant after the reminder milestone was added.

Send:

```text
upcoming deadlines
```

Expected response:

```text
Upcoming deadlines in the next 7 days:

- Requirement Task | SE Software Requirement Engineering | in 3 days at 20 Jul 2026, 05:00 PM
```

Send:

```text
due today
```

Expected response:

```text
Assignments due today:
...
```

If nothing is due:

```text
No assignments are due today.
```

## Test 11: Recent Activity

Send:

```text
history
```

Expected response:

```text
Recent Classroom activity:
...
```

## Test 12: Submission Report

Send:

```text
submission report
```

Expected response:

```text
Python Loops Submission Report

Course: SE Software Requirement Engineering
Submitted: ...
Missing or not turned in: ...
Late: ...

Missing students:
- Student Name 1
- Student Name 2

Late students:
- Student Name 3
```

The report uses the latest assignment created through this assistant. Student names require roster access during Google login.

## Test 13: Debug Logs

Send:

```text
debug logs
```

Expected response:

```text
Recent errors:
...
```

If there are no errors:

```text
No recent errors logged.
```

## Test 14: RAG Document Assistant

Show RAG menu:

```text
RAG menu
```

Ask from indexed documents:

```text
Ask docs: What is photosynthesis?
```

List documents:

```text
List documents
```

Reprocess a document:

```text
Reprocess document 1
```

Delete a document:

```text
Delete document 1
```

Generate Classroom MCQs from uploaded documents:

```text
Create 10 MCQs from docs for Class 9 Biology Topic: Photosynthesis Deadline Friday 5 PM Marks 10
```

Expected response is a normal Classroom assignment preview. Teacher must reply `1`, `2`, or `3`.

## Terminal Debug Commands

Simulate WhatsApp:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "Show classes"
```

Search local files:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py find-file "Task Req def and specification"
```

Show recent activity:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py history --phone "+923018083053"
```

Show latest submission report:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py submission-report --phone "+923018083053"
```

Show deadline reminders:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py deadline-reminders --phone "+923018083053"
```

Show today's deadlines:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py due-today --phone "+923018083053"
```

Run scheduled reminder job manually:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py reminder-job
.\.venv\Scripts\python.exe assistant_cli.py reminder-job --send
.\.venv\Scripts\python.exe assistant_cli.py whatsapp-outbox
```

Show debug logs:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py debug-logs
```

Search Google Drive:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py find-drive-file --phone "+923018083053" "Task Req def and specification"
```

RAG upload/process/ask:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py rag-upload --phone "+923018083053" --path "C:\path\to\chapter.pdf" --category "Class 9 Biology"
.\.venv\Scripts\python.exe assistant_cli.py rag-process --phone "+923018083053" --document-id 1
.\.venv\Scripts\python.exe assistant_cli.py rag-ask --phone "+923018083053" "What is this chapter about?"
.\.venv\Scripts\python.exe assistant_cli.py rag-delete --phone "+923018083053" --document-id 1
```

RAG uses ChromaDB vector retrieval after processing. PDF Q&A works for selectable-text PDFs; scanned/image-only PDFs need OCR, which is not part of this MVP.

Run dashboard:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py dashboard
```

Open:

```text
http://127.0.0.1:8765
```
