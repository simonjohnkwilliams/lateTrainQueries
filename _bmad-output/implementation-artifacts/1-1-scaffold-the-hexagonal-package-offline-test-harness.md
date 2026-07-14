# Story 1.1: Scaffold the hexagonal package + offline test harness

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want a clean `trainline/` package skeleton and an offline pytest/pytest-bdd harness,
so that every later story has a home and is built test-first with no network.

## Acceptance Criteria

1. **Package skeleton exists as importable stubs.** `trainline/engine/{models,delay,optimiser}.py`, `trainline/adapters/{hsp_client,storage,config}.py`, and `trainline/cli.py` all exist and import without error (empty/stub bodies are fine at this stage). The intra-package layout matches the Architecture "Structural Seed". *(Epic 1 AC; AD-1, AD-7)*
2. **Import-boundary test passes and is enforced.** An automated test proves nothing under `trainline/engine/` imports an I/O module (`requests`, `os`, `csv`, `json`, `pathlib`, `configparser`, `smtplib`, `urllib`, …) or any module under `trainline/adapters/`; and no adapter imports another adapter. Dependencies point inward toward `engine.models` only. *(Epic 1 AC; AD-1, AD-2, AD-9)*
3. **Old-model tests are removed (FR20).** The tests that lock in the old behaviour (>1-min threshold, both-legs drop, worst-per-day pick) are deleted, not kept as a regression baseline. *(Epic 1 AC; FR20)*
4. **`pytest` runs green offline with no network and no credentials.** The default invocation (`python -m pytest`) passes with zero network access and no `HSP_CREDENTIALS_FILE` set; the `live` marker stays excluded by default. *(Epic 1 AC; NFR2, FR21)*
5. **Real-HSP-grounded fixtures are preserved (FR21).** The recorded fixtures captured from the live HSP API (`tests/fixtures/recorded_metrics_2026-05-28.json` and `recorded_details_*.json`) are retained for later stories to ground the engine in real Darwin data. *(FR21)*

> **TDD (AD-12):** Write the ACs as failing tests first (import-boundary test for AC2 is the anchor scenario for this story; a smoke import test covers AC1), watch them fail, then make them pass. This is a scaffold story so the "implementation" is largely file creation + deletion — but the import-boundary test is real logic and must be seen to fail (e.g. temporarily against a deliberately-bad import) then pass.

## Tasks / Subtasks

- [ ] **Task 1 — Resolve the `TrainLine/` → `trainline/` collision and remove the old monolith (AC: 1, 3)**
  - [ ] `git rm -r TrainLine/` — removes `TrainLine/{TestFileGenerator,LateObject,JsonArgs,messageCreator}.py`, `TrainLine/__init__.py`, and `TrainLine/Results/`. **Critical (Windows):** the filesystem is case-insensitive, so `trainline/` cannot be created while `TrainLine/` exists — the old dir must go first. This is aligned with AD-7 (greenfield; old logic not carried forward).
  - [ ] Remove `scripts/verify_last_week.py` — it imports `TestFileGenerator`/`LateObject` and verifies the discarded >1-min behaviour, so it cannot compile once the old modules are gone (see Open Questions — confirm with Simon).
- [ ] **Task 2 — Create the `trainline/` package skeleton (AC: 1)**
  - [ ] `trainline/__init__.py`
  - [ ] `trainline/engine/__init__.py`, `engine/models.py`, `engine/delay.py`, `engine/optimiser.py` (stub bodies — module docstring only; no I/O imports)
  - [ ] `trainline/adapters/__init__.py`, `adapters/hsp_client.py`, `adapters/storage.py`, `adapters/config.py` (stub bodies; adapters may import `trainline.engine.models` only)
  - [ ] `trainline/cli.py` (stub composition root; may import all)
- [ ] **Task 3 — Rewrite the test harness for the new package (AC: 3, 4)**
  - [ ] Delete old-model test files: `tests/test_late_train_pipeline.py`, `tests/test_late_object.py`, `tests/test_http_calls.py`, `tests/test_json_args.py`, `tests/test_bdd_late_trains.py`, `tests/test_bdd_live.py`, `tests/features/late_trains.feature`, `tests/features/live_hsp_api.feature`.
  - [ ] Update `tests/conftest.py`: remove the `TrainLine/` sys.path hack; ensure the project root is importable so `import trainline...` resolves. No old-module paths.
  - [ ] Keep `pytest.ini` markers (`offline`/`recorded`/`live`) and `addopts = -m "not live"` — this is exactly the AD-12 testing convention; do not weaken it.
  - [ ] Add `tests/test_import_boundaries.py` (AC2) and a minimal `tests/test_package_imports.py` smoke test (AC1).
- [ ] **Task 4 — Implement the import-boundary test (AC: 2)**
  - [ ] For each module file under `trainline/engine/`, parse it with `ast` and collect every `import`/`from ... import`. Assert none resolve to a forbidden I/O module or to any `trainline.adapters.*`. (AST parsing avoids importing I/O side-effects and works on stub files.)
  - [ ] For each module under `trainline/adapters/`, assert it imports no other adapter module (only `trainline.engine.*` is allowed within the package).
  - [ ] Watch it fail first (e.g. add a throwaway `import os` to `engine/delay.py`, confirm red, remove it, confirm green).
- [ ] **Task 5 — Verify offline-green (AC: 4)**
  - [ ] Run `python -m pytest` from the project root with no `HSP_CREDENTIALS_FILE` and confirm all tests pass and the `live` scenario is deselected.
  - [ ] Optionally bump `requirements-dev.txt` `requests>=2.25` → `>=2.31` to match the Architecture stack (see Dev Notes).

## Dev Notes

### Why this story exists
This is the greenfield scaffold (AD-7). It replaces the monolithic `TrainLine/TestFileGenerator.py` with the hexagonal `trainline/` package and stands up the offline-first, test-first harness that **every** later story builds on. It deliberately carries **no** old logic forward (FR20) — only the real-HSP fixtures (FR21) and the pytest marker convention survive.

### Target structure (Architecture "Structural Seed")
```text
trainline/
  __init__.py
  engine/                # pure domain core — imports nothing I/O (AD-1)
    __init__.py
    models.py            #   Service, Claim, DayResult          (built in Story 1.2)
    delay.py             #   calculate_delay, band, payout       (built in Story 1.3)
    optimiser.py         #   per-day max-payout optimise         (built in Story 1.4/1.5)
  adapters/
    __init__.py
    hsp_client.py        #   HSP HTTP + TLS + cache; JSON->Service (Epic 2)
    storage.py           #   Claim -> CSV + JSON                 (Story 3.2)
    config.py            #   route / window / credentials        (Story 3.1)
  cli.py                 # composition root (AD-8)               (Story 3.3)
tests/
  ...                    # new-model unit + BDD tests; old-behaviour tests removed
```
Stubs are enough for now — later stories fill each module. Keep bodies to a module docstring (and, if you like, `pass`/`...`) so imports succeed without pulling in I/O.

### Dependency rules the boundary test must enforce (AD-1, AD-2, AD-9)
- `engine/*` imports **nothing** in the package and performs no I/O. Allowed stdlib for the core is limited to pure helpers (`dataclasses`, `enum`, `typing`, `functools`, `itertools`, `math`) — **not** `os`, `json`, `csv`, `pathlib`, `configparser`, `requests`, `smtplib`, `urllib`.
- `adapters/*` may import `trainline.engine.models` **only** — never `engine.delay`/`engine.optimiser`, never another adapter.
- `cli` may import everything.
- The only legal import arrows are the ones in the AD-9 mermaid diagram.

### CRITICAL — Windows case-insensitivity (do not skip)
`TrainLine/` (mixed-case) and the required `trainline/` (lowercase) are the **same path** on Simon's Windows machine (NFR3 context). You **cannot** have both. Sequence matters: `git rm -r TrainLine/` **first**, commit or stage the deletion, **then** create `trainline/`. A plain `mkdir trainline` while `TrainLine/` still exists will either silently write into the old dir or error. Verify with `git status` that the case flipped (git is case-sensitive even when the FS is not — use `git mv`/`git rm` so the rename is recorded correctly).

