# Milestone 3: Course Sync and Class Selection

## Goal

Teacher can list Google Classroom classes and select the class the assistant should use for the next action.

## Implemented

- syncs active Google Classroom courses
- caches courses in SQLite
- selects class by list number
- selects class by partial class name
- stores selected course per teacher
- supports WhatsApp-style message simulation:
  - `Meri classes dikhao`
  - `Class 2 select karo`
  - `selected class`

## Manual Test

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe assistant_cli.py courses --phone "+923018083053"
.\.venv\Scripts\python.exe assistant_cli.py select-course --phone "+923018083053" 2
.\.venv\Scripts\python.exe assistant_cli.py selected-course --phone "+923018083053"
```

WhatsApp-style simulator:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "Meri classes dikhao"
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "Class 2 select karo"
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "selected class"
```

## Done Criteria

- course list shows real Google Classroom courses
- selecting by number stores the correct course ID
- selected class can be retrieved later

## Next Milestone

WhatsApp command parser for assignment/material/announcement intent detection.
