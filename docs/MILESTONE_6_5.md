# Milestone 6.5: Local File Search

## Goal

Teacher can mention a file by name, and the assistant searches the allowed local folder instead of requiring a full path.

## Allowed Search Folder

```text
C:\Users\SiddiqShah\Documents\University_6th_Sem
```

## Implemented

- searches only the allowed university folder
- supports `.pdf`, `.pptx`, `.docx`
- matches partial file names
- rejects ambiguous matches
- stages matched file for later Drive upload
- includes found file in assignment/material preview

## WhatsApp Test

Send:

```text
SE Software Requirement Engineering mein assignment banao:
Title: Requirement Specification Task
Deadline: 15 July 2026 6 PM
Marks: 25
Attach: Task Req def and specification
```

Expected preview:

```text
Please confirm:

Course: SE Software Requirement Engineering
Type: Assignment
Title: Requirement Specification Task
Instructions: Not set
Deadline: 15 July 2026 6 PM
Marks: 25
Files: Task Req def and specification.pdf

Reply:
1 = Publish
2 = Save as draft
3 = Cancel
```

## Local CLI Test

```powershell
.\.venv\Scripts\python.exe assistant_cli.py find-file "Task Req def and specification"
```

## Next

Milestone 7 uploads the staged file to Google Drive. Milestone 8 attaches the Drive file to a Classroom assignment.
