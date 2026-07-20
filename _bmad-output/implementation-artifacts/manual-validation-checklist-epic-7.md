# Manual validation checklist — Release 3 (Epic 7)

Generated: 2026-07-20 · Epic 7 weekly local ops loop

Run **A. Automated** first. Items marked **MANUAL** need your eyes, Task
Scheduler, or an attended live session. Items marked **LIVE** are pytest opt-in
markers (`@gmail` / `@live` / `@vision`).

## Timer / schedule requirements (yes — first-class)

| ID | Requirement |
| --- | --- |
| **FR32** | Scheduled weekly job on **Friday**, or **next power-on** after a missed Friday |
| **FR33** | Assess window = **prior** Mon–Fri relative to the anchor Friday |
| **FR39** | Re-running the same anchor Friday must **not** duplicate filing / Table 2 paid noise |
| **NFR12** | **Windows Task Scheduler** + PowerShell — no cloud scheduler |
| **NFR13** | Missed-Friday catch-up uses the **same** anchor window (not a new week) |

Story **7.2** owns window math + Task Scheduler script + completion marker.  
Story **7.3** owns the single `--weekly-ops` entrypoint the timer invokes.

## Prerequisites

- [ ] `pip install -r requirements-dev.txt`
- [ ] `creds/trainConfig.txt` with HSP + `## Gmail API ##` (+ token via `--gmail-auth`)
- [ ] Optional AVG: `creds/ca-bundle.pem` (auto-used; no manual env required for Gmail)
- [ ] Ollama + ticket model for classify (attended weekly run)
- [ ] Playwright Chromium for live file (human reCAPTCHA)

## A. Automated gate (run these first)

```powershell
# Offline default — expect green; Epic 7.3–7.5 harness tests SKIP until implemented
python -m pytest -q

# Window math (7.2 AC1–AC2) — must be green now
python -m pytest tests/test_schedule_window.py -q

# Gmail adapter + digest transport + SWR claim mail (7.1)
python -m pytest tests/test_gmail_auth.py tests/test_gmail_client.py tests/test_gmail_config.py `
  tests/test_swr_claim_mail.py tests/test_digest_gmail_transport.py -q
```

Skip-gated offline contracts (activate when stories land):

| File | Story | Activates when |
| --- | --- | --- |
| `tests/test_weekly_marker.py` | 7.2 marker | `trainline.adapters.weekly_marker` |
| `tests/test_weekly_ops_cli.py` | 7.3 chain | `--weekly-ops` in `cli.py` |
| `tests/test_ops_email.py` | 7.4 tables | `trainline.adapters.ops_email` |
| `tests/test_claim_lifecycle.py` | 7.5 store | `trainline.adapters.claim_lifecycle` |

## B. LIVE automated (opt-in) — run for confirmation

```powershell
$env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\trainConfig.txt).Path
if (Test-Path creds\ca-bundle.pem) {
  $env:REQUESTS_CA_BUNDLE = (Resolve-Path creds\ca-bundle.pem).Path
}

# Gmail inbox stages for characterised claim (FR38) + send smoke
python -m pytest -m gmail -v -o addopts=

# Optional HSP / SMTP legacy
python -m pytest -m live -v -o addopts=
```

| Check | Command / test | Status |
| --- | --- | --- |
| SWR inbox RECEIVED / Approved / PAYMENT SENT | `test_live_gmail_claim_mail.py` | LIVE `@gmail` |
| Gmail API send one-liner to DIGEST_TO | `test_live_gmail_digest_send.py` | LIVE `@gmail` |
| HSP smoke | `pytest -m live` | LIVE |
| Ops email live send (Tables 1–2) | *after 7.4* | LIVE TBD |
| Full `--weekly-ops` dry (FakeBrowser) | *after 7.3* | LIVE/offline TBD |

## C. MANUAL sign-off (cannot fully automate)

### C1. Task Scheduler (FR32, NFR12) — **close-out**

**Already automated on this machine (2026-07-20):**

| Task | Schedule | State |
| --- | --- | --- |
| `LateTrainQueries-WeeklyOps-Friday` | Weekly Friday **18:00** | Registered |
| `LateTrainQueries-WeeklyOps-CatchUp` | Daily **09:30** (missed-Friday catch-up; no-ops when marker present) | Registered |

Scripts: `scripts/weekly_ops.ps1`, `scripts/register-weekly-ops-task.ps1`  
CLI: `python -m trainline --weekly-ops` / `--weekly-status`  
Marker: `Results/weekly/weekly-complete-YYYY-MM-DD.marker` (FR39)

True **At log on** needs an elevated Admin shell (`-PreferLogon`); daily catch-up covers the same FR32 intent without admin.

**What you still need to do:**

1. **Confirm tasks in UI or PowerShell**
   ```powershell
   Get-ScheduledTask -TaskName 'LateTrainQueries-WeeklyOps-*' | Format-Table TaskName, State
   ```
2. **Optional — change times** (then re-register):
   ```powershell
   .\scripts\register-weekly-ops-task.ps1 -At 19:00 -CatchUpAt 08:00
   ```
3. **First real run when ready** (Ollama up; FakeBrowser file — no captcha):
   ```powershell
   Start-ScheduledTask -TaskName 'LateTrainQueries-WeeklyOps-Friday'
   # or: python -m trainline --weekly-ops
   python -m trainline --weekly-status   # expect complete=true after success
   python -m trainline --weekly-ops      # expect skip / already complete
   ```
4. **Catch-up smoke (without waiting for a missed Friday):** delete the marker for the current anchor, then run CatchUp once:
   ```powershell
   python -m trainline --weekly-status
   # note marker_path, then:
   Remove-Item -LiteralPath (python -m trainline --weekly-status | ConvertFrom-Json).marker_path -ErrorAction SilentlyContinue
   Start-ScheduledTask -TaskName 'LateTrainQueries-WeeklyOps-CatchUp'
   ```
5. **Sign-off FR32:** after one successful Friday (or CatchUp) run, tick this epic item. Optional later: leave PC off over a Friday and confirm CatchUp next morning still uses the **prior** Mon–Fri window.

### C2. First-time Gmail OAuth (FR40) — **done / good to go**

### C3. Attended weekly dry-run — **good to go when you want**

```powershell
python -m trainline --weekly-ops
# Re-run should no-op via marker:
python -m trainline --weekly-ops
```

### C4. Attended weekly live file (OQ4 / reCAPTCHA) — after you want a real submit

```powershell
.\scripts\weekly_ops.ps1 -LiveSubmit
# or: python -m trainline --weekly-ops --live-submit --weekly-ops-force
```

### C5. Ops email eyeball (FR36–FR38) — after 7.4 / 7.5

1. Open the ops email in DIGEST_TO inbox.
2. **Table 1:** late trains, matched tickets, rejects (reason + path), newly filed / open.
3. **Table 2:** follow-up statuses; `Approved` does **not** omit; only after **PAYMENT SENT** was reported in a prior digest is the claim omitted next week.
4. Confirm no placeholder subject matchers — real SWR subjects only.

### C6. Secrets / git hygiene

- [ ] `creds/`, `gmail_token.json`, `Results/`, lifecycle JSON never committed
- [ ] Real `ticket_price` / `ticket_reference` set before live file (open Epic 6 action)

## D. Story readiness map

| Story | Spec file | Offline automation now | Implement next |
| --- | --- | --- | --- |
| 7.1 Gmail adapter | `7-1-…md` | **Green** (review) | Code review |
| 7.2 Window + scheduler | `7-2-…md` | Window **green**; marker/PS **skip** | Marker + `.ps1` + Task Scheduler |
| 7.3 Weekly chain | `7-3-…md` | **Skip** harness ready | `--weekly-ops` |
| 7.4 Ops tables | `7-4-…md` | **Skip** harness ready | `ops_email` renderer |
| 7.5 Lifecycle | `7-5-…md` | **Skip** harness ready | `claim_lifecycle` store |

## Pass criteria for Epic 7

- [ ] `python -m pytest` green (offline); skip-gated files green once stories land
- [ ] `pytest -m gmail` green (inbox stages + send smoke)
- [ ] Task Scheduler Friday + logon catch-up verified once (C1)
- [ ] One attended `--weekly-ops` dry-run with correct prior-week window (C3)
- [ ] Ops email Tables 1–2 eyeballed (C5)
- [ ] Re-run same anchor Friday is idempotent (marker + Table 2 omit paid)
