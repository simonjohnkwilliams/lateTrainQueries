---
story_key: 7-4-ops-email-tables
epic: 7
status: ready-for-dev
created: 2026-07-20
depends_on: [7-1, 7-5]
---

# Story 7.4: Ops email Tables 1 and 2

Status: ready-for-dev

## Story

As Simon,
I want Table 1 for this week's new/open work and Table 2 for follow-up on earlier claims,
So that I see both action needed now and payment outcomes later.

## Acceptance Criteria

1. **Table 1 — this run (FR36).** Email body includes:
   - late / claimable trains (optimiser output)
   - tickets transformed / matched to those trains
   - rejection list: short reason + file path
   - newly filed claims + still-open claims from this run
2. **Table 2 — follow-up (FR37).** Lists previously actioned claims not yet reported **paid** in the last digest, with status: `received` / `approved` / `paid` / `failed` / `in_flight`.
3. **Omit closed successes (FR37, FR39).** Claims already reported as successful (`paid`) in the last digest are omitted from Table 2.
4. **Inbox matchers (FR38).** Use characterised SWR rules (not placeholders):
   - From: `No-replySWRDR@firstcustomercontact.com`
   - Subject: `South Western Railway Delay Repay - Claim {SWR-####-###-###} - {RECEIVED|Approved|PAYMENT SENT}`
   - Map via `trainline.adapters.gmail.claim_mail` → `ClaimMailStage`
5. **Transport.** Send via Gmail API (Story 7.1); SMTP legacy only as explicit fallback.
6. **Offline tests.** Render Tables 1–2 from fixtures with zero network; assert HTML/text contain expected rows. Live `@gmail` optional for send smoke.

## Tasks

- [ ] Pure(ish) renderer: `render_ops_email(table1, table2) -> (html, text)` — prefer living next to `notification.py` digest helpers or new `adapters/ops_email.py` with **no** Gmail import (CLI sends).
- [ ] Build Table 2 rows from lifecycle store (7.5) + optional fresh Gmail lookup results passed in by CLI.
- [ ] Wire subject line distinct from legacy digest (e.g. `Delay Repay weekly ops — {anchor Friday}`).
- [ ] Offline tests using `tests/fixtures/swr_claim_mail/samples.py` for status labels.
- [ ] Extend/replace legacy `--digest` path or keep both until weekly-ops is default.

## Dev Notes

### Inbox contract (locked 2026-07-20)

See `epic-7-fr38-inbox-contract-2026-07-20.md`.

| Subject stage | Table 2 status | Closes claim for omission? |
| --- | --- | --- |
| RECEIVED | received | No |
| Approved | approved | No |
| PAYMENT SENT | paid | Yes (after reported in a digest) |

`in_flight` = submitted locally, no matching inbox mail yet.  
`failed` = portal/audit failure or explicit reject (define from Epic 6 audit).

### Guardrails

- **AD-2:** Renderer does not call Gmail; CLI searches inbox / loads state, then renders, then sends.
- Do not treat `approved` as digest-success; only `paid` omits next week.
- Reuse `parse_swr_claim_mail` / `parse_gmail_message` — do not re-parse subjects ad hoc in the renderer.

### Anti-patterns

- Placeholder subject regexes (“confirmation”, “payment received”) — **forbidden**; real tokens above.
- Putting £ amounts in Table 2 without claim id.
- Cards/HTML frameworks — keep simple tables like existing digest.

### Automated tests (pre-written)

| File | Notes |
| --- | --- |
| `tests/test_ops_email.py` | Skip until `adapters/ops_email.py`; Tables 1–2 + AD-2 |
| `tests/test_swr_claim_mail.py` | **Live now** — FR38 subject/stage mapping |
| `tests/test_live_gmail_claim_mail.py` | LIVE `@gmail` characterisation |

### References

- Epics Story 7.4; FR35–FR38
- `claim_mail.py`, fixtures, `tests/test_swr_claim_mail.py`
- Story 7.5 lifecycle state (source of truth for “reported paid”)
- Sign-off: `manual-validation-checklist-epic-7.md`