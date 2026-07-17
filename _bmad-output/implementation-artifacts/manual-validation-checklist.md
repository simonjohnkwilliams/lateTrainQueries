# Manual validation checklist — Release 2 (Epics 4–6)

Generated: 2026-07-17 · Branch: `release-2`

Run the automated suites first. Items marked **MANUAL** need your eyes or a live
HSP / Ollama / SWR session. Everything else below is already covered by pytest.

## Prerequisites

- [ ] On branch `release-2` (`git branch --show-current`)
- [ ] `pip install -r requirements-dev.txt`
- [ ] Optional live SWR: `playwright install chromium`
- [ ] Ollama running with `trainline-ticket` (or `qwen2.5vl:7b`) for classify / vision gate
- [ ] `creds/trainConfig.txt` exists locally and is **not** committed
- [ ] Optional AVG TLS: `REQUESTS_CA_BUNDLE=creds/ca-bundle.pem`

## A. Automated gate (run these first)

```powershell
# Offline + recorded (default; no network, no secrets) — expect all green
python -m pytest

# Live HSP smoke
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
if (Test-Path creds\ca-bundle.pem) { $env:REQUESTS_CA_BUNDLE = (Resolve-Path creds\ca-bundle.pem).Path }
python -m pytest -m live -v -o addopts=

# Live Ollama vision smoke
python -m pytest -m vision -v -o addopts=

# Full golden vision quality gate
$env:TRAINLINE_VISION_GATE = "1"
python -m pytest
```

## B–E. Earlier epics (automated unless noted)

| Area | Status |
| --- | --- |
| Epic 1 engine / Epic 2 HSP offline / Epic 3 CLI / Epic 4 digest offline | AUTOMATED |
| Epic 5 gate + Epic 5b FakeOcr classify | AUTOMATED |
| **MANUAL** Spot-check one known late day in `claims.csv` | MANUAL |
| **MANUAL** Classify 5–10 real photos with `--classify-tickets` | MANUAL |
| **LIVE** `pytest -m live` + `pytest --vision-gate` | AUTOMATED (needs creds / Ollama) |

## F. Epic 6 — SWR auto-file (**mostly automated offline**)

| Check | How | Status |
| --- | --- | --- |
| CRS → station + cancel/delay reason mapping | `tests/test_swr_mapping.py` | AUTOMATED |
| Fake browser fill + JSONL audit + batch continue-on-fail | `tests/test_claim_submission.py` | AUTOMATED |
| `--file` happy path (fake browser, audit, move to claimed, digest) | `tests/test_file_cli.py` + BDD `file_pipeline.feature` | AUTOMATED |
| `--file` gate blocks submit; claims still written | same | AUTOMATED |
| Default assess (no `--file`) does not submit | same | AUTOMATED |
| **MANUAL** Dry-run `--file` on a real week (FakeBrowser) | See steps below | MANUAL |
| **MANUAL / LIVE** SWR form field parity + `--live-submit` (OQ3/OQ4) | See steps below | MANUAL |

### MANUAL — dry-run `--file` (FakeBrowser, safe)

1. Assess + classify so `Results/claims.json` and `tickets/processed/ready_to_claim/` align for the week.
2. Run:
   ```powershell
   python -m trainline --file --from-date YYYY-MM-DD --to-date YYYY-MM-DD --digest
   ```
3. Confirm stderr mentions `FakeBrowserSession`, stdout filing summary has `filed` ≥ 1, `Results/filing-audit.jsonl` has success lines, and matching tickets moved to `tickets/claimed/`.
4. Confirm a second `--file` on the same week skips already-claimed dates.

### MANUAL — live SWR (OQ3 / OQ4; do not leave unattended yet)

1. `playwright install chromium`
2. Put SWR login details only in env / password manager — never in the repo.
3. Run one claim with:
   ```powershell
   python -m trainline --file --live-submit --from-date YYYY-MM-DD --to-date YYYY-MM-DD
   ```
4. Watch the browser: journey date, stations, times, delay reason, ticket upload match `claims.csv`.
5. Note whether login / 2FA blocks unattended runs (OQ4). Current live path **fills** the form but does **not** auto-click Submit until OQ4 is resolved.

## G. Residual MANUAL-only (cannot fully automate)

1. **OQ3** — Confirm live SWR Delay Repay field labels/selectors match our mapping (update Playwright selectors if the site differs).
2. **OQ4** — Decide session persistence / 2FA strategy before enabling unattended Submit.
3. Confirm HSP password authenticates (`pytest -m live`).
4. Eyeball one real `--classify-tickets` batch (ready vs rejected).
5. Optional: refresh recorded HSP fixtures from a newer live capture.

## Pass criteria for Release 2 Epic 6 on `release-2`

- [ ] `python -m pytest` green (offline)
- [ ] Dry-run `--file` produced a trusted audit + moved tickets
- [ ] At least one manual compare of a claim row to the live SWR form (OQ3)
- [ ] OQ4 notes captured (2FA / session) before enabling auto-Submit
