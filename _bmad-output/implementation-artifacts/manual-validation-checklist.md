# Manual validation checklist — Late Train Query Engine MVP

Generated: 2026-07-15

Use this after the automated suites. Offline/recorded coverage is automated;
items marked **MANUAL** need your eyes (or a live HSP account).

## Prerequisites

- [ ] `pip install -r requirements-dev.txt` (or project equivalent)
- [ ] `creds/trainConfig.txt` exists locally and is **not** committed
- [ ] File starts with:

```ini
[configuration]
username=YOUR_OPEN_RAIL_DATA_EMAIL
password=YOUR_HSP_PASSWORD
```

  Trailing portal notes are ignored by the loader. Only those two keys are used.
- [ ] Optional AVG TLS: `REQUESTS_CA_BUNDLE=creds/ca-bundle.pem`

## A. Automated gate (run these first)

```powershell
# Offline + recorded (default; no network, no secrets)
python -m pytest

# Schema fidelity of committed fixtures vs live contract
python -m pytest tests/test_hsp_schema_fixtures.py -v

# Live smoke (creds + HSP endpoints + schema + live-capture/)
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
if (Test-Path creds\ca-bundle.pem) { $env:REQUESTS_CA_BUNDLE = (Resolve-Path creds\ca-bundle.pem).Path }
python -m pytest -m live -v -o addopts=
```

Expected: offline suite all green. Live suite green **only if** HSP accepts the
`[configuration]` username/password (HTTP 401 means update those two keys —
Darwin/KB keys in the same file are not used).

Live responses are written under `live-capture/` (gitignored). Compare shapes to
`tests/fixtures/recorded_*` and `service_*`.

## B. Epic 1 — Claim engine (**mostly automated**)

| Check | How | Status |
| --- | --- | --- |
| Delay / band / payout | `python -m pytest tests/test_delay.py` | AUTOMATED |
| Optimiser feasibility + tie-break | `python -m pytest tests/test_optimiser.py` (or equivalent) | AUTOMATED |
| Cancellation gate off by default | engine/BDD tests | AUTOMATED |
| **MANUAL** Spot-check one known late day mentally | Pick a day you remember being ≥15 min late; once live CLI works, confirm that day produces a claim row | MANUAL |

## C. Epic 2 — HSP adapter (**offline automated; live below**)

| Check | How | Status |
| --- | --- | --- |
| Metrics body + all RIDs | offline HSP tests | AUTOMATED |
| Details → `Service` mapping | offline + fixture schema tests | AUTOMATED |
| Cache skip-if-present | offline cache tests | AUTOMATED |
| FETCH_FAILED ≠ no-claim | BDD pipeline scenario | AUTOMATED |
| **LIVE** Auth + metrics schema | `pytest -m live` | AUTOMATED (needs valid creds) |
| **LIVE** Details schema + map | `pytest -m live` | AUTOMATED (needs valid creds) |
| **MANUAL** Eyeball `live-capture/*.json` vs `tests/fixtures/` | Same keys: `Services` / `serviceAttributesDetails.locations[*]` fields | MANUAL |

## D. Epic 3 — Config, storage, CLI

| Check | How | Status |
| --- | --- | --- |
| Config defaults GOD↔WAT full-day | `tests/test_config.py` | AUTOMATED |
| Creds from env only | `tests/test_config.py` | AUTOMATED |
| CSV+JSON SWR fields, sort, no £ | `tests/test_storage.py` | AUTOMATED |
| Stubbed week E2E | BDD `claims_pipeline.feature` | AUTOMATED |
| Recorded quiet Thursday → 0 claims | `@recorded` scenario | AUTOMATED |
| Sole orchestrator | `tests/test_cli.py` AST check | AUTOMATED |
| **MANUAL** `python -m trainline --lookback-days 1 --batch-size 1` | With valid `HSP_CREDENTIALS_FILE`; inspect `Results/claims.csv` + summary JSON; confirm FETCH_FAILED days print as "Not analysed" | MANUAL |
| **MANUAL** Open `claims.csv` and verify one row against the SWR form | Date, O→D, times, delay, band | MANUAL |

## E. Residual MANUAL-only (cannot fully automate)

1. SWR website form field parity (OQ3) — compare one claim row to the live filing form.
2. Confirm your Open Rail Data / HSP password actually authenticates (portal account health).
3. Optional: refresh recorded fixtures from a live capture when you want a newer quiet-day baseline.

## Pass criteria for "MVP validated"

- [ ] `python -m pytest` green (offline/recorded)
- [ ] `python -m pytest -m live -o addopts=` green with your creds
- [ ] At least one manual CLI run produces CSV/JSON you trust against SWR
