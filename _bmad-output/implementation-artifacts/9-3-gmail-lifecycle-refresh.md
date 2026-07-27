---
story_key: 9-3-gmail-lifecycle-refresh
epic: 9
status: done
created: 2026-07-27
baseline_commit: 2099029
depends_on: [9-2]
blocks: [9-4]
---

# Story 9.3: Gmail lifecycle refresh via claim_mail

Status: done

## Story

As the weekly ops chain,
I want a best-effort Gmail search to advance stored claim statuses via `apply_stage`,
So that Table 2 reflects received → approved → paid before the digest is sent.

## Acceptance Criteria

1. **Best-effort refresh (AD-19, FR38).** `_refresh_claim_lifecycle` reads `LifecycleStore`, searches Gmail per known claim id, and applies monotonic `apply_stage` using `ClaimMailStage.value`.
2. **UNKNOWN skipped.** Messages whose stage parses to `ClaimMailStage.UNKNOWN` do not change the row.
3. **Failure isolation.** Gmail/parse failures for one claim warn on stderr and continue to the next — never raise; the weekly chain must not block.
4. **No Gmail configured.** When no `## Gmail API ##` config exists, refresh is a no-op warning (return 0) — Table 1 email still sends.
5. **Reported-paid excluded.** Only `open_for_table2()` rows are searched; paid-and-reported rows are not re-queried.
6. **Chain order.** Refresh runs between `--file` and the ops email (AD-21).
7. **Offline-first (AD-12).** `tests/test_lifecycle_refresh_cli.py` uses a stub Gmail client; no network.

## Tasks / Subtasks

- [x] RED: `tests/test_lifecycle_refresh_cli.py` — 6 cases (received advance, paid chain, UNKNOWN skip, no client no-op, search failure warn, reported-paid skip)
- [x] GREEN: `_lifecycle_gmail_client_factory` test seam + `_build_lifecycle_gmail_client` + `_refresh_claim_lifecycle` + `_run_weekly_lifecycle_refresh` in `trainline/cli.py`
- [x] Wire `_run_weekly_lifecycle_refresh` into `_run_weekly_ops` between file and email
- [x] `python -m pytest -q --tb=line tests/test_lifecycle_refresh_cli.py` green; full suite 477 passed

### Review Findings

(none — first-pass clean; store monotonicity guarded by 9.1)

## Dev Notes

- Refresh only iterates `open_for_table2()`; the reported-paid filter prevents redundant Gmail queries for claims already removed from Table 2.
- `_build_lifecycle_gmail_client` reuses `load_gmail_config` + `GmailConfig` + `get_credentials` + `GmailClient`; raising `GmailConfigError` is the "not configured" path (returns `None`).
- Test seam `_lifecycle_gmail_client_factory` mirrors the `_digest_transport` / `_file_browser_factory` pattern; tests inject a fake client or assert "skipped" when no factory + no client.
- `swr_claim_search_query` is reused verbatim from `claim_mail`; `parse_gmail_message` is the pure Gmail→`SwrClaimMail` parser (no new Gmail code in `claim_lifecycle`).

## Dev Agent Record

### Agent Model Used

Composer (opencode)

### Completion Notes List

- 6 new offline tests; `_refresh_claim_lifecycle` warns and returns 0 on every failure path.
- `_run_weekly_lifecycle_refresh(out_dir, credentials_path)` is the chain-facing wrapper; uses `_default_lifecycle_path_for_out_dir`.
- Full suite: 477 passed, 75 deselected (live `@gmail` opt-in only).

### File List

- `trainline/cli.py`
- `tests/test_lifecycle_refresh_cli.py`
- `_bmad-output/implementation-artifacts/9-3-gmail-lifecycle-refresh.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-07-27 — Story implemented (RED→GREEN); status → done
