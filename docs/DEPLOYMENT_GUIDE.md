# Deployment Guide

This guide turns the local MVP into a production-style setup.

## 1. Production Checklist

- Use a dedicated Google Cloud project.
- Keep `secrets/google_oauth_client.json` private.
- Re-run Google login for each teacher account.
- Use HTTPS/reverse proxy if exposing a dashboard later.
- Back up `data/classroom_assistant.sqlite`.
- Back up `data/rag` if using document Q&A.
- Restart OpenClaw after config or skill changes.
- Keep WhatsApp sender allowlist restricted to trusted teacher numbers.

## 2. Required Google APIs

Enable these APIs in Google Cloud:

- Google Classroom API
- Google Drive API

OAuth scopes used by the assistant:

- `classroom.courses.readonly`
- `classroom.coursework.students`
- `classroom.courseworkmaterials`
- `classroom.announcements`
- `classroom.rosters.readonly`
- `drive.file`
- `drive.readonly`

## 3. Environment Paths

Project folder:

```text
C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
```

Main CLI:

```text
C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant\assistant_cli.py
```

Database:

```text
C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant\data\classroom_assistant.sqlite
```

## 4. Scheduled Reminder Job

The reminder job prints due-today and upcoming-deadline reminders for all configured teachers:

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe assistant_cli.py reminder-job
```

To send through a webhook or queue the message in the local outbox:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py reminder-job --send
.\.venv\Scripts\python.exe assistant_cli.py whatsapp-outbox
```

Set this environment variable when you have an outbound WhatsApp bridge:

```powershell
$env:OPENCLAW_WHATSAPP_SEND_WEBHOOK="http://127.0.0.1:3000/send-whatsapp"
```

If the webhook is missing or fails, messages are saved to:

```text
data\outbox\whatsapp_outbox.jsonl
```

Wrapper script:

```powershell
.\scripts\run_reminder_job.ps1
```

### Windows Task Scheduler

Create a daily scheduled task using the wrapper script:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant\scripts\run_reminder_job.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
Register-ScheduledTask -TaskName "Google Classroom Assistant Reminders" -Action $action -Trigger $trigger -Description "Runs classroom deadline reminders daily."
```

Use `--send` in the scheduled task when the outbound WhatsApp webhook is ready.

## 5. Debug Commands

Show recent assistant errors:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py debug-logs
```

Show recent Classroom activity:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py history --phone "+923018083053"
```

Show Google auth scopes:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py google-status --phone "+923018083053"
```

## 6. Security Notes

- Store OAuth tokens encrypted before production use.
- Restrict WhatsApp `allowFrom` to real teacher phone numbers.
- Never auto-publish without preview approval.
- Keep action and error logs.
- Give teachers a revoke-access process.

Generate an encryption key:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py security-key
```

Set it before Google login or token refresh:

```powershell
$env:CLASSROOM_ASSISTANT_TOKEN_KEY="paste-generated-key-here"
.\.venv\Scripts\python.exe assistant_cli.py google-login --phone "+923018083053"
```

Encrypt an existing token after setting the key:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py encrypt-token --phone "+923018083053"
```

## 7. Dashboard

Run the local dashboard:

```powershell
.\.venv\Scripts\python.exe assistant_cli.py dashboard
```

Open:

```text
http://127.0.0.1:8765
```

It shows courses, recent Classroom posts, RAG documents, errors, and the WhatsApp outbox.
