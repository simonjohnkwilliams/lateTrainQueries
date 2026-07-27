# Brownfield Reality-Check — Stack, Structure & Release-6 Claims

**Date:** 2026-07-27  
**Reviewer:** automated repo inspection (not memory)  
**Target:** `../ARCHITECTURE-SPINE.md` — Stack table, Structural Seed, AD-18–AD-21  
**Method:** filesystem walk of `trainline/`, read `requirements-dev.txt`, `pip show` on dev machine, pytest spot-check, grep for lifecycle wiring in `cli.py`

---

## Executive verdict

**PARTIALLY ALIGNED.** The hexagonal package layout, engine purity, and Releases 1–5 substrate described in the spine **match the brownfield repo**. Stack floors are mostly sane but **incomplete** (missing Gmail/OCR/PDF deps) and **drift** exists between the spine and `requirements-dev.txt` on `requests`. Release-6 decisions AD-18–AD-21 correctly describe **target architecture**; only **`gmail.claim_mail` and a partial `ops_email`** are shipped — **`claim_lifecycle` is seed-only** and the weekly chain **does not yet** include lifecycle refresh or Table 2 composition.

---

## Stack table vs repo

### As written in spine (lines 168–176)

| Name | Version (spine) |
| --- | --- |
| Python | 3.10+ (dev on 3.12) |
| requests | >=2.31 |
| pytest | >=7.0 |
| pytest-bdd | >=7.0 |
| playwright | >=1.40 (Release 2 — claim submission) |

### As found in repo

| Name | `requirements-dev.txt` | Installed (dev, 2026-07-27) | Verdict |
| --- | --- | --- | --- |
| Python | *(not pinned)* | **3.12.4** | **OK** — spine floor 3.10+ matches `docs/QUICKSTART.md` and dev runtime; prior review's 3.8+ flag was already fixed in spine |
| requests | `>=2.25` | **2.33.1** | **DRIFT** — spine says `>=2.31`; repo pin still `>=2.25`. Installed version satisfies spine; file does not |
| pytest | `>=7.0` | **9.0.3** | **OK** — floor valid; major 9.x requires Python ≥3.10 (consistent with spine floor) |
| pytest-bdd | `>=7.0` | **8.1.0** | **OK** |
| playwright | `>=1.40` | **1.61.0** | **OK** — `trainline/adapters/claim_submission.py` present |

### Shipped deps **missing from spine Stack table**

These appear in `requirements-dev.txt` and are exercised by shipped adapters; the spine Stack table is **incomplete**:

| Name | Floor in `requirements-dev.txt` | Used by (verified) | Verdict |
| --- | --- | --- | --- |
| google-api-python-client | >=2.100 | `trainline/adapters/gmail/client.py` | **GAP** — should be listed (Gmail adapter, FR32–FR40) |
| google-auth-oauthlib | >=1.2 | `trainline/adapters/gmail/auth.py` | **GAP** |
| google-auth | >=2.23 | Gmail auth/client | **GAP** |
| google-auth-httplib2 | >=0.2.0 | Gmail transport | **GAP** |
| httplib2 | >=0.22 | Gmail transport | **GAP** |
| Pillow | >=10.0 | ticket/OCR paths (`ollama_vision`, intake) | **GAP** — Releases 4–5 shipped |
| pdfplumber | >=0.11 | `trainline/booking_pdf.py` | **GAP** — booking PDF ingest shipped |

Installed on dev machine: google-api-python-client 2.198.0, google-auth 2.56.0, Pillow 12.2.0, pdfplumber 0.11.9 — all well above floors. **Version floors themselves are unverified against PyPI EOL** in this pass; only repo presence was checked.

### Prior review superseded items

`reviews/review-versions.md` (2026-07-14) flagged Python 3.8+ and requests `>=2.25`. Spine now reads **3.10+** and **requests >=2.31** — spine fixed, **`requirements-dev.txt` not yet bumped** for requests.

---

## Structural seed vs filesystem

### Spine seed — confirmed present

| Spine path | Repo | Status |
| --- | --- | --- |
| `trainline/engine/models.py` | ✓ | Shipped |
| `trainline/engine/delay.py` | ✓ | Shipped |
| `trainline/engine/optimiser.py` | ✓ | Shipped |
| `trainline/adapters/hsp_client.py` | ✓ | Shipped |
| `trainline/adapters/storage.py` | ✓ | Shipped |
| `trainline/adapters/config.py` | ✓ | Shipped |
| `trainline/adapters/notification.py` | ✓ | Shipped |
| `trainline/adapters/ticket_gate.py` | ✓ | Shipped |
| `trainline/adapters/swr_mapping.py` | ✓ | Shipped |
| `trainline/adapters/claim_submission.py` | ✓ | Shipped (Playwright) |
| `trainline/adapters/ops_email.py` | ✓ | **Partial** — see below |
| `trainline/adapters/gmail/` | ✓ | Shipped (`auth`, `client`, `claim_mail`, `ticket_mail`, `errors`) |
| `trainline/cli.py` | ✓ | Shipped |
| Legacy `TrainLine/TestFileGenerator.py` | absent | **OK** — AD-7 greenfield replacement done |

Hexagonal import-boundary tests (`tests/test_import_boundaries.py`) pass on the engine/adapters layout; AD-1/AD-2 substrate is real, not aspirational.

### Spine seed — **not present (seed / Release 6)**

| Spine path | Repo | Status |
| --- | --- | --- |
| `trainline/adapters/claim_lifecycle.py` | **missing** | **SEED ONLY** — glob returns 0 files |
| `Results/claim-lifecycle.json` | not created at runtime | Expected until adapter lands |

Evidence:

- `tests/test_claim_lifecycle.py` — every test uses `pytest.importorskip("trainline.adapters.claim_lifecycle", reason="Story 7.5 claim_lifecycle not implemented yet")`; **8 skipped** on spot run.
- `grep` over `trainline/` for `record_submitted`, `apply_stage`, `lifecycle_refresh`, `claim_lifecycle` — **no matches**.
- Story spec: `_bmad-output/implementation-artifacts/7-5-claim-lifecycle-state.md` still open.

**Minor path naming drift:** AD-18 default path is `Results/claim-lifecycle.json` (hyphen); story/tests use `claim_lifecycle.json` (underscore). Pick one before implementation.

### Shipped adapters **omitted from Structural Seed** (brownfield richer than diagram)

These exist under `trainline/adapters/` or package root but are absent from the spine tree (lines 180–200):

| Module | Role | In capability map? |
| --- | --- | --- |
| `ticket_intake.py` | OCR/classify pipeline | FR41–FR45 (via ingest) |
| `ticket_drop.py` | Dedup/hash for ticket drop | Epic 8 |
| `ticket_quality.py` | Ticket quality gates | Epic 5b |
| `schedule_window.py` | Anchor Friday / working week | FR32–FR34 |
| `weekly_marker.py` | FR39 completion marker | FR32–FR34 |
| `ollama_vision.py` + `ollama/` | Local vision OCR | Releases 4–5 |
| `trainline/booking_pdf.py` | SWR booking PDF parse | FR41–FR45 |

The seed diagram understates shipped surface area; consider expanding the tree or adding a “Release 4–5 extensions” subsection so the spine matches brownfield.

---

## Release-6 claims: `claim_lifecycle` vs `ops_email` vs `gmail.claim_mail`

### `gmail.claim_mail` — **shipped and tested**

- File: `trainline/adapters/gmail/claim_mail.py` (~200 lines).
- Exports: `ClaimMailStage`, `SwrClaimMail`, `parse_swr_claim_mail`, `parse_gmail_message`, etc.
- Characterised from live inbox (claim `SWR-0218-108-579`).
- Tests: `tests/test_swr_claim_mail.py` — **passing**; `tests/test_live_gmail_claim_mail.py` — `@gmail` gated live.
- **Pure parse** — no Gmail client import inside `claim_mail.py` (AD-19 compliant at parse layer).

### `ops_email` — **partially shipped**

- File: `trainline/adapters/ops_email.py` exists.
- `render_ops_email(..., table2=...)` **does** accept Table 2 and renders a section when non-empty (AD-20 renderer claim is **true**).
- Module docstring (line 3): *"Table 2 (claim lifecycle follow-up, FR37) is deferred to a later epic."*
- `cli._run_weekly_ops_email` always passes **`table2=None`** (line 1075); comment: *"Table 2 deferred."*
- Tests: Table 1 tests **pass**; Table 2 tests **explicitly skipped** (`pytest.skip("Table 2 deferred to next epic")`).
- **No Gmail import** in module — AD-2 satisfied (`test_ops_email_module_does_not_import_gmail`).

**Conclusion:** `ops_email` is **not** seed — it is **Table-1-complete, Table-2-renderer-ready, integration-pending**.

### `claim_lifecycle` — **seed only**

- No module file.
- No CLI mutation hooks (`record_submitted`, `apply_stage`).
- No `claim-lifecycle.json` / `claim_lifecycle.json` store.
- Tests written TDD-style but **all skip** until module lands.

---

## AD-18–AD-21 vs `cli` weekly chain

