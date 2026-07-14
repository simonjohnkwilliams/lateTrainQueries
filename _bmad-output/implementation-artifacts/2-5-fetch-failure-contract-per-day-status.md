# Story 2.5: Fetch-failure contract (per-day status)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want a failed fetch to never masquerade as "no claim",
so that I never silently miss money.

## Acceptance Criteria

1. **A failed fetch marks the day FETCH_FAILED, never a clean no-claim.** When a `serviceMetrics` **or** any required `serviceDetails` fetch fails for a day, that day's `DayResult.status` is `FETCH_FAILED` and it is reported as "not analysed" — it is never emitted as a trustworthy no-claim day. *(Epic 2 AC; FR5, AD-5, NFR1 SM2/CM1)*
2. **A day is OK only if every required leg fetched.** `DayResult.status` is `OK` **only if** both directions' `serviceMetrics` fetched successfully **and** all of their `serviceDetails` fetched successfully. Any single required-fetch failure downgrades the whole day to `FETCH_FAILED`. *(Epic 2 AC; AD-5)*
3. **A single failure is logged and skipped without aborting the run.** One failing day/service is logged (visibly, distinct from "no claim") and skipped; the run continues to fetch and assemble the remaining days. *(Epic 2 AC; FR5, NFR5)*

> **TDD (AD-12):** Encode all three ACs as `@offline` pytest-bdd/unit tests **first** (fake transport injecting failures), watch them fail against the current stub, then implement the roll-up until green. No criterion ships without a test. This is the correctness spine of Epic 2 (NFR1) — the anchor scenario is AC1 (a failure must not read as no-claim).

## Tasks / Subtasks

- [ ] **Task 1 — Per-service fetch-outcome recording in `hsp_client` (AC: 1, 2)**
  - [ ] As each `serviceMetrics` (per direction) and `serviceDetails` (per RID) call is made through the injectable transport (Story 2.1), record its outcome (success / failure) keyed by day and direction.
  - [ ] A required fetch = both directions' metrics for the day **and** every RID's details discovered from those metrics.
- [ ] **Task 2 — Roll up outcomes into `DayResult.status` (AC: 1, 2)**
  - [ ] Compute per-day status: `OK` iff all required fetches for the day succeeded; otherwise `FetchStatus.FETCH_FAILED` (enum from `engine.models`, Story 1.2).
  - [ ] Build the day's `DayResult` with its `Service`s (from the successful fetches) **and** the computed `status`. Never hand the engine a day that looks empty when it actually failed to fetch.
  - [ ] The engine (Story 1.4) passes `status` through unchanged — do not compute or reinterpret status inside `engine`.
- [ ] **Task 3 — Resilience: log-and-skip, never abort (AC: 3)**
  - [ ] Wrap each fetch so an exception/error for one day or one service is caught, logged with enough context to identify it (date, direction, RID, error), and does not propagate to abort the whole run.
  - [ ] Ensure the log line for a failure is clearly distinct from a legitimate no-claim day so a skipped day is visible downstream (Story 3.3 surfaces "not analysed").
- [ ] **Task 4 — Tests first (AC: 1, 2, 3)**
  - [ ] `tests/test_fetch_failures.py` (`@offline`): metrics-fetch failure → day `FETCH_FAILED`; details-fetch failure (one RID) → day `FETCH_FAILED`; all-succeed → day `OK`; and a mid-run failure → run continues + other days assembled + failure logged.
  - [ ] Assert explicitly that a `FETCH_FAILED` day is **not** an empty/clean no-claim `DayResult`.

## Dev Notes

### Why this story exists
This is the last story of Epic 2 and the guardrail that makes the whole acquisition layer trustworthy. Per **AD-5** and the PRD's **SM2/CM1** correctness metrics, a failed HSP fetch that silently reads as "nothing to claim" would miss claimable money **invisibly** — the single worst failure mode for this product (NFR1: a wrong/under claim is worse than a slow run). Stories 2.1–2.4 fetch, extract RIDs, map to `Service`, and cache; this story makes the day *honest* about whether it was fully seen.

### Ownership boundary (AD-5, AD-2)
- **`hsp_client` OWNS the meaning of fetch success/failure.** It records per-service outcomes and rolls them up into `DayResult.status`.
- **`engine` passes `status` through unchanged** (Story 1.4's optimiser does not own its meaning — it only optimises the services it is given and forwards the day's status).
- **`cli`** (Story 3.3) surfaces `FETCH_FAILED` days as "not analysed", distinct from a clean no-claim day.
- Boundary: `hsp_client` imports `trainline.engine.models` only — never another adapter, never `engine.delay`/`engine.optimiser` (AD-2, AD-9). The import-boundary test from Story 1.1 enforces this.

### Data shapes (from `engine.models`, Story 1.2)
- `DayResult` carries `date`, a fetch `status` (`FetchStatus.OK` / `FetchStatus.FETCH_FAILED`), the day's `Service`s, and 0–2 `Claim`s. A bare `list[Claim]` is **not** a legal engine return precisely because it cannot express a failed day (AD-1). Confirm the exact `FetchStatus` enum name/values against `engine/models.py` as built in Story 1.2 and use them verbatim.

### What "required legs" means (AD-5, precisely)
For a given date D the required fetches are:
1. `serviceMetrics` for **outbound** (GOD→WAT) on D.
2. `serviceMetrics` for **inbound** (WAT→GOD) on D.
3. `serviceDetails` for **every** RID discovered in (1) and (2) — recall FR3: all RIDs, not just `rids[0]`.

If **any** of these fails, the day is `FETCH_FAILED`. Only when all succeed is the day `OK` and its claim/no-claim result trustworthy.

### Interaction with the cache (Story 2.4)
A cached day is one that previously fetched successfully; re-running must reproduce `OK` without re-hitting the API (NFR4). A `FETCH_FAILED` day should **not** be cached as if successful — a later re-run must be able to retry it (do not poison the cache with a failure). Align with the cache semantics established in Story 2.4.

### Testing standards (AD-12, testing convention)
- `@offline` by default; no network, no `HSP_CREDENTIALS_FILE` (NFR2, FR21). Drive failures through the injectable transport/session seam from Story 2.1 (e.g. a fake that raises or returns an error for a chosen call).
- Test-first: write the failing tests, see red, implement, see green.
- Keep `live`-marked tests deselected by default (`pytest.ini` `addopts = -m "not live"`).
- Prefer asserting on `DayResult.status` and the absence of spurious `Claim`s, not on log text — but do assert a failure is logged (capture with `caplog`).

### Stack
Python 3.10+ (dev 3.12), `requests>=2.31`, `pytest>=7.0`, `pytest-bdd>=7.0`.

### Project Structure Notes
- Lives in `trainline/adapters/hsp_client.py` (extends Stories 2.1–2.4). New test file `tests/test_fetch_failures.py`.
- No structural variance; this story adds the status roll-up to the client built earlier in Epic 2 and depends on the `FetchStatus`/`DayResult` shapes from Story 1.2.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-5] fetch failure ≠ no-claim; #AD-1 DayResult legal return; #AD-2/#AD-9 boundaries
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR5] tolerate + surface failures; #NFR1 correctness (SM2/CM1)
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#HSP JSON shape reference] — cancelled/empty-actual signal is distinct from a fetch failure (do not conflate)
- Depends on: Story 1.2 (`DayResult`/`FetchStatus`), Story 2.1 (injectable transport), Stories 2.2–2.4 (metrics/details/cache)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
