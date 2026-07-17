# Manual validation checklist — Late Train Query Engine MVP

Generated: 2026-07-16

Use this after the automated suites. Offline/recorded coverage is automated;
items marked **MANUAL** need your eyes (or a live HSP / Ollama session).

## Prerequisites

- [ ] `pip install -r requirements-dev.txt`
- [ ] Ollama running locally with `trainline-ticket` (or `qwen2.5vl:7b`)
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

# Live HSP smoke (creds + HSP endpoints + schema + live-capture/)
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
if (Test-Path creds\ca-bundle.pem) { $env:REQUESTS_CA_BUNDLE = (Resolve-Path creds\ca-bundle.pem).Path }
python -m pytest -m live -v -o addopts=

# Live Ollama vision smoke (GPU + model)
python -m pytest -m vision -v -o addopts=

# Full golden vision quality gate (all accept + reject photos)
$env:TRAINLINE_VISION_GATE = "1"
python -m pytest
# or: python -m pytest --vision-gate
```

Expected: offline suite all green. Live / vision suites green only when HSP
creds and Ollama+model are healthy.

## B. Epic 1 — Claim engine (**mostly automated**)

| Check | How | Status |
| --- | --- | --- |
| Delay / band / payout | `python -m pytest tests/test_delay.py` | AUTOMATED |
| Optimiser feasibility + tie-break | optimiser / BDD tests | AUTOMATED |
| Cancellation gate off by default | engine/BDD tests | AUTOMATED |
| **MANUAL** Spot-check one known late day | Pick a day you remember being ≥15 min late; confirm that day produces a claim row | MANUAL |

## C. Epic 2 — HSP adapter (**offline automated; live below**)

| Check | How | Status |
| --- | --- | --- |
| Metrics / details / cache / FETCH_FAILED | offline HSP + BDD tests | AUTOMATED |
| **LIVE** Auth + metrics/details schema | `pytest -m live` | AUTOMATED (needs creds) |
| **MANUAL** Eyeball `live-capture/*.json` vs `tests/fixtures/` | Same keys: `Services` / `serviceAttributesDetails.locations[*]` | MANUAL |

## D. Epic 3 — Config, storage, CLI

| Check | How | Status |
| --- | --- | --- |
| Config / storage / stubbed week / recorded quiet day | offline + BDD | AUTOMATED |
| **MANUAL** `python -m trainline --lookback-days 1 --batch-size 1` | With valid `HSP_CREDENTIALS_FILE`; inspect `Results/claims.csv` + summary JSON; confirm FETCH_FAILED days print as "Not analysed" | MANUAL |
| **MANUAL** Open `claims.csv` and verify one row against the SWR form | Date, O→D, times, delay, band | MANUAL |

## E. Epic 5 / 5b — Ticket gate + Ollama classify

| Check | How | Status |
| --- | --- | --- |
| Parser / golden FakeOcr classify / reject negatives | offline pytest | AUTOMATED |
| Vision JSON helpers | offline `tests/test_ollama_vision.py` | AUTOMATED |
| Vision golden quality gate (all accept+reject) | `pytest --vision-gate` or `TRAINLINE_VISION_GATE=1` | AUTOMATED (needs Ollama) |
| **MANUAL** Classify a small inbox of real photos | Copy 5–10 tickets into `tickets/unclassified/`; run `python -m trainline --classify-tickets`; confirm ready vs rejected | MANUAL |
| **MANUAL** Spot-check renamed ready files | Filename `MM-DD-…` matches printed journey/start date; route is GOD↔London | MANUAL |
| **MANUAL** Confirm rejects are correct | Wrong route / receipt / voucher / multi-ticket / unreadable land under `processed/rejected/` with sensible prefixes | MANUAL |
| **MANUAL** `--check-tickets` after assess | With `Results/claims.json` present, confirm gate reports missing tickets honestly | MANUAL |

## F. Residual MANUAL-only (cannot fully automate)

1. SWR website form field parity (OQ3) — compare one claim row to the live filing form.
2. Confirm your Open Rail Data / HSP password actually authenticates.
3. Optional: refresh recorded fixtures from a live capture when you want a newer quiet-day baseline.
4. Broader vision regression: run classify over the full golden accept/reject set and note any date/route mismatches (not yet a full automated suite).

## Pass criteria for "MVP validated"

- [ ] `python -m pytest` green (offline/recorded)
- [ ] `python -m pytest -m live -o addopts=` green with your creds
- [ ] `python -m pytest --vision-gate` (or `TRAINLINE_VISION_GATE=1`) green with Ollama
- [ ] At least one manual CLI assess run produces CSV/JSON you trust against SWR
- [ ] At least one manual `--classify-tickets` run on real photos looks correct
