# Milestone 7: Google Drive Upload System

## Goal

Upload a staged PDF/PPTX/DOCX file to the teacher's Google Drive and store the Drive file ID for later Classroom attachment.

## Implemented

- creates/finds `Classroom Assistant` Drive folder
- creates/finds selected course subfolder when a class is selected
- uploads the latest staged file to Google Drive
- stores Drive file ID and web link in SQLite
- marks staged file as uploaded

## Manual Test

First stage or find a file:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "SE Software Requirement Engineering mein pdf upload karo: Title: SRE INTRODUCTION Attach: Task Req def and specification"
```

Then upload latest staged file:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py upload-latest-file --phone "+923018083053"
```

Check latest Drive upload:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py latest-drive-file --phone "+923018083053"
```

Expected:

```text
File uploaded successfully.
File: Task Req def and specification.pdf
Drive file ID: ...
Link: ...
```

## Sources

Google Drive API supports uploading file data when creating files, and client libraries support media upload flows:

https://developers.google.com/workspace/drive/api/guides/manage-uploads

Drive `files.create` creates files/folders and returns selected fields:

https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create

## Next

Milestone 8: attach the uploaded Drive file to a Google Classroom assignment/material.
