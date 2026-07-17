---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 6.3: Batch auto-file all claims + audit log

Status: ready-for-dev

## Story

As Simon,
I want every emitted claim row filed automatically with a persistent audit trail,
so that I trust the engine to handle the full week and can review what was submitted.

## Acceptance Criteria

1. **All rows submitted.** Batch processes every claim from the run. *(R2-FR5)*
2. **JSONL audit log.** Append-only file: timestamp, date, direction, outcome, swr_reference, raw_reason. *(R2-FR8, R2-NFR4)*
3. **Partial failure.** One failure does not abort remaining rows; summary reports counts.
4. **Default path.** `results/filing-audit.jsonl` (configurable).

## Dev Notes

- `submit_all_claims(claims, ticket_mapping, config) -> BatchResult`
- Audit writer in `claim_submission.py` or `storage.py` (prefer submission adapter owns audit)
