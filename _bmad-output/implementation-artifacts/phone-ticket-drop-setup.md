# Phone → unclassified ticket drop (Epic 8)

Setup for Simon — 2026-07-20

## What you do on the phone

1. Photograph your Delay Repay ticket (jpg/png).
2. Email it **to yourself** (same Gmail used for `--gmail-auth`).
3. Subject must start with **`TICKET`**  
   Example: `TICKET GOD return 16 Jul`
4. Attach the photo. Send.

No special app required. Works on Android or iPhone Mail / Gmail.

## One-time PC setup

```powershell
cd C:\Users\simon\IdeaProjects\lateTrainQueries

# Re-auth once (Story 8.1 added gmail.modify scope)
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
python -m trainline --gmail-auth

# Daily drain at 09:00 (before CatchUp / well before Friday 18:00 weekly ops)
powershell -ExecutionPolicy Bypass -File .\scripts\register-ticket-ingest-task.ps1 -At 09:00
```

Friday `--weekly-ops` **also** runs ingest first, so a photo emailed Thursday evening is picked up by Friday’s job even if the daily task was missed.

## Verify

```powershell
# After sending a TICKET email from your phone:
python -m trainline --ingest-ticket-mail
dir tickets\unclassified

# Optional folder path (Syncthing / OneDrive → tickets\inbox):
python -m trainline --ingest-ticket-folder
```

Ingested mails get Gmail label `trainline-ticket-ingested` so they are not downloaded twice. Content-hash dedup also blocks identical bytes.

## Cadence (locked)

| When | Action |
| --- | --- |
| Daily ~09:00 | `--ingest-ticket-mail` |
| Friday weekly-ops | ingest → assess → classify → file → email |

## Optional: Syncthing / OneDrive

Point the sync folder at `tickets\inbox\` (not directly at `unclassified`). Then run `--ingest-ticket-folder` or add it to a schedule. Non-images are parked under `tickets\inbox\processed\`.

## Unregister daily ingest

```powershell
.\scripts\register-ticket-ingest-task.ps1 -Unregister
```
