# Milestone 2: Google OAuth Login for Teachers

## Goal

Connect an authorized teacher WhatsApp number to a Google account so the backend can access Google Classroom and Google Drive.

## Implemented

- validates `secrets/google_oauth_client.json`
- detects wrong `web` OAuth client type
- supports Desktop OAuth login flow
- saves teacher token JSON under `secrets/tokens/`
- tracks token metadata in SQLite
- adds `google-check`, `google-login`, and `google-status` CLI commands
- adds `courses` CLI command as the Classroom permission test

## Setup

Install dependencies inside the project virtual environment:

```powershell
cd C:\Users\SiddiqShah\.openclaw\projects\google-classroom-assistant
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Check credentials:

```powershell
python assistant_cli.py google-check
```

Connect Mr.Siddiq's Google account:

```powershell
python assistant_cli.py google-login --phone "+923018083053"
```

Check connection:

```powershell
python assistant_cli.py google-status --phone "+923018083053"
```

Permission test:

```powershell
python assistant_cli.py courses --phone "+923018083053"
```

## Current OAuth Scopes

- `https://www.googleapis.com/auth/classroom.courses.readonly`
- `https://www.googleapis.com/auth/drive.file`

These scopes are enough for the next milestone: course listing, plus future Drive uploads for files created/uploaded by the app.

Milestone 3 continues this course listing work by caching courses and allowing class selection.

## Security Notes

- The OAuth client JSON and token files are ignored by `.gitignore`.
- Token encryption is not implemented yet; this is acceptable for local learning, but production must encrypt tokens.
- Never paste credentials or token file contents into chat, GitHub, or a client demo.
