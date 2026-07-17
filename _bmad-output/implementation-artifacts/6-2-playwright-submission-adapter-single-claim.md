---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 6.2: Playwright submission adapter — single claim

Status: done

## Story

As Simon,
I want one claim row auto-filled and submitted on the SWR site,
so that manual copy-paste is eliminated for a single journey.

## Acceptance Criteria

1. **Form fill.** Journey date, stations, scheduled/actual times, delay reason populated from mapped fields. *(R2-FR5, R2-FR6)*
2. **Ticket upload.** Matching ticket file attached per claim. *(R2-FR7)*
3. **Injectable browser.** Offline tests use page fixture / recorded HTML without live SWR. *(R2-NFR2)*
4. **Credentials from env.** SWR login credentials never in repo. *(R2-NFR3)*
5. **Confirmation captured.** Returns SWR reference/confirmation text when present. *(R2-FR8)*

## Dev Notes

- New adapter: `trainline/adapters/claim_submission.py` (Playwright)
- Add `playwright` to requirements-dev.txt; document install in QUICKSTART
- `@live` test gated on SWR credentials + network
- Target: https://delayrepay.southwesternrailway.com/ (validate selectors against live form — OQ3)
