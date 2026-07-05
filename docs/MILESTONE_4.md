# Milestone 4: WhatsApp Command Parser

## Goal

Teacher can send normal language messages and the system extracts the Classroom action details before any Google Classroom post happens.

## Implemented

- detects assignment, study material, and announcement intents
- extracts course, title/message, deadline, marks, and instructions where available
- detects missing required fields
- renders confirmation preview
- supports CLI parser command
- supports WhatsApp-style simulator previews

## Manual Test

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe assistant_cli.py parse "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "SE Databases mein Python Loops assignment banao. Deadline 15 July 2026 6 PM. Marks 25."
```

Example preview:

```text
Please confirm:

Course: SE Databases
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

## Notes

This parser is deterministic and local. Later, an AI parser can improve phrasing coverage, but this gives us a safe baseline with predictable tests.

## Next Milestone

Assignment creation without file. Implemented in `MILESTONE_5.md`.
