# Story 3.1: Config — route/window/dates + credential loading

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want route, time windows, and dates driven by config, with credentials loaded from an external file,
so that I'm not editing code to change a query, and credentials stay out of the repo.

## Acceptance Criteria

1. **Defaults with no arguments.** With no CLI/config overrides, the tool produces a run configuration for **GOD ⇄ WAT** with **full-day** per-direction windows (capture *every* inbound and outbound service; the engine slims down afterward) and the lookback window already set. *(Epic 3 AC; FR16)*
2. **Everything is overridable, nothing hard-coded.** Given a config override, the origin/destination CRS codes, the per-direction time windows, and the date/lookback window are **all** configurable — no route, window, or date literal is baked into engine or adapter code paths. *(Epic 3 AC; FR16)*
3. **Credentials from `HSP_CREDENTIALS_FILE`, never in the repo.** Credentials are read from the file whose path is in the `HSP_CREDENTIALS_FILE` environment variable and are never committed. A missing file, missing env var, or malformed file is reported with a clear, actionable error. *(Epic 3 AC; FR17)*

> **TDD (AD-12):** Write each AC as a failing `@offline` test first (see Testing), watch it fail, then implement `adapters/config` to make it pass. No criterion ships without a test.

## Tasks / Subtasks

- [ ] **Task 1 — Define the run-config shape (AC: 1, 2)**
  - [ ] In `trainline/adapters/config.py`, define an immutable config object (e.g. a frozen `dataclass` `RunConfig`) carrying: `origin`/`destination` CRS, an outbound and an inbound leg each with `from_time`/`to_time` (HSP `HHMM` strings), the date basis (`to_date` + `lookback_days`, or an explicit date list), and a **`batch_size`** (max days fetched per run — supports the batched-fetch strategy below so a single invocation doesn't over-pull from HSP).
  - [ ] Config is **passed explicitly** to whatever needs it (hsp_client, engine, storage) — **no module-level/global mutable state** (AD-3 consistency convention). `cli.py` builds it once and threads it through (AD-8).
  - [ ] Keep the shape season-ticket-tolerant only insofar as it does not preclude a future ticket-type field (FR18 is owned by `engine.models`, but don't hard-block it here).
- [ ] **Task 2 — Defaults factory (AC: 1)**
  - [ ] Provide a `default_config()` (or equivalent) returning the GOD ⇄ WAT config with **full-day windows both directions** (decided 2026-07-14 — see "Query strategy" below): outbound `0000`–`2359`, inbound `0000`–`2359`, so no service is missed and the ≥15-min claimable-delay logic (Epic 1) does the slimming. Default `lookback_days` capped by the SWR 28-day filing window.
  - [ ] No positional-CLI parsing gap: unlike the old `getJson` (which documented but never parsed positional args), overrides must actually take effect (AC2).
- [ ] **Task 3 — Overrides (AC: 2)**
  - [ ] Allow overriding origin/destination CRS, each leg's window, and the date/lookback via an explicit override mechanism (kwargs/dict/CLI flags — pick one, document it). Supplied values win; unspecified values fall back to defaults.
  - [ ] Assert (via test) that changing route/window/date requires **no code edit** — everything flows through config.
- [ ] **Task 4 — Credential loading (AC: 3)**
  - [ ] Read the credentials file path from `HSP_CREDENTIALS_FILE`. Parse the INI format `[configuration]` with `username=` and `password=` keys (matches the existing `creds/trainConfig.txt` shape and the live-test contract).
  - [ ] Return credentials in a form `hsp_client` can consume for HTTP basic auth (Story 2.1). **Do not** hold credentials in the run-config object that might get logged/serialised; keep the loader separate.
  - [ ] Clear errors: env var unset → actionable message; file missing → message naming the path; malformed (no `[configuration]` section, or missing `username`/`password`) → message naming what's missing. Mirror the skip semantics the old live BDD used (`pytest.skip` when creds absent) so offline/live boundaries stay clean.
- [ ] **Task 5 — Tests (AC: 1, 2, 3)** — see Testing standards below.

## Dev Notes

### Why this story exists
`adapters/config` is the sole owner of *what to query* (route, windows, dates) and *how to authenticate* (credential file). It replaces the old `TrainLine/JsonArgs.py` (`getJson`) and the old `getCredentials()` from `TestFileGenerator.py` — re-implemented fresh, not carried forward (AD-7). It is a prerequisite for the `cli.py` composition root (Story 3.3), which builds the config and threads it through fetch → optimise → write.

### Architecture constraints (must follow)
- **AD-2 / AD-9 (dependency direction):** `adapters/config` may import `trainline.engine.models` **only**. It must **not** import `hsp_client` or `storage` (no adapter imports another adapter). The import-boundary test from Story 1.1 will enforce this — keep config clean or that test goes red.
- **AD-3 (no global state):** config is passed explicitly; credentials only from `HSP_CREDENTIALS_FILE`, never in the repo. Errors are surfaced clearly, never swallowed.
- **AD-8 (composition root):** `cli.py` — not config — decides how config is assembled from defaults + overrides at runtime. `config` provides the builder + loader; it does not orchestrate.
- **FR16:** route/window/date all config-driven. **FR17:** credentials external, path via env var. **NFR2:** offline tests need no network and no secrets.

### Files being created / touched (read before editing)
- **CREATE/FILL `trainline/adapters/config.py`** — currently a stub from Story 1.1. Add `RunConfig` (or equivalent), `default_config()`, an override path, and the credential loader.
- **CREATE `tests/test_config.py`** — new-model config tests.
- **DO NOT** import or resurrect `TrainLine/JsonArgs.py` — it is removed in Story 1.1. Its constants (`OUTBOUND_JOURNEY`, `DEPARTURE_STATION`, `START_TIME`, `DAYS_BACK`, etc.) are gone by design.

### Query strategy — full-day windows + batched fetch (decided 2026-07-14, Simon)
The default query is **deliberately wide**: pull *all* inbound and outbound services for each day (full-day `0000`–`2359` both directions), and let the Epic 1 engine apply the ≥15-min claimable-delay logic to slim results down. Rationale: never miss a train Simon could have caught (SM2/CM1 — a wide net is correctness-first).

Because a wide window over a multi-day lookback is a lot of HSP calls, **runs must be batchable so a single invocation doesn't pull too much from the train API**:
- `RunConfig.batch_size` bounds how many days one run fetches; the composition root (Story 3.3) iterates the lookback in chunks of `batch_size`.
- The on-disk response cache (Story 2.4, NFR4) means re-running a week never re-hits already-fetched days — so batches are resumable and cheap to repeat.
- Keep live request volume modest (the old live test deliberately capped to ~3 RIDs "for CI politeness"); document any per-run cap so nothing silently truncates coverage.
This is a config + orchestration concern only; the engine stays pure. Cross-references: Story 2.4 (cache), Story 3.3 (batched orchestration), Story 2.2/2.5 (fetch + failure contract).

### Old behaviour, for reference only (superseded — do NOT replicate the bugs)
The old `JsonArgs.getJson` defaults were: outbound **GOD→WAT `0400`–`1300`**, inbound **WAT→GOD `1200`–`2359`**, lookback **`DAYS_BACK = 9`** ("one week + buffer"), `clear_old_data = True`, start date = two days ago. It documented positional CLI args but **never actually parsed them** (called out in FR16) — the override path here must genuinely work. The old `getCredentials(path)` read INI `[configuration]` → `["username", "password"]` from `creds/trainConfig.txt`. Reuse the **file format**, not the code.

### CRITICAL — credentials hygiene (do not skip)
`creds/trainConfig.txt` holds real HSP usernames + endpoints and **must never be committed** (it is `.gitignore`d; FR17). It may be used **only** for live-endpoint testing by pointing `HSP_CREDENTIALS_FILE` at it. Offline tests **must** create their own throwaway credentials file in a `tmp_path` — never read, copy, or assert against the real `creds/trainConfig.txt`. Never log credential values.

### Testing standards (AD-12, testing convention)
- Test-first, `@offline`, no network, no real secrets. New file `tests/test_config.py`.
- **Defaults (AC1):** `default_config()` → GOD ⇄ WAT, both legs' windows = full day (`0000`–`2359`), lookback set, `batch_size` set; assert the concrete values.
- **Overrides (AC2):** supplying custom CRS / windows / date-basis is honoured and beats defaults; a test that a route/window/date change needs no source edit (drive it purely through the override API).
- **Credentials (AC3):** write a valid INI file to `tmp_path`, point `HSP_CREDENTIALS_FILE` at it (via `monkeypatch.setenv`), assert it loads; then assert clear errors for (a) env var unset, (b) file missing, (c) malformed file (no `[configuration]`, or missing `username`/`password`). Use `monkeypatch`, never the real creds file.
- Keep the `pytest.ini` marker convention (`offline`/`recorded`/`live`, `addopts = -m "not live"`) intact.

### Project Structure Notes
- `config.py` sits under `trainline/adapters/` per the Structural Seed; it is one of the three MVP adapters (`hsp_client`, `storage`, `config`).
- No structural variance. The only cross-cutting rule to respect is "no global mutable state" — build config in `cli.py` and pass it down.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1] — user story + ACs
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR16] config-driven route/window/date; #FR17 credentials via `HSP_CREDENTIALS_FILE`, never in repo; #NFR2 offline-first
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-2] inward-only deps; #AD-3 no global state / config explicit; #AD-8 composition root; #Consistency Conventions (credentials only from `HSP_CREDENTIALS_FILE`)
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#SWR claim form] 28-day filing window (context for lookback sizing)
- Replaces (removed in Story 1.1): `TrainLine/JsonArgs.py`, `getCredentials()` in `TrainLine/TestFileGenerator.py`

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
