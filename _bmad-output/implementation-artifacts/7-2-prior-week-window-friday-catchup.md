---
story_key: 7-2-prior-week-window-friday-catchup
epic: 7
status: ready-for-dev
created: 2026-07-20
depends_on: 7-1
---

# Story 7.2: Prior-week window + Friday catch-up scheduler

Status: ready-for-dev

## Story

As Simon,
I want the job to target Mon–Fri of the week before the anchor Friday,
So that Friday (or later power-on) never analyses the incomplete current week.

## Acceptance Criteria

1. **Anchor Friday window.** `as_of = Fri 17 Jul 2026` → assess range Mon 6 Jul – Fri 10 Jul (FR33).
2. **Missed Friday catch-up.** `as_of = Mon 20 Jul 2026` → same Mon 6 Jul – Fri 10 Jul (NFR13).
3. **Task Scheduler / power-on.** Windows PowerShell script runs the weekly command once for that anchor Friday if not already completed (FR32, FR39). Idempotent marker on disk.

## Tasks

- [ ] Pure function `prior_week_window(as_of: date) -> tuple[date, date]` (Mon–Fri inclusive) in `engine` or a tiny pure helper module under adapters with no I/O — prefer **engine** if date-only pure; else `adapters/schedule.py` pure functions only.
- [ ] Offline parametrised tests for Fri / Sat–Thu catch-up cases (table of as_of → window).
- [ ] PowerShell script under `scripts/` for Task Scheduler + optional “run on logon if Friday’s marker missing”.
- [ ] Completion marker path (e.g. under `Results/` or `creds/`-adjacent state dir) keyed by anchor Friday ISO date — do not duplicate runs (FR39). Full weekly chain wiring is Story 7.3; this story can stub “invoke weekly entrypoint” or write marker after dry invoke.

## Dev Notes

- Partial weeks are **not** special-cased — always five weekdays (FR33).
- Do not call HSP or Gmail here beyond optional CLI flag that only prints the window.
- AD-8: scheduler script calls `python -m trainline …`; logic stays out of engine I/O.

## Automated tests (pre-written)

| Layer | File | Notes |
| --- | --- | --- |
| Window (AC1–AC2) | `tests/test_schedule_window.py` | **Live now** — `prior_working_week` |
| Completion marker (AC3) | `tests/test_weekly_marker.py` | Skip until `adapters/weekly_marker.py` |
| Task Scheduler | MANUAL C1 in `manual-validation-checklist-epic-7.md` | Cannot fully automate |

### References

- Epics Story 7.2; FR32–FR33, FR39, NFR12–NFR13
- Architecture AD-8 composition root
- Sign-off: `_bmad-output/implementation-artifacts/manual-validation-checklist-epic-7.md`