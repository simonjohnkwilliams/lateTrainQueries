# Ticket fixtures for OCR / intake tests

Committed samples:

- Positive GOD↔London candidates + wrong-route + blank (legacy)
- **`date_cases/`** — ground-truth photos for APTIS date parsing
  - `expected.json` — visual inspection truth (journey / start / valid-until)
  - Months use APTIS codes: **JNR**=Jan, **FBY**=Feb, **MCH**=Mar, **JLY**=Jul, **DMR**=Dec

Full dump lives in `sample-tickets/` (gitignored).

Runtime tree (also gitignored):

```
tickets/unclassified/
tickets/processed/ready_to_claim/
tickets/processed/rejected/
tickets/claimed/
```

**Important:** Phone capture stamps (`YYYYMMDD_HHMMSS`) are *not* journey dates.
The wrong `01-31-*.jpg` ready names came from Galaxy filenames, not ticket print.
