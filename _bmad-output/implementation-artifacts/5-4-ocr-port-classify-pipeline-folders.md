---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.4: OCR port + classify pipeline + folders

Status: done

## Story

As Simon, I want unclassified ticket photos OCR'd and sorted into ready/rejected folders so naming is automatic.

## Acceptance Criteria

1. Injectable `OcrEngine` (Tesseract + Fake); low confidence → `unreadable-<stamp>-…` in rejected.
2. Wrong route → `Not_valid_Route-<stamp>-…` in rejected.
3. GOD↔WAT + journey date → `MM-DD-TICKET_NUMBER.ext` in `processed/ready_to_claim`.

## File List

- `trainline/adapters/ticket_intake.py`
- `tests/test_ticket_intake.py`
- `tests/fixtures/tickets/`
- `sample-tickets/` (gitignored bulk dump)