### Files being removed and why (read before deleting)
| File | Reason (old model / FR20) |
| --- | --- |
| `TrainLine/TestFileGenerator.py` | The monolith: `>1`-min threshold, `trimToRouteOnlyDictionary` (both-legs drop), `getLatestTrainObject` (worst-per-day), `generatePidList` (first-RID only, violates FR3). Replaced across Epics 1–3. |
| `TrainLine/LateObject.py` | Old `calculate_delay` on HHMM strings (no origin-day-relative minutes; cross-midnight bug per AD-4). Replaced by `engine.delay` (Story 1.3). |
| `TrainLine/JsonArgs.py` | Old config (`DAYS_BACK=9`, positional-arg model). Replaced by `adapters/config` (Story 3.1). |
| `TrainLine/messageCreator.py` | Old HSP request-body builder. Replaced by `adapters/hsp_client` (Epic 2). |
| `tests/test_late_train_pipeline.py` | Pins both-legs-drop + worst-per-day + first-RID. **Exactly** the behaviour FR20 says to discard. |
| `tests/test_late_object.py` | Pins old HHMM `calculate_delay`. |
| `tests/test_http_calls.py` | Pins old `writeServiceMetricsTestData`/`writeAttributeMessageTestData`/`getCredentials`. |
| `tests/test_json_args.py` | Pins old `JsonArgs.getJson` config. |
| `tests/test_bdd_late_trains.py` + `tests/features/late_trains.feature` | Named directly in FR20 (">1 minute / worst-per-day" BDD). |
| `tests/test_bdd_live.py` + `tests/features/live_hsp_api.feature` | Live scenario wired to the old pipeline; the new live path is defined later in Epic 2/3. |
| `scripts/verify_last_week.py` | One-off verifier of the **old** >1-min pipeline; imports deleted modules. (Confirm removal — Open Questions.) |

### Files being preserved / updated (read before touching)
- **KEEP `pytest.ini`** — markers + `addopts = -m "not live"` are the AD-12 convention. Current state: `testpaths=tests`, three markers, live excluded. Do not change semantics.
- **KEEP the recorded fixtures (FR21)** — `tests/fixtures/recorded_metrics_2026-05-28.json`, `recorded_details_202605287679094.json`, `...7679538`, `...7679545`, `...7679554`, `...7683874`, `...7683885`, `...7684064`, `...7684065`, `...7684066.json`. These are real Darwin captures (a quiet Thu 2026-05-28) and are the FR21 grounding for engine tests. Do **not** delete.
- **Synthetic fixtures** (`service_details_late.json`, `service_details_on_time.json`, `service_details_one_minute_late.json`, `service_details_very_late.json`, `service_details_inbound_late.json`, `service_metrics_god_wat.json`): hand-built for the old model. They are valid HSP-shaped JSON and may be reused as raw material when writing new-model tests. Not required by this story; leave them for now (a later story may prune/replace).
- **UPDATE `tests/conftest.py`** — current body inserts `PROJECT_ROOT` **and** `TrainLine/` onto `sys.path` for the old flat imports. After removal, drop the `TrainLine/` entry. Keep `PROJECT_ROOT` on `sys.path` (or rely on pytest rootdir + the `trainline/` package) so `import trainline.engine.models` resolves. Keep `tests/__init__.py` and `tests/fixtures/__init__.py`.

### Testing standards (AD-12, testing convention)
- Test-first: the import-boundary test (AC2) is the anchor. Prove it fails on a deliberately-bad import, then passes.
- Offline by default (NFR2/FR21): no network, no credentials. The `hsp_client` HTTP call becomes an injectable seam **in Story 2.1** — not this story; here `hsp_client.py` is just a stub.
- Prefer `ast`-based static analysis for the boundary test so it works on empty stubs and never triggers an I/O import side-effect.
- Keep `live`-marked tests deselected by default via the existing `addopts`.

### Stack (Architecture)
Python 3.10+ (dev on 3.12, matching the `__pycache__` `cpython-312`), `requests>=2.31`, `pytest>=7.0`, `pytest-bdd>=7.0`. Current `requirements-dev.txt` pins `requests>=2.25` — bump to `>=2.31` to match the spine (low risk; the seam is stubbed here anyway).

### Project Structure Notes
- New package `trainline/` sits at the project root beside `tests/`, per the Structural Seed. This **replaces** `TrainLine/`; the two cannot coexist on Windows (see CRITICAL note).
- `creds/trainConfig.txt` is unrelated to this story (FR17, Story 3.1) — leave it.
- No conflicts with the unified structure; the only variance is the deliberate removal of the old package and its one-off verify script.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-1] pure core; #AD-2 inward-only deps; #AD-7 greenfield; #AD-9 dependency diagram; #AD-12 test-first; #Structural Seed; #Stack
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR20] old tests rewritten not kept; #FR21 offline, real-HSP fixtures; #NFR2 offline-first; #NFR3 AVG-TLS
- Removed old code: `TrainLine/TestFileGenerator.py`, `LateObject.py`, `JsonArgs.py`, `messageCreator.py`, `scripts/verify_last_week.py`
- Removed old tests: `tests/test_late_train_pipeline.py`, `test_late_object.py`, `test_http_calls.py`, `test_json_args.py`, `test_bdd_late_trains.py`, `test_bdd_live.py`, `tests/features/late_trains.feature`, `live_hsp_api.feature`

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.

### File List
