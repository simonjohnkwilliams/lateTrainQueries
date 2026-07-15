---
baseline_commit: 8e812f542cfdb286a321600d0e5fc890587c3370
---
# Story 3.3: CLI composition root — end-to-end run

Status: done

## Story

As Simon,
I want one command that produces a week of file-ready claims,
so that filing is a matter of copying verified rows into the SWR form.

## Acceptance Criteria

1. **`cli.py` is the sole orchestrator (AD-8).**
2. **End-to-end run over a stubbed week produces CSV + JSON.**
3. **A fetch-failed day is reported as "not analysed", distinct from a clean no-claim day (AD-5).**
4. **The recorded real-HSP fixtures drive an offline end-to-end BDD scenario that passes (FR21).**

## Tasks / Subtasks

- [x] **Task 1 — Write the acceptance scenarios first (AC: 1, 2, 3, 4)**
- [x] **Task 2 — Wire `trainline/cli.py` as the composition root (AC: 1, 2)**
- [x] **Task 3 — Surface the AD-5 status distinction in the run output (AC: 3)**
- [x] **Task 4 — Provide `python -m trainline` / console entry (AC: 1, 2)**
- [x] **Task 5 — Offline & recorded verification (AC: 2, 4)**
- [x] **Task 6 — (Optional) live smoke path (AC: n/a)** — added `@live` smoke + schema suite; gated on `HSP_CREDENTIALS_FILE`.

## Dev Agent Record

### Agent Model Used

Composer (Amelia / bmad-dev-story)

### Completion Notes List

- `cli.run` wires config → hsp_client → optimise → storage; batching by `batch_size`.
- `cli.main` + `trainline/__main__.py` for one-command runs; creds via env/path override only.
- BDD pipeline scenarios green offline (stub claimable, FETCH_FAILED, recorded quiet Thursday).
- Live smoke/schema tests added; local run currently returns HSP HTTP 401 against `creds/trainConfig.txt` `[configuration]` username/password — needs valid HSP Open Rail Data credentials to go green.

### File List

- trainline/cli.py
- trainline/__main__.py
- tests/features/claims_pipeline.feature
- tests/test_bdd_pipeline.py
- tests/test_cli.py
- tests/hsp_schema.py
- tests/test_hsp_schema_fixtures.py
- tests/test_live_smoke.py
- trainline/adapters/config.py (loader tolerates trailing portal-export notes)

### Change Log

- 2026-07-15: Story 3.3 implemented and marked done; Phase C live suite added.
