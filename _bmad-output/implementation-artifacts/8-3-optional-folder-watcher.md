---
story_key: 8-3-optional-folder-watcher
epic: 8
status: review
created: 2026-07-20
depends_on: [8-1, 8-2]
optional: true
---

# Story 8.3: Optional filesystem watcher (Syncthing / OneDrive)

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As Simon,
I want a watched inbox folder as an alternate to email,
So that Syncthing or OneDrive can feed the same pipeline.

## Acceptance Criteria

1. **Inbox path.** Default `tickets/inbox/` (configurable). New image files there are ingested into `tickets/unclassified/` (FR41).
2. **CLI.** `python -m trainline --ingest-ticket-folder` (batch drain, not a long-running daemon in MVP) moves/copies eligible images with **8.2 dedup** (FR42–FR43).
3. **Safe move.** After successful write to unclassified (or skip-as-dup), remove or archive from inbox so Syncthing does not re-deliver forever. Prefer move to `tickets/inbox/processed/` or delete after hash recorded.
4. **Non-images skipped** with log; exit 0 (FR44).
5. **Offline tests.** Temp inbox with jpg + txt → only jpg in unclassified; second run no duplicate.
6. **Optional epic path.** Gmail (8.1) remains primary. This story is **optional** for project completion if Simon only uses email drop — still ship if low cost after 8.2.

## Tasks / Subtasks

- [x] Add `--ingest-ticket-folder` + `_run_ingest_ticket_folder` in CLI (AD-8) (AC: #1–#2)
- [x] Reuse 8.2 `ticket_drop` helpers — no Gmail imports (AC: #2, #5)
- [x] Ensure `tickets/inbox/` (+ optional `processed/`) via layout extension or mkdir in CLI (AC: #1, #3)
  - [x] Prefer extending `TicketsLayout` carefully (AD-2: layout module owns paths; ingest logic stays out of Gmail)
- [x] Offline tests `tests/test_ticket_folder_ingest.py` (AC: #5)
- [x] Short note in phone setup (8.4) pointing Syncthing/OneDrive at `tickets/inbox/`

## Dev Notes

### Architecture

- **AD-2 / AD-8:** Folder drain is CLI + tiny filesystem helper; do not put watchers inside `engine`.
- No long-running `watchdog` daemon required for MVP — scheduled batch (daily + weekly-ops) matches locked cadence. Optional later: `watchdog` if Simon wants instant local sync.

### Anti-patterns

- Do not sync OneDrive **directly** into `unclassified/` (classify may race). Always land in `inbox/` then drain.
- Do not follow symlinks outside tickets root.
- Do not implement cloud APIs for Drive/OneDrive — OS sync client only.

### References

- Epics Story 8.3; FR41–FR44; options B/C in Epic 8 table
- Stories 8.1 (primary mail), 8.2 (dedup)

## Dev Agent Record

### Completion Notes List

### File List
