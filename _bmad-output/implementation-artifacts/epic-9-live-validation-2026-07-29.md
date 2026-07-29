# Epic 9 — live validation against real claims (2026-07-29)

Real-world confirmation of the Story 9.1–9.4 claim follow-up path, run
against the two claims actually filed live on Monday 2026-07-27 (not the
fictitious `SWR-0218-108-579` seed used in
`manual-validation-checklist-epic-9.md`).

## Claims under test

From `Results/filing-audit.jsonl` (real live `--file --live-submit`, 2026-07-27):

| Claim ID | Direction | Journey date | Filed at |
| --- | --- | --- | --- |
| `SWR-1316-710-286` | outbound | 2026-07-24 | 2026-07-27T10:34:21Z |
| `SWR-1141-527-492` | inbound | 2026-07-24 | 2026-07-27T10:35:49Z |

`Results/claim-lifecycle.json` did not contain rows for either claim as of
2026-07-29 — the live filing run predates/missed the Story 9.2
`record_submitted` wiring. Backfilled both as `submitted` via
`LifecycleStore.record_submitted` to match what the pipeline should have
recorded at filing time.

## Blocker hit + fixed: AVG root cert had rotated

Live Gmail refresh initially failed with
`SSL: CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate`
calling `googleapis.com` — **not** a network outage (confirmed reachable
with verification disabled). `creds/ca-bundle.pem`'s embedded AVG root
(exported 2026-06-11) no longer matched AVG's current interception cert
(HSP's rail-data domain still validated fine with the same bundle — AVG
had rotated the cert since, and the old one just hadn't been exercised
against `googleapis.com` since).

Fix: re-ran `creds/export-avg-root.ps1` (new thumbprint
`E68874DBA3BA5DB2DF70E140ED1F6C941459BF33`), replaced the stale AVG cert
block at the tail of `creds/ca-bundle.pem` with the fresh export. Live
Gmail calls succeeded immediately after.

## Live Gmail refresh result

Both claims advanced all the way to `paid` — the real RECEIVED / Approved
/ PAYMENT SENT emails in-inbox all parsed correctly against the FR38
subject contract characterised in
`epic-7-fr38-inbox-contract-2026-07-20.md`. No parser gap found.

```json
{
  "SWR-1141-527-492": {
    "claim_id": "SWR-1141-527-492",
    "status": "paid",
    "date": "2026-07-24",
    "direction": "inbound",
    "updated_at": "2026-07-29T08:25:32.684155Z",
    "amount_gbp": null,
    "reported_paid_at": null
  },
  "SWR-1316-710-286": {
    "claim_id": "SWR-1316-710-286",
    "status": "paid",
    "date": "2026-07-24",
    "direction": "outbound",
    "updated_at": "2026-07-29T08:25:33.396866Z",
    "amount_gbp": null,
    "reported_paid_at": null
  }
}
```

## Dry-run ops email (Table 2) — `Results/ops-email-dry-2026-07-29.txt`

Generated via `_run_weekly_ops_email` with `TRAINLINE_OPS_EMAIL_FILE` sink
(no send; `Results/` is gitignored so the file itself isn't tracked — this
doc is the durable record of its content):

```
Subject: Delay Repay weekly ops — 2026-07-31 (filed 0, claimable 0)

Delay Repay weekly ops — 2026-07-31

No claimable rows found.

Newly filed this run:
  (none)

Skipped (no ticket for claim date):
  (none)

Tickets with no matching late trains:
  (none)

Table 2 — follow-up (prior claims):
  2026-07-24 SWR-1141-527-492 paid
  2026-07-24 SWR-1316-710-286 paid
```

`paid_ids` returned by the call: `['SWR-1141-527-492', 'SWR-1316-710-286']`.
`mark_reported_paid` was **not** invoked here (this was a dry-run, not a
real send) — both rows remain open in Table 2 with `reported_paid_at:
null`. The real Friday `--weekly-ops` chain will mark them after it
actually sends.

## Gap found + fixed: claim-status mail was never filed

`_refresh_claim_lifecycle` (Story 9.3) only ever searched + read claim-status
mail — it never labelled or archived it, unlike ticket-ingest mail
(`trainline-ticket-ingested`). Sign-off required this to actually happen, so
it was added: `trainline/cli.py` now calls `ensure_label_id` /
`modify_message` (label `trainline-claim-processed`, remove
`INBOX`/`UNREAD`) for every message that successfully advances a claim's
lifecycle stage, mirroring the ticket-ingest pattern exactly
(`_ingest_from_gmail_client`, `trainline/cli.py:1317+`) — best-effort and
scope-tolerant via `getattr`/`_is_insufficient_gmail_scope` so minimal test
doubles and missing-scope tokens don't break. Three new offline tests added
to `tests/test_lifecycle_refresh_cli.py` (files on advance, doesn't file on
unknown stage, missing-scope still advances lifecycle without filing). Full
offline suite: 480 passed, 75 deselected.

Verified live: after re-running the refresh, all 6 real messages (3 stages ×
2 claims) now carry the `trainline-claim-processed` label and are out of
`INBOX`/`UNREAD` (confirmed via `list_labels` + `search_messages` against
the real inbox).

## Real send (not dry-run)

Ran `_run_weekly_ops_email` for real (no `TRAINLINE_OPS_EMAIL_FILE` sink) —
sent to `simonjohnkwilliams@gmail.com` via the Gmail API digest transport.
Then called `_mark_paid_reported_after_email` for both claim ids (mirroring
what the real `--weekly-ops` chain does immediately after a send), so
`reported_paid_at` is now stamped on both rows in
`Results/claim-lifecycle.json` — they will correctly drop out of Table 2 on
the next run.

## Outcome

- [x] Lifecycle store backfilled with the two real filed claims
- [x] Live Gmail refresh advances real claims through received → approved → paid
- [x] Dry-run ops email renders Table 2 correctly for real claims
- [x] AVG cert rotation issue found and fixed (`creds/ca-bundle.pem` refreshed)
- [x] Claim-status mail filing implemented (was missing), tested offline, verified live
- [x] Real ops status email sent to the user's own inbox; paid rows marked reported
- Open note: confirm on the next real `--weekly-ops` run that Story 9.2's
  `record_submitted` fires automatically on live filing going forward —
  this run needed a manual backfill, which shouldn't be necessary if 9.2
  is wired correctly on the code version used for filing.
