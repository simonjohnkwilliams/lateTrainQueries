# Manual validation — Epic 8 phone ticket drop (2026-07-20)

Run after the automated gate is green. Offline suite should already pass.

## A. Automated (agent already ran)

```powershell
python -m pytest -q
```

Expect all green (Epic 8 unit tests included).

## B. One-time setup (you)

1. **Re-auth Gmail** (new `gmail.modify` scope):
   ```powershell
   cd C:\Users\simon\IdeaProjects\lateTrainQueries
   $env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
   python -m trainline --gmail-auth
   ```
   Complete the browser consent for readonly + send + **modify**.

2. **Confirm daily ingest task** (registered at **09:00** if the agent ran the script):
   ```powershell
   Get-ScheduledTask -TaskName 'LateTrainQueries-TicketIngest-Daily','LateTrainQueries-WeeklyOps-*' |
     Format-Table TaskName, State
   ```
   Change time: `.\scripts\register-ticket-ingest-task.ps1 -At 08:30`

## C. Phone → Gmail → unclassified (core sign-off)

1. On your phone: email **yourself** a ticket photo.
2. Subject must start with **`TICKET`** (e.g. `TICKET test Thursday`).
3. On the PC:
   ```powershell
   python -m trainline --ingest-ticket-mail
   dir tickets\unclassified
   ```
4. Confirm the jpg/png is in `tickets\unclassified\`.
5. Run ingest again — same mail must **not** create a second file (label + hash dedup).
6. In Gmail, confirm label **`trainline-ticket-ingested`** on that message.

## D. Friday chain (with ingest first)

```powershell
# When ready (Ollama up; FakeBrowser OK):
python -m trainline --weekly-ops
# or: Start-ScheduledTask -TaskName 'LateTrainQueries-WeeklyOps-Friday'
python -m trainline --weekly-status   # complete=true after success
```

Stderr order should include ticket-mail ingest before HSP assess.

## E. Optional folder path (8.3)

```powershell
# Drop a jpg into tickets\inbox\ (or Syncthing that folder), then:
python -m trainline --ingest-ticket-folder
dir tickets\unclassified
```

## F. Doc

Phone steps also live in:  
`_bmad-output/implementation-artifacts/phone-ticket-drop-setup.md`

## Pass criteria for Epic 8

- [ ] `--gmail-auth` with modify scope done
- [ ] One real phone `TICKET` email lands in `unclassified` via `--ingest-ticket-mail`
- [ ] Second ingest is a no-op for that mail
- [ ] Daily task visible in Task Scheduler
- [ ] (Optional) Friday weekly-ops run with ingest-first confirmed
