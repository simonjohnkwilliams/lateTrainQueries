# Epic 7 close-out — 2026-07-20

**Decision:** Epic 7 **accepted / closed** for Release 3 timer + weekly chain.  
**Owner sign-off:** Simon — Task Scheduler glance OK; digest/ops email path OK; Gmail auth done.  
**Pending human run:** Thursday test ticket photo → Friday `--weekly-ops` / scheduled task (not a blocker to start Epic 8).

## Delivered

| Area | Evidence |
| --- | --- |
| Gmail adapter + auth + FR38 claim-mail characterisation | Story 7.1; `@gmail` live green |
| Digest prefers Gmail API | `cli._maybe_send_digest` |
| Prior-week window (FR33/NFR13) | `schedule_window.prior_working_week` |
| Completion marker (FR39) | `weekly_marker` + `Results/weekly/*.marker` |
| Task Scheduler (FR32/NFR12) | `scripts/weekly_ops.ps1`, `register-weekly-ops-task.ps1`; Friday 18:00 + daily CatchUp 09:30 |
| Weekly chain (FR34) | `python -m trainline --weekly-ops` → assess → classify → file → digest |

## Accepted deferrals (not blocking Epic 8)

| Item | Notes |
| --- | --- |
| Story 7.4 rich Tables 1–2 | Current digest accepted as ops email for now; full Table 1/2 can return as a small follow-up or fold into Epic 8 polish |
| Story 7.5 lifecycle JSON store | FR38 inbox stages characterised; durable Table 2 state deferred until richer ops email returns |
| True At-logon task | Needs Admin; daily CatchUp covers missed-Friday intent |

## Simon’s Friday test (when ready)

1. Thursday: drop ticket photo into `tickets/unclassified/` (or Epic 8 mail-drop once built).
2. Friday (or `Start-ScheduledTask LateTrainQueries-WeeklyOps-Friday`): PC on, Ollama up.
3. Confirm `--weekly-status` → `complete=true`; second run skips.
4. Optional: `--weekly-ops --live-submit` + captcha for a real SWR file.

## Next

**Epic 8 — Phone ticket drop into `unclassified/`** (see `epics.md` Release 4 / Epic 8).
