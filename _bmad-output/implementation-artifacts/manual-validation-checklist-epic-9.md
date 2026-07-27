# Manual validation — Epic 9 claim follow-up (2026-07-27)

Run after the automated gate is green. Offline suite already passes
(`477 passed, 75 deselected` — the `75 deselected` are the live `@gmail`
tests below).

## A. Automated (already done by agent)

```powershell
cd C:\Users\simon\IdeaProjects\lateTrainQueries
python -m pytest -q
```
Expect 477 passed, 75 deselected. If any fail, stop.

## B. Confirm the lifecycle contract holds on a real store (you, ~2 min)

This is the one piece the unit tests can't prove on its own — exercise the
real file path and re-load it:

```powershell
# Seed a fake-but-well-formed lifecycle, then verify monotonicity + reload
notepad Results\claim-lifecycle.json
# paste (or just look — Story 9.1 already enforces the shape on any write):
# {
#   "SWR-0218-108-579": {
#     "claim_id": "SWR-0218-108-579",
#     "status": "submitted",
#     "date": "2026-07-10",
#     "direction": "outbound",
#     "updated_at": "2026-07-27T12:00:00Z",
#     "amount_gbp": null,
#     "reported_paid_at": null
#   }
# }

python -c "from trainline.adapters.claim_lifecycle import LifecycleStore; \
  s=LifecycleStore('Results/claim-lifecycle.json'); \
  print([r.claim_id, r.status] for r in s.all())"
```

Expect one row, status `submitted`. Delete the file before continuing if you
don't want a stale seed (a real `--file --live-submit` will recreate it).

## C. Live Gmail refresh against the known claim (you, ~1 min, opt-in)

The only live Gmail path in Epic 9 is the refresh search — it reuses the
parser already characterised in Epic 7. Confirm it advances the seeded row:

```powershell
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
python -c "from trainline import cli; \
  cli._refresh_claim_lifecycle( \
    lifecycle_path='Results/claim-lifecycle.json', \
    credentials_path=$env:HSP_CREDENTIALS_FILE)"
type Results\claim-lifecycle.json
```

Expect `SWR-0218-108-579` to advance from `submitted` toward `paid`
(depending on which stage emails have actually arrived — RECEIVED / Approved
/ PAYMENT SENT are all live for that claim per `epic-7-fr38-inbox-contract`).

If you see `Lifecycle refresh skipped: Gmail not configured` → re-run
`python -m trainline --gmail-auth` (the token or `## Gmail API ##` keys are
missing). That is a warning, not a failure — refresh is best-effort by design.

## D. Table 2 render in a real ops email (you, ~2 min, no send)

The dry-run sink exercises the full Table 2 build path without sending mail:

```powershell
$env:TRAINLINE_OPS_EMAIL_FILE = (Resolve-Path .\Results).Path + "\ops-email-dry.txt"
# (with the lifecycle file from step B/C still present)
python -c "from trainline import cli; \
  rc, paid = cli._run_weekly_ops_email( \
    day_results=[], credentials_path=$env:HSP_CREDENTIALS_FILE, \
    strict=False, filing_summary={}, anchor_friday='2026-07-31', \
    out_dir='Results'); \
  print('rc=', rc, 'paid_ids=', paid)"
type Results\ops-email-dry.txt
```

Expect the email body to contain a **Table 2 — follow-up** section listing
`SWR-0218-108-579` with its current status (`in_flight` if still
`submitted`, else `received` / `approved` / `paid`). If the row is `paid`,
the printed `paid_ids` list should contain `['SWR-0218-108-579']`.

## E. Full Friday chain end-to-end (optional, deferred to your Friday sign-off)

Story 9.2's seeding (`record_submitted`) only fires on a **real** live
`--file --live-submit`, which needs the human reCAPTCHA gate (OQ4) — there is
no unattended way to verify it in isolation. The next time you do a real
filing, then run `--weekly-ops`, confirm:

```powershell
python -m trainline --weekly-ops --live-submit
# solve captcha when prompted; let it finish
type Results\claim-lifecycle.json       # newly-filed claim appears as submitted
python -m trainline --weekly-status     # complete=true
```

The next Friday after a paid claim has been reported, re-run `--weekly-ops`
and confirm that paid claim is **absent** from Table 2 (it was just marked
`reported_paid_at` by the prior run).

## F. Don't need to verify

- 9.1 store monotonicity — covered by `tests/test_claim_lifecycle.py` (14 cases).
- 9.2 fake-ref / captcha-abandon skip paths — covered by `tests/test_file_cli.py`.
- 9.3 search-failure warn-and-continue — covered by `tests/test_lifecycle_refresh_cli.py`.
- 9.4 chain order, mark-after-send, email-failure-doesn't-mark — covered by `tests/test_table2_cli.py` + `tests/test_weekly_ops_cli.py`.

## Pass criteria for Epic 9

- [ ] Offline suite green (A)
- [ ] Lifecycle file loads + shows the expected row (B)
- [ ] Live Gmail refresh advances a seeded claim, or warns cleanly when not configured (C)
- [ ] Dry-run ops email contains a Table 2 section for the seeded claim (D)
- [ ] (Optional, next real Friday) `--weekly-ops --live-submit` produces a `submitted` row; the following Friday omits paid rows already reported (E)
