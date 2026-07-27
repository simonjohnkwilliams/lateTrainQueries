---
story_key: 9-4-table2-ops-email-weekly-chain
epic: 9
status: done
created: 2026-07-27
baseline_commit: 2099029
depends_on: [9-3]
blocks: []
---

# Story 9.4: Table 2 in ops email + weekly chain

Status: done

## Story

As the recipient of the weekly ops email,
I want an open follow-up section (Table 2) and automatic drop-off once a paid claim has been reported,
So that I stop wondering "did I get paid?" and stop being reminded of claims already settled.

## Acceptance Criteria

1. **Table 2 build (AD-20, FR37).** `_build_table2(out_dir)` renders `open_for_table2()` rows as `{claim_id, status, journey_date}`. Store `submitted` displays as `in_flight`; other statuses pass through.
2. **Ops email composition (AD-20).** `_run_weekly_ops_email` builds Table 1 (existing) and Table 2 (new) and renders them in a single email. Table 2 is empty/absent only when the store has no open rows.
3. **Pure renderer.** `ops_email.render_ops_email` stays pure; no Gmail/lifecycle/config imports (verified by existing source-scan test).
4. **Post-send mark (AD-20, FR39).** On successful email send, the chain calls `mark_reported_paid` for every paid claim id that appeared in the sent Table 2 (`store.status == "paid"`, not the display label).
5. **Failure isolation.** Email failure (rc != 0) must not mark any paid rows reported — the chain returns early before `_mark_paid_reported_after_email`.
6. **Chain order (AD-21).** `--weekly-ops` order: ingest → assess → classify → file → lifecycle refresh → ops email (Table 1 + Table 2) → `mark_reported_paid` → completion marker.
7. **Next week.** Reported-paid rows are omitted from the next week's Table 2 via `open_for_table2` (store filter).
8. **Offline-first (AD-12).** `tests/test_table2_cli.py` + un-skipped `tests/test_ops_email.py` Table 2 cases; `tests/test_weekly_ops_cli.py` chain-order test extended.

## Tasks / Subtasks

- [x] RED: un-skip `tests/test_ops_email.py::test_render_ops_email_table2_statuses` and `..._omits_reported_paid_rows`; add `tests/test_table2_cli.py` (8 cases — build, display, omit reported, empty, mark, no-op, end-to-end sink, chain marks after success, chain does not mark on email failure)
- [x] GREEN: `_build_table2`, `_mark_paid_reported_after_email` in `trainline/cli.py`
- [x] Extend `_run_weekly_ops_email` to return `(rc, paid_ids_sent)` and accept `out_dir`; pass Table 2 to `render_ops_email`
- [x] Extend `_run_weekly_ops` chain: refresh → email → mark → marker (refresh failure non-blocking; mark only after successful email)
- [x] Update existing `tests/test_weekly_ops_cli.py` mocks to return `(0, [])` from `_run_weekly_ops_email` and capture `refresh`/`mark`/`complete` in order
- [x] `python -m pytest -q --tb=line` green — 477 passed, 75 deselected

### Review Findings

(none — first-pass clean; renderer stays pure; store API unchanged)

## Dev Notes

- `_run_weekly_ops_email` now returns `tuple[int, list[str]]`; the second element is the paid claim ids that appeared in the sent Table 2. The chain calls `_mark_paid_reported_after_email` unconditionally — it no-ops when the list is empty (keeps chain order stable and the test assertion clean).
- `_mark_paid_reported_after_email` delegates to `LifecycleStore.mark_reported_paid`, which only stamps `status == "paid"` rows (AC #5 of 9.1) — non-paid rows in the same payload are silently ignored.
- Reported-paid rows drop out via `open_for_table2` (`reported_paid_at is None`) — no extra filter needed in `_build_table2`.
- Display label `in_flight` is presentation only — never persisted (matches AD-18 / 9.1 contract).
- Table 1 path unchanged; Table 2 is additive. Existing Table 1 renderer tests stay green.

## Dev Agent Record

### Agent Model Used

Composer (opencode)

### Completion Notes List

- 8 new offline Table 2 CLI tests + 2 un-skipped renderer tests; weekly-ops order test extended to `ingest → assess → classify → file → refresh → email → mark → complete`.
- `_run_weekly_ops_email` returns `(rc, paid_ids_sent)`; chain only marks after `rc == 0`.
- Full suite: 477 passed, 75 deselected.

### File List

- `trainline/cli.py`
- `tests/test_table2_cli.py` (new)
- `tests/test_ops_email.py`
- `tests/test_weekly_ops_cli.py`
- `_bmad-output/implementation-artifacts/9-4-table2-ops-email-weekly-chain.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-27 — Story implemented (RED→GREEN); status → done; Epic 9 complete
