---
baseline_commit: 39617cf25ea411e81e34921380a255764ea8c406
---
# Story 6.1: SWR field mapping at submit time

Status: done

## Story

As Simon,
I want CRS codes and HSP reasons mapped to SWR form values during submission,
so that auto-filled forms match what the site expects (OQ3).

## Acceptance Criteria

1. **CRS → station name.** WAT → London Waterloo; GOD → Godalming. Extensible dict in config. *(R2-FR6, OQ3)*
2. **Delay reason category.** Cancelled row → "Train cancelled"; actual-late → "Delayed en route".
3. **Raw reason preserved.** HSP `late_canc_reason` code kept for audit, not sent as form value.
4. **Pure function.** `map_claim_for_swr(claim) -> SwrFormFields` — no browser imports; unit-tested offline.

## Dev Notes

- `trainline/adapters/swr_mapping.py` or inside `claim_submission.py` as pure helpers
- Reference PRD OQ3 table and retro action item #2
- Does not change CSV output (mapping at submit time only — per discovery)