| AD | Spine rule | Brownfield `cli` | Match? |
| --- | --- | --- | --- |
| AD-18 | Mutable status store in `claim_lifecycle` | Module absent | **NO** — target |
| AD-19 | Only `cli` mutates lifecycle; Gmail → parse → `apply_stage` | No lifecycle calls | **NO** — target |
| AD-20 | `cli` builds Table 2 from lifecycle open claims | `table2=None` always | **NO** — target |
| AD-21 | `--weekly-ops`: … → file → **lifecycle refresh** → ops email | `ingest → assess → classify → file → email` | **NO** — missing lifecycle refresh step |

Verified chain in `trainline/cli.py` `_run_weekly_ops` (~lines 1425–1474) and `tests/test_weekly_ops_cli.py::test_weekly_ops_call_order_ingest_assess_classify_file_email` — expected order has **no** lifecycle or Gmail claim-mail step.

Spine scope line says *"Releases 1–5 shipped substrate + next-stage claim lifecycle / ops Table 2"* — accurate framing: **AD-18–21 are forward-looking**; repo is still at pre–Table-2 integration.

---

## Other spine claims spot-checked

| Claim | Finding |
| --- | --- |
| Hexagonal layout / pure engine | **Verified** — `engine/` has 3 modules; no I/O imports in boundary tests |
| Playwright for claim submission (AD-15) | **Verified** — `claim_submission.py` present; playwright in deps |
| AD-6 cancellation on by default | **Mostly aligned** — `RunConfig.enable_cancellation_fallback = True`; CLI disables only via `--no-cancellations`; engine bare-call default remains False (documented in config comment) |
| Deferred: OQ1 resolved | **Verified** — `tests/test_cancellation.py`, fixtures under `tests/fixtures/recorded_details_cancelled_*.json` |
| Gmail weekly ops (FR32–FR34) | **Verified** — ingest, marker, ops email Table 1 wired |
| FR37–FR39 Table 2 + lifecycle | **Not shipped** — parse layer only |

---

## Recommended spine / repo actions

| Priority | Item | Action |
| --- | --- | --- |
| 1 | `claim_lifecycle` in Structural Seed | Mark explicitly as **planned / Release 6** until `trainline/adapters/claim_lifecycle.py` lands; or add `[PLANNED]` tag in seed comment |
| 2 | AD-21 weekly chain diagram | Add footnote: *current repo stops at file → email; lifecycle refresh pending Story 7.5* |
| 3 | Stack table | Add Gmail + Pillow + pdfplumber rows with floors from `requirements-dev.txt` |
| 4 | `requirements-dev.txt` | Bump `requests>=2.25` → `>=2.31` to match spine |
| 5 | Structural Seed tree | Add shipped Release 4–5 modules (`ticket_intake`, `weekly_marker`, `booking_pdf`, `ollama_vision`, …) |
| 6 | Default lifecycle path | Resolve `claim-lifecycle.json` vs `claim_lifecycle.json` before implementation |

---

## Test evidence (spot run)

```
python -m pytest tests/test_claim_lifecycle.py tests/test_ops_email.py tests/test_swr_claim_mail.py -q
→ 10 passed, 8 skipped in 0.70s
```

- Skipped: all `test_claim_lifecycle_*`, Table 2 ops_email tests, stale importorskip gates on ops_email (module exists; some skips are conservative).
- Passing: `test_swr_claim_mail_*`, Table 1 ops_email, AD-2 ops_email/gmail isolation tests.

---

## Verdict summary

| Area | Verdict |
| --- | --- |
| Python 3.10+ / dev 3.12 | **OK** |
| requests >=2.31 (spine) vs >=2.25 (repo file) | **DRIFT** — bump repo pin |
| pytest / pytest-bdd / playwright floors | **OK** |
| Gmail / OCR / PDF deps | **GAP in spine** — shipped but unlisted |
| Hexagonal structure & Releases 1–5 substrate | **CONFIRMED** |
| `gmail.claim_mail` | **SHIPPED** |
| `ops_email` | **PARTIAL** — Table 1 + renderer; Table 2 integration deferred |
| `claim_lifecycle` | **SEED ONLY** — not implemented |
| AD-18–AD-21 weekly/lifecycle wiring | **AHEAD OF REPO** — target state documented correctly as next stage |

**Overall: PARTIALLY ALIGNED** — substrate trustworthy; Stack incomplete; Release-6 lifecycle/Table-2 is architecture-on-paper with parse/renderer prep done.

---

## Sources (repo-local)

- `requirements-dev.txt`
- `trainline/` package tree
- `trainline/cli.py` — `_run_weekly_ops`, `_run_weekly_ops_email`
- `trainline/adapters/ops_email.py`
- `trainline/adapters/gmail/claim_mail.py`
- `tests/test_claim_lifecycle.py`, `tests/test_ops_email.py`, `tests/test_swr_claim_mail.py`, `tests/test_weekly_ops_cli.py`
- Prior review: `reviews/review-versions.md` (2026-07-14)
