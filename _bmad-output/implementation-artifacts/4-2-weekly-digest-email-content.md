---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 4.2: Weekly digest email content

Status: done

## Story

As Simon,
I want the email to summarise claimable rows for the week,
so that I can see at a glance what was found without opening files.

## Acceptance Criteria

1. **Claim rows listed.** Digest includes date, direction, band, origin→destination, delay_min for each claim. *(FR22 / R2-FR1)*
2. **Fetch-failed days distinct.** Days with `FETCH_FAILED` appear as "not analysed", not as no-claim. *(AD-5)*
3. **Zero-claim week.** Email explicitly states no claimable rows found.
4. **HTML + plain text.** Both formats generated; tables readable in plain-text clients.

## Tasks / Subtasks

- [x] **Task 1 — `render_digest` pure function (AC: 1–4)**
- [x] **Task 2 — Tests (AC: 1–4)**

## Dev Agent Record

### Completion Notes List

- Added `render_digest` / `digest_subject` in `notification.py` (imports `engine.models` only).
- Unit + BDD coverage for claims, FETCH_FAILED vs no-claim, zero-claim, HTML+text.
- Full suite: 186 passed.

### File List

- `trainline/adapters/notification.py`
- `tests/test_digest_content.py`
- `tests/features/notification.feature`
- `tests/test_bdd_notification.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-16: Implemented digest content rendering; done.
