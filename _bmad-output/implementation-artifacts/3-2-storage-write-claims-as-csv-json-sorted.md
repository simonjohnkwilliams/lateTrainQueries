---
baseline_commit: 8e812f542cfdb286a321600d0e5fc890587c3370
---
# Story 3.2: Storage — write claims as CSV + JSON, sorted

Status: done

## Story

As Simon,
I want claim output I can eyeball and re-use,
so that I can verify each row against SWR before filing.

## Acceptance Criteria

1. **Every claim row carries the SWR-form fields.** Given a list of `Claim`s, when written, each row carries: journey date, origin→destination, scheduled departure, scheduled arrival, actual arrival, delay (min), band, and delay/cancellation reason. *(Epic 3 AC; FR13, AD-3)*
2. **Both CSV and JSON are produced, surfacing the band — not £.** Given a run's results, when stored, both a CSV file (human-checkable, one row per claim) and a JSON file (structured, for later phases) are produced; both surface the band/percentage, never a £/pence figure. *(Epic 3 AC; FR14, AD-11)*
3. **Output is sorted by date then direction.** Given multiple days and directions, when written, output is ordered by date ascending, then direction (outbound before inbound) so a week reads at a glance. *(Epic 3 AC; FR15)*

## Tasks / Subtasks

- [x] **Task 1 — Define the SWR-form field order and `Claim` → row mapping (AC: 1)**
- [x] **Task 2 — Format origin-day-relative minutes back to human HH:MM (AC: 1)**
- [x] **Task 3 — Write CSV (AC: 1, 2)**
- [x] **Task 4 — Write JSON (AC: 2)**
- [x] **Task 5 — Sort output by date then direction (AC: 3)**
- [x] **Task 6 — Tests (AC: 1, 2, 3)**

## Dev Agent Record

### Agent Model Used

Composer (Amelia / bmad-dev-story)

### Completion Notes List

- Implemented `write_claims` / `claim_to_row` / `sort_claims` in `adapters/storage.py`.
- Band surfaced as range labels (`15-29`, …); no `engine.delay` import (AD-2); no £.
- Times rendered with `% 1440` HH:MM; `None` actual → empty string.
- Offline tests cover FR13 fields, cross-midnight, band-not-£, sort, CSV↔JSON agreement.

### File List

- trainline/adapters/storage.py
- tests/test_storage.py

### Change Log

- 2026-07-15: Story 3.2 implemented and marked done.
