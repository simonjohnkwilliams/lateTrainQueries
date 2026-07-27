---
story_key: 9-2-record-submitted-on-live-file
epic: 9
status: done
created: 2026-07-27
baseline_commit: 6ed3ac4
depends_on: [9-1]
blocks: [9-3, 9-4]
---

# Story 9.2: Record submitted on successful live file

Status: done

## Story

As the ops pipeline,
I want successful live SWR filings to seed the lifecycle store with `submitted`,
So that Table 2 follow-up can track each claim through to paid.

## Acceptance Criteria

1. **CLI-only mutation (AD-19).** After `_file_claims` succeeds, only `cli` calls `LifecycleStore.record_submitted`.
2. **Real SWR id required.** `record_submitted` runs only when `SubmitResult.ok` and `normalize_claim_id(swr_reference)` returns `SWR-####-###-###`.
3. **Captcha abandon / non-SWR ref.** `ok=False` or `FAKE-*` / `SUBMITTED-*` refs produce no lifecycle row and no error.
4. **Idempotent.** Re-running on the same SWR id does not duplicate or regress the row (delegated to store AC).
5. **Path.** Store lives at `{audit_path.parent}/claim-lifecycle.json` (matches `Results/claim-lifecycle.json` for default audit).
6. **Offline-first (AD-12).** `tests/test_file_cli.py` covers SWR success, fake ref, captcha abandon with `@pytest.mark.offline`.

## Tasks / Subtasks

- [x] RED: extend `tests/test_file_cli.py` with three cases (success → submitted; fake ref → no row; captcha abandon → no row)
- [x] GREEN: add `_claim_lifecycle_path` + `_record_lifecycle_submissions` in `trainline/cli.py`; call after `submit_all_claims` in `_file_claims`
- [x] `python -m pytest -q --tb=line tests/test_file_cli.py` green; full offline suite 461 passed, 2 skipped
- [x] No Gmail/playwright import added inside `claim_lifecycle` adapter

### Review Findings

(none — first-pass clean; store ACs already hardened in 9.1)

## Dev Notes

- `_record_lifecycle_submissions` lazily imports `LifecycleStore` + `normalize_claim_id` so the store stays hexagonally clean.
- Store is constructed only when at least one successful SWR submit is observed (avoids touching the filesystem when nothing was filed).
- Captcha abandon path: `FakeBrowserSession(fail_dates=...)` returns `ok=False` and is skipped before `normalize_claim_id` runs.

## Dev Agent Record

### Agent Model Used

Composer (opencode)

### Completion Notes List

- 9.2 wired: `_record_lifecycle_submissions(audit_path, batch, items)` invoked at the end of `_file_claims`.
- `_SwrRefBrowserSession` test stub returns `SWR-0218-108-579` (matches live observed id from Epic 7 FR38 contract).
- 3 new offline tests; full suite 461 passed, 2 skipped.

### File List

- `trainline/cli.py`
- `tests/test_file_cli.py`
- `_bmad-output/implementation-artifacts/9-2-record-submitted-on-live-file.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-27 — Story implemented (RED→GREEN); status → done
