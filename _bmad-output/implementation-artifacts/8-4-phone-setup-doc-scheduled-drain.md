---
story_key: 8-4-phone-setup-doc-scheduled-drain
epic: 8
status: review
created: 2026-07-20
depends_on: [8-1]
---

# Story 8.4: Phone setup doc + scheduled drain

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As Simon,
I want a one-page phone setup and a scheduled ingest,
So that Thursday photos are waiting before Friday weekly ops.

## Acceptance Criteria

1. **Phone setup doc (FR41, NFR15).** One-page markdown under `_bmad-output/` or `docs/` explaining Android/iPhone: email photo to self with subject starting **`TICKET`**, optional Gmail label, confirm arrives after daily drain.
2. **Daily Task Scheduler job (NFR14).** Register a once-daily task (e.g. morning) that runs `python -m trainline --ingest-ticket-mail` — **not** a 15-minute poller. Cadence locked 2026-07-20: once daily + pre-Friday weekly-ops hook (hook is Story 8.1).
3. **Register script.** Extend `scripts/register-weekly-ops-task.ps1` or add `scripts/register-ticket-ingest-task.ps1` creating e.g. `LateTrainQueries-TicketIngest-Daily` at a configurable `-At` (default align with CatchUp **09:30** or earlier).
4. **Idempotent with weekly-ops.** Running daily ingest then Friday `--weekly-ops` (which ingests again) must not duplicate files (8.1 labels + 8.2 hashes).
5. **Doc includes re-auth** note if `gmail.modify` was added in 8.1 (`--gmail-auth` once).

## Tasks / Subtasks

- [x] Write setup doc (AC: #1, #5) — e.g. `_bmad-output/implementation-artifacts/phone-ticket-drop-setup.md`
  - [x] Subject `TICKET …`; attach jpg/png; PC must be on for daily task; Friday auto-ingests before assess
  - [x] Optional: point Syncthing/OneDrive at `tickets/inbox/` if 8.3 shipped
- [x] PowerShell register/unregister for daily ingest (AC: #2–#3)
  - [x] Reuse patterns from `scripts/register-weekly-ops-task.ps1` / `weekly_ops.ps1` (env HSP + CA bundle)
- [x] Update Epic 8 / manual checklist with register commands (AC: #1)
- [x] Smoke: dry-run register script syntax; offline test not required for schtasks (manual verify)

## Dev Notes

### Locked cadence (2026-07-20)

| When | What |
| --- | --- |
| Daily (e.g. 09:30) | `--ingest-ticket-mail` |
| Friday weekly-ops | ingest → assess → classify → file → email |

No continuous / 15-minute polling.

### Depends on

- **8.1** required (`--ingest-ticket-mail` + weekly hook).
- **8.2** strongly preferred before calling Epic 8 done (dedup under double drain).
- **8.3** optional mention in the setup doc.

### Anti-patterns

- Do not create ONLOGON ingest requiring Admin unless documented as optional `-PreferLogon`.
- Do not put secrets in the markdown doc.
- Do not change Friday 18:00 weekly task semantics beyond ensuring 8.1 ingest-first already landed.

### References

- Epics Story 8.4; FR41; NFR14–NFR15
- `scripts/weekly_ops.ps1`, `scripts/register-weekly-ops-task.ps1`
- `epic-7-closeout-2026-07-20.md` (scheduler precedent)
- Story 8.1

## Dev Agent Record

### Completion Notes List

### File List
