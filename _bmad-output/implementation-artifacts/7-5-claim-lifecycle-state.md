---
story_key: 7-5-claim-lifecycle-state
epic: 7
status: ready-for-dev
created: 2026-07-20
depends_on: [7-1]
blocks: [7-4]
---

# Story 7.5: Claim lifecycle state store

Status: ready-for-dev

## Story

As Simon,
I want durable local state for filed / received / paid / reported,
So that Table 2 and idempotent runs stay correct across weeks.

## Acceptance Criteria

1. **On successful Epic 6 file.** Persist claim lifecycle record: claim id (e.g. `SWR-0218-108-579`), journey date, direction/route summary, `submitted` + timestamp, audit path (FR38 stage 1).
2. **On Gmail inbox update.** When search finds RECEIVED / Approved / PAYMENT SENT for a known claim id, update status (+ timestamps). Prefer highest stage seen (received < approved < paid).
3. **Reported-paid flag.** When Table 2 includes a `paid` row in a sent digest, mark `reported_paid_at` so the next run omits it (FR37, FR39).
4. **Durable, local, gitignored.** JSON/SQLite under a project state dir (e.g. `Results/claim_lifecycle.json` or `state/`) — never committed; documented in `.gitignore`.
5. **Offline tests.** Fake clock + fixture mail updates; assert transitions and omission eligibility without network.

## Tasks

- [ ] Define frozen record shape (dataclass) + load/save module in `adapters/` (e.g. `claim_lifecycle.py`) — **no** Gmail import inside the store.
- [ ] Hook Epic 6 audit success path (CLI or submission result handler) to upsert `submitted`.
- [ ] Upsert from parsed `SwrClaimMail` list supplied by CLI after inbox search.
- [ ] Query helpers: `open_for_table2()` (not reported paid), `mark_reported_paid(claim_ids, when)`.
- [ ] Offline unit tests for ordering, idempotent upserts, and omit-after-reported.

## Dev Notes

### Status enum (align with `ClaimMailStage` + local)

| Status | Meaning |
| --- | --- |
| submitted | Portal file succeeded; no inbox mail yet → Table 2 `in_flight` |
| received | Inbox RECEIVED |
| approved | Inbox Approved |
| paid | Inbox PAYMENT SENT |
| failed | Filing/audit failure |

### Guardrails

- **AD-2 / AD-3:** Store owns persistence only; does not import Playwright or Gmail client.
- Claim id format: `SWR-\d{4}-\d{3}-\d{3}` (confirmed live).
- Idempotent upserts by claim id; never duplicate rows on weekly re-run.
- Human captcha abandon (filled but not submitted) must **not** create a submitted lifecycle row.

### Suggested file layout

```
trainline/adapters/claim_lifecycle.py   # load/save/upsert/query
Results/claim_lifecycle.json            # or state/ — gitignored
tests/test_claim_lifecycle.py           # offline
```

### Automated tests (pre-written)

| File | Notes |
| --- | --- |
| `tests/test_claim_lifecycle.py` | Skip until `adapters/claim_lifecycle.py`; transitions + omit reported paid |

### References

- Epics Story 7.5; FR37–FR39
- Inbox contract: `epic-7-fr38-inbox-contract-2026-07-20.md`
- Epic 6 audit log shape (confirmation id parsing in `claim_submission.py`)
- Sign-off: `manual-validation-checklist-epic-7.md`