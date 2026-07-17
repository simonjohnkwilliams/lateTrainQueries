---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 5.1: Ticket naming contract + directory scanner

Status: done

## Story

As Simon,
I want a defined ticket directory and naming format,
so that the tool can reliably match tickets to claim dates.

## Acceptance Criteria

1. **Naming regex.** Accept `<MM-DD-TICKET_NUMBER>` with extensions `.jpg`, `.jpeg`, `.png`, `.pdf` (case-insensitive ext). *(FR23, FR24)*
2. **Parse fields.** `07-10-ABC123.pdf` → month=07, day=10, ticket_number=ABC123.
3. **Reject misnamed.** Files not matching pattern listed with expected format hint.
4. **Configurable path.** Default `ticket/`; override via config or `--ticket-dir`.

## Dev Agent Record

### Completion Notes List

- Implemented `trainline/adapters/ticket_gate.py`: `parse_ticket_filename`, `scan_ticket_dir`, `EXPECTED_FORMAT`.
- `RunConfig.ticket_dir` + CLI `--ticket-dir`.
- Unit + BDD coverage; import boundaries updated.

### File List

- `trainline/adapters/ticket_gate.py`
- `trainline/adapters/config.py`
- `tests/test_ticket_scan.py`
- `tests/features/ticket_gate.feature`
- `tests/test_bdd_ticket_gate.py`
- `tests/test_import_boundaries.py`
- `tests/test_package_imports.py`

## Change Log

- 2026-07-16: Implemented; done.
