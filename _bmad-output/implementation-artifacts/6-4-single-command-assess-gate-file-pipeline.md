---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 6.4: Single-command assess → gate → file pipeline

Status: done

## Story

As Simon,
I want one command that assesses, checks tickets, files everything, emails the digest, and logs the audit,
so that weekly Delay Repay is fully hands-off.

## Acceptance Criteria

1. **`--file` pipeline.** assess → CSV/JSON → ticket gate → batch submit → audit log → digest email. *(R2-FR9)*
2. **Ticket gate blocks submit.** Missing tickets: assess output written, submission skipped, non-zero exit. *(R2-FR4)*
3. **Release 1 preserved.** Default `python -m trainline` = assess-only (no gate, no submit).
4. **Run summary.** Stdout: claims found, filed, failed, audit path, digest sent/not.
5. **BDD end-to-end.** Offline scenario with fake submission + notification transports.

## Dev Notes

- Orchestration in `cli.py` only (AD-8)
- Suggested invocation: `python -m trainline --file` or `python -m trainline --file --digest`
- This story wires Epics 4, 5, 6 together — implement last
- **Ticket folders (Epic 5b):** scan `tickets/processed/ready_to_claim`; on successful submit call `move_to_claimed`; before batch use `filter_claims_not_already_claimed` against `tickets/claimed/` so the same claim date is not filed twice.
- Optional: run `--classify-tickets` before `--file` (or document as a prerequisite step).
