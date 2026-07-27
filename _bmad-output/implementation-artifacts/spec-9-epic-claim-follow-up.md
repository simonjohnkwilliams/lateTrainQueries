---
title: 'Epic 9 remaining — claim follow-up (9.2–9.4)'
type: 'feature'
created: '2026-07-27'
status: 'in-progress'
baseline_revision: '6ed3ac4'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-9-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/9-1-claim-lifecycle-store.md'
warnings:
  - multiple-goals
  - oversized
---

<intent-contract>

## Intent

**Problem:** Successful filings and inbox stages never update lifecycle or Table 2, so weekly ops cannot show follow-up until paid or drop reported paid claims.

**Approach:** Wire CLI-only mutations: `record_submitted` on successful file (9.2), best-effort Gmail→`apply_stage` refresh (9.3), then Table 2 build + post-send `mark_reported_paid` in the weekly chain (9.4). Store from 9.1 stays as-is.

## Boundaries & Constraints

**Always:**
- Only `cli` mutates `LifecycleStore` (AD-19).
- Persist statuses only `submitted|received|approved|paid|failed`; display `submitted` as `in_flight` in email only.
- Monotonic `apply_stage`; `mark_reported_paid` only for rows that were `paid` in the sent Table 2.
- Weekly order: ingest → assess → classify → file → lifecycle refresh → ops email → mark reported → marker (AD-21).
- Refresh failures warn and continue; marker only after email success.
- Default pytest offline; `@gmail` live opt-in only.
- `record_submitted` only when `SubmitResult.ok` and `normalize_claim_id(swr_reference)` yields `SWR-####-###-###`.

**Block If:**
- Required Gmail scopes or config keys for refresh are missing in a way that cannot soft-fail — prefer warn+continue; only block if inventing new OAuth scopes beyond existing modify/send/readonly.

**Never:**
- Import Gmail/playwright inside `claim_lifecycle` or `ops_email`.
- Adapter→adapter imports.
- Rewrite filing-audit.jsonl as status.
- Persist `in_flight`.
- Paper-ticket preprocessor / SQLite / cloud.
- Implement deferred 7.4/7.5 story files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Live file success | `ok=True`, `swr_reference=SWR-…` | `record_submitted` once | No error |
| Captcha abandon | `ok=False` / no ref | No lifecycle row | Continue file batch |
| Non-SWR ref | `FAKE-SWR-…` / `SUBMITTED-…` | No lifecycle row | Ignore |
| Refresh mail | Fixture Gmail → received/approved/paid | `apply_stage` advances | Offline mock |
| Refresh fail | Gmail raises | Warn; email still runs | Best-effort |
| Table 2 build | Open lifecycle rows | `submitted`→`in_flight` display | Pure render |
| Post-send mark | Email ok + paid rows shown | `mark_reported_paid` those ids | Skip non-paid |
| Next week | Previously reported paid | Omitted from Table 2 | Store filter |

</intent-contract>

## Code Map

- `trainline/adapters/claim_lifecycle.py` -- store API (done in 9.1; reuse)
- `trainline/adapters/gmail/claim_mail.py` -- `normalize_claim_id`, `parse_gmail_message`, `swr_claim_search_query`, `ClaimMailStage`
- `trainline/adapters/ops_email.py` -- pure `render_ops_email(table1, table2, …)`
- `trainline/adapters/claim_submission.py` -- `SubmitResult.ok` / `swr_reference`
- `trainline/cli.py` -- `_file_claims`, `_run_weekly_ops`, `_run_weekly_ops_email` (composition root)
- `tests/test_file_cli.py` -- 9.2 offline hooks
- `tests/test_weekly_ops_cli.py` -- chain order + mark after email
- `tests/test_ops_email.py` -- un-skip Table 2 render assertions
- `tests/test_claim_lifecycle.py` -- store contract (already green)

## Tasks & Acceptance

**Execution:**
- [ ] `tests/test_file_cli.py` (+ helpers) -- RED then GREEN: success → lifecycle `submitted`; abandon/non-SWR → no row -- 9.2
- [ ] `trainline/cli.py` -- in `_file_claims`, after successful submit with normalized SWR id, `LifecycleStore.record_submitted(...)` under `Results/claim-lifecycle.json` (or out_dir) -- 9.2
- [ ] `tests/…` offline refresh -- mocked Gmail messages → `apply_stage` -- 9.3
- [ ] `trainline/cli.py` -- `_refresh_claim_lifecycle(...)` best-effort; call between file and email in `_run_weekly_ops` -- 9.3
- [ ] `tests/test_ops_email.py` / `tests/test_weekly_ops_cli.py` -- Table 2 rows + order + mark after send -- 9.4
- [ ] `trainline/cli.py` -- `_run_weekly_ops_email` builds Table 2 from `open_for_table2` (`submitted`→`in_flight`); after successful send `mark_reported_paid` for paid rows shown -- 9.4
- [ ] Sprint status -- move 9.2–9.4 through in-progress → review/done as each slice lands; keep 9.1 done

**Acceptance Criteria:**
- Given successful file with SWR id, when CLI finishes, then lifecycle has `submitted` for that id
- Given captcha abandon or non-SWR ref, when file finishes, then no new lifecycle row
- Given mocked inbox stages, when refresh runs, then statuses advance monotonically without network
- Given refresh failure, when weekly-ops continues, then Table 1 email still sends
- Given open lifecycle rows, when ops email renders, then Table 2 shows them with `in_flight` for `submitted` and real `approved`
- Given successful email including paid rows, when post-send runs, then those ids get `reported_paid_at` and omit next week
- Given `--weekly-ops`, when instrumented, then order includes refresh before email and mark before marker

## Design Notes

Lifecycle path: prefer `{out_dir}/claim-lifecycle.json` when CLI has `out_dir`, else `DEFAULT_LIFECYCLE_PATH`. Keep store API unchanged.

Refresh: for each known claim id in store (or open_for_table2), search via `swr_claim_search_query`, parse, `apply_stage(claim_id, stage.value)` skipping UNKNOWN.

Only mark paid rows that appeared in the Table 2 payload just sent (store status `paid`, not display label).

## Verification

**Commands:**
- `python -m pytest -q --tb=line` -- expected: all offline tests pass; no new live tests without `@gmail`
- `python -m pytest -q --tb=line tests/test_file_cli.py tests/test_weekly_ops_cli.py tests/test_ops_email.py tests/test_claim_lifecycle.py` -- expected: green for Epic 9 wiring
