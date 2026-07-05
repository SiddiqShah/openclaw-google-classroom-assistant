# Milestone 1: WhatsApp Bot Setup + Teacher Access Control

## Goal

Secure the assistant so only approved teacher WhatsApp numbers can use the Classroom automation.

## Implemented

- SQLite-backed teacher allowlist
- WhatsApp phone normalization
- unknown-number block message
- group/private channel guard
- one teacher phone mapped to one Google email field
- bot greeting and menu simulation
- access attempt logs
- unit tests for allowed, blocked, and group-message cases

## Manual Test

```powershell
python projects\google-classroom-assistant\assistant_cli.py init-db
python projects\google-classroom-assistant\assistant_cli.py add-teacher --name "Mr. Ali" --phone "+923001234567" --google-email "mr.ali@example.com"
python projects\google-classroom-assistant\assistant_cli.py message --phone "+923001234567" --text "Hi"
python projects\google-classroom-assistant\assistant_cli.py message --phone "+923009999999" --text "Hi"
python projects\google-classroom-assistant\assistant_cli.py message --phone "+923001234567" --text "Hi" --channel group
```

## Done Criteria

- allowed teacher receives welcome/menu reply
- unknown sender receives unauthorized reply
- group message does not run classroom actions
- access logs are saved

## Next Milestone

Google OAuth login for teachers.
