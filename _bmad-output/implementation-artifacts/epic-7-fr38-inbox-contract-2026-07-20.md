# Epic 7 — Architecture review (FR37/FR38 inbox lifecycle)

**Date:** 2026-07-20  
**Input:** Live SWR emails for claim `SWR-0218-108-579` (Gmail PDF exports)  
**Verdict:** **No blockers** — proceed to story creation. One FR status-set refinement only.

## Observed inbox contract (replaces placeholders)

| Order | Subject stage token | Mapped status | Observed sent |
| --- | --- | --- | --- |
| 1 | `RECEIVED` | `received` | Fri 17 Jul 2026 15:33 |
| 2 | `Approved` | `approved` | Sat 18 Jul 2026 09:02 |
| 3 | `PAYMENT SENT` | `paid` | Sat 18 Jul 2026 13:01 |

**From:** `No-replySWRDR@firstcustomercontact.com`  
**Subject shape:** `South Western Railway Delay Repay - Claim {SWR-####-###-###} - {STAGE}`  
**Amount:** `£1.57` present on all three bodies (matches 12.5% of return fare for 15–29 band).

## FR / AD impact

| Item | Finding |
| --- | --- |
| FR38 three-stage success | Still valid: submit → inbox received → payment. **Approved** is an intermediate inbox stage between received and paid (not a fourth success gate for “successful in last digest”). |
| FR37 Table 2 statuses | Extend set: `received` / `approved` / `paid` / `failed` / `in_flight`. Treat `approved` as not-yet-successful for Table 2 omission rules (omit only after `paid` reported). |
| AD-2 | Parser stays in `adapters/gmail/claim_mail.py` (string→DTO); lifecycle store later in adapters; cli wires. No engine I/O. |
| AD-8 | Weekly chain remains composition-root only. |
| NFR3 / Gmail TLS | `run_auth_flow` must inject `truststore` (same as HSP) — fixed 2026-07-20. |
| NFR11 | Offline fixtures under `tests/fixtures/swr_claim_mail/`; live `@gmail` opt-in. |

## Challenges raised?

**None that block Epic 7 stories.**  
Open product nuance (non-blocking): whether Table 2 should show `approved` as its own column/state vs collapse into `in_flight` until payment — default recommendation: **surface `approved`** (matches real mail; clearer than “in flight”).

## Code landed with this review

- `trainline/adapters/gmail/claim_mail.py` — subject/body parser + Gmail message helpers  
- Offline tests: `tests/test_swr_claim_mail.py`  
- Live opt-in: `tests/test_live_gmail_claim_mail.py` (`pytest -m gmail`)  
- Fixtures: `tests/fixtures/swr_claim_mail/samples.py`

Stories 7.4 / 7.5 should wire these parsers into Table 2 + lifecycle store rather than re-characterising placeholders.
