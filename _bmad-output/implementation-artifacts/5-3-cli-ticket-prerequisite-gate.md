---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.3: CLI ticket prerequisite gate

Status: done

## Story

As Simon,
I want `--check-tickets` to validate tickets without filing,
so that I can fix naming gaps before a filing run.

## Acceptance Criteria

1. **`--check-tickets` standalone.** Validates tickets against `claims.json` in `--out-dir`. Non-zero exit on failure. *(FR25)*
2. **Human-readable errors.** Lists missing dates and misnamed files.
3. **Gate blocks filing.** `gate_blocks_filing(MatchResult)` is the Epic 6 hook (no Playwright yet).
4. **Offline tests.** Full gate logic via tmp dirs + BDD.

## Dev Agent Record

### Completion Notes List

- CLI: `--check-tickets`, `--ticket-dir` (default `ticket/`).
- Reads `Results/claims.json` (or `--out-dir`); no HSP fetch.
- Full suite: 219 passed offline.

### File List

- `trainline/cli.py`
- `trainline/adapters/ticket_gate.py`
- `tests/features/ticket_gate.feature`
- `tests/test_bdd_ticket_gate.py`
- `tests/test_cli.py`

## Change Log

- 2026-07-16: Implemented; done.
