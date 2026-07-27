# Deferred work

## Deferred from: code review of 9-1-claim-lifecycle-store.md (2026-07-27)

- Non-atomic JSON rewrite / concurrent writers for `Results/claim-lifecycle.json` — same DropHashStore-style full rewrite; fine for solo local runs until concurrency appears.
- One corrupt lifecycle row fails the entire store load — align with other Results JSON loaders; consider skip-bad-row later if needed.
- Sticky `failed` claims remain in `open_for_table2()` forever — product exit path (omit/hide) deferred to Story 9.4 or later.
