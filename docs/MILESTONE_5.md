# Milestone 5: Assignment Creation Without File

## Goal

Teacher can create a Google Classroom assignment without attachments after preview and approval.

## Implemented

- pending approval storage
- teacher reply handling:
  - `1` = publish
  - `2` = save as draft
  - `3` = cancel
- Google Classroom `CourseWork` creation
- deadline parsing into Classroom `dueDate` and `dueTime`
- assignment records saved locally

## Required OAuth Scope

Google Classroom assignment creation requires:

```text
https://www.googleapis.com/auth/classroom.coursework.students
```

Re-run Google login after this milestone so the token includes the new scope:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py google-login --phone "+923018083053"
```

## Manual Test

First select a class:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py select-course --phone "+923018083053" 2
```

Preview:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "SE Software Requirement Engineering mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
```

Save as draft:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "2"
```

Publish:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "1"
```

Cancel:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "3"
```

## Safety

The assistant still never posts directly from the first message. It stores a pending action and waits for teacher approval.
