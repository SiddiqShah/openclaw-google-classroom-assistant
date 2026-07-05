# Milestone 6: WhatsApp File Receiving

## Goal

Teacher can send a PDF/PPTX/DOCX file to the assistant, and the backend validates and stages it for later Google Drive upload.

## Implemented

- validates supported file types:
  - `.pdf`
  - `.pptx`
  - `.docx`
- rejects empty files
- rejects files larger than 25 MB
- copies valid files into `data/staged_files/`
- stores file metadata in SQLite
- tracks the latest staged file per teacher
- returns a WhatsApp-style next-step prompt

## Manual Test

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe assistant_cli.py receive-file --phone "+923018083053" --path "C:\path\to\worksheet.pdf"
.\.venv\Scripts\python.exe assistant_cli.py latest-file --phone "+923018083053"
```

WhatsApp-style simulator:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py message --phone "+923018083053" --text "receive file C:\path\to\worksheet.pdf"
```

Expected response:

```text
File received: worksheet.pdf

What do you want to do with this file?

1. Attach to Assignment
2. Upload as Study Material
3. Cancel
```

## Notes

Actual WhatsApp media download is handled by OpenClaw/WhatsApp. This milestone handles the backend side once OpenClaw provides a local file path.

## Next Milestone

Google Drive upload system.
