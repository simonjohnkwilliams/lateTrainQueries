---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.6: Gate on ready_to_claim + claimed dedup API

Status: done

## Story

As Simon, I want the ticket gate to scan OCR-ready tickets and Epic 6 to skip already-claimed dates.

## Acceptance Criteria

1. `resolve_ticket_scan_dir` prefers `tickets/processed/ready_to_claim`.
2. `claimed_mm_dds` / `filter_claims_not_already_claimed` / `move_to_claimed` for Epic 6.
3. `@ocr` fixture tests (deselected by default) for blank / wrong-route / GOD sample.

## Epic 6 contract (notes)

- Submit source tickets from `ready_to_claim`.
- On successful submit: `move_to_claimed(path, claimed_dir)`.
- Before submit: filter claims with `filter_claims_not_already_claimed`.

## File List

- `trainline/adapters/ticket_gate.py`
- `tests/test_ocr_fixtures.py`
- `pytest.ini`
