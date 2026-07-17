---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.2: Claim-to-ticket matcher

Status: done

## Story

As Simon,
I want every claim date to have a matching ticket before filing,
so that I never submit a claim without proof attached.

## Acceptance Criteria

1. **Missing date fails.** Claims for 07-08, 07-09, 07-10 with tickets only for 07-08 and 07-10 → reports 07-09 missing, returns failure. *(FR25)*
2. **Multiple tickets per date OK.** Any one valid file satisfies a date.
3. **Mapping output.** Returns `dict[date_str, Path]` for submission adapter. *(FR28 prep)*
4. **Claim date format.** Match on `Claim.date` (ISO `YYYY-MM-DD`) converted to `MM-DD`.

## Dev Agent Record

### Completion Notes List

- `match_tickets_to_claims` → `MatchResult(ok, missing_dates, mapping, errors)`.
- `gate_blocks_filing` for Epic 6 `--file` skip path.
- Unit + BDD green.

### File List

- `trainline/adapters/ticket_gate.py`
- `tests/test_ticket_match.py`
- `tests/features/ticket_gate.feature`
- `tests/test_bdd_ticket_gate.py`

## Change Log

- 2026-07-16: Implemented; done.
