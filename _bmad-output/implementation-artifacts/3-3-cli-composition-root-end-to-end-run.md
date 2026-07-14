# Story 3.3: CLI composition root — end-to-end run

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want one command that produces a week of file-ready claims,
so that filing is a matter of copying verified rows into the SWR form.

## Acceptance Criteria

1. **`cli.py` is the sole orchestrator (AD-8).** The wired `trainline/cli.py` orchestrates the full flow `config → hsp_client → engine.optimise → storage`, and **nothing else** orchestrates. No orchestration logic (fetch/optimise/write sequencing) lives in `engine/*` or in any adapter. *(Epic 3 AC; AD-8, FR11)*
2. **End-to-end run over a stubbed week produces CSV + JSON.** Given a week of (stubbed) HSP data injected through the Story 2.1 transport seam, running the pipeline end-to-end produces both a CSV and a JSON claim file containing the claimable days' rows. *(Epic 3 AC; FR13, FR14)*
3. **A fetch-failed day is reported as "not analysed", distinct from a clean no-claim day (AD-5).** When a required leg fails to fetch, that day appears in the run summary/output as "not analysed" (or equivalent explicit marker), visibly and semantically distinct from a day that fetched OK but had nothing claimable. The two are never conflated. *(Epic 3 AC; FR5, AD-5, NFR1/CM1)*
4. **The recorded real-HSP fixtures drive an offline end-to-end BDD scenario that passes (FR21).** An `@recorded` scenario runs the whole pipeline from the captured 2026-05-28 Darwin fixtures through to CSV + JSON, offline, with no network and no credentials — grounding the entire pipeline in real Darwin data. *(Epic 3 AC; FR21, NFR2)*

> **TDD (AD-12):** All four ACs are pytest-bdd Gherkin scenarios written **first** (fail → pass), one-to-one with the criteria above. This is the MVP capstone story — its acceptance tests are the executable definition of "the tool works end-to-end". A story is not done until every scenario is green and no criterion is untested.

## Tasks / Subtasks

- [ ] **Task 1 — Write the acceptance scenarios first (AC: 1, 2, 3, 4)**
  - [ ] `tests/features/claims_pipeline.feature` with four scenarios: (a) `@offline` end-to-end over a stubbed week → CSV+JSON for claimable days; (b) `@offline` sole-orchestrator assertion; (c) `@offline` injected fetch failure → day shows "not analysed" not no-claim; (d) `@recorded` real-fixture end-to-end offline.
  - [ ] `tests/test_bdd_claims_pipeline.py` step definitions. Watch all scenarios fail before wiring `cli`.
- [ ] **Task 2 — Wire `trainline/cli.py` as the composition root (AC: 1, 2)**
  - [ ] `cli.main(argv, transport=None)` (or equivalent): load config (`adapters/config`), construct `hsp_client` with the injected transport/session (default = real requests session), fetch per-day `DayResult`s (both directions, all RIDs, cache-aware), call `engine.optimise(days, config)`, hand the resulting `DayResult`s to `storage` to write CSV + JSON.
  - [ ] `cli` may import config, hsp_client, storage, and engine (AD-2 permits cli → everything). No adapter-to-adapter calls; no engine I/O.
  - [ ] Keep the flow linear and side-effect-free except through the adapters (all disk/network stays in hsp_client/storage; all decisions stay in engine).
- [ ] **Task 3 — Surface the AD-5 status distinction in the run output (AC: 3)**
  - [ ] Emit a per-day run summary that renders `FETCH_FAILED` days as "not analysed" (or similar) and OK-with-no-claim days as "no claim" — never the same token. Ensure the JSON/CSV output (owned by `storage`) also preserves the distinction (a failed day is not written as a clean zero-claim row).
- [ ] **Task 4 — Provide `python -m trainline` / console entry (AC: 1, 2)**
  - [ ] Add `trainline/__main__.py` (or a `main()` guarded by `if __name__ == "__main__"`) so the tool runs as one command from the project root, defaulting to GOD ⇄ WAT (config defaults from Story 3.1).
- [ ] **Task 5 — Offline & recorded verification (AC: 2, 4)**
  - [ ] Confirm the stubbed-week scenario writes CSV+JSON with the expected claimable rows.
  - [ ] Confirm the `@recorded` scenario drives the real `recorded_metrics_2026-05-28.json` + `recorded_details_*.json` through the full pipeline offline and asserts the produced claim output. Update the expected claim outcome to the **new** claimable-delay model (not the old >1-min/worst-per-day result).
  - [ ] Run `python -m pytest` with no `HSP_CREDENTIALS_FILE`; all pass, `live` deselected.
- [ ] **Task 6 — (Optional) live smoke path (AC: n/a)**
  - [ ] If adding a `@live` end-to-end scenario, gate it behind `HSP_CREDENTIALS_FILE` and the `live` marker so it skips cleanly by default (NFR2). Not required for MVP completion.

## Dev Notes

### Why this story exists
This is the **MVP capstone** — the single command that turns "a week on the GOD ⇄ WAT line" into file-ready claim data. It wires together everything built in Epics 1–3 behind one composition root and proves, against real recorded Darwin data, that the whole pipeline produces correct claims offline. When this is green, the MVP is functionally complete.

### Composition-root contract (AD-8, AD-1, AD-2)
- `cli.py` is the **only** MVP orchestrator. The flow is exactly: `config → hsp_client → engine.optimise → storage`.
- A future **Lambda handler** would be a *second* composition root calling the same `engine.optimise(days, config)` — so keep all orchestration in `cli` and none in `engine`. This is the whole point of the hexagonal shape: the core is reused verbatim by a new entry point; only the root changes.
- Import rules (AD-2/AD-9): `cli` may import config, hsp_client, storage, engine. Adapters still may import `engine.models` only; engine still imports nothing I/O. Do not introduce an adapter→adapter call to "simplify" wiring — that belongs in `cli`.

### The AD-5 "not analysed" distinction (AC3 — correctness-critical)
Per AD-5 and NFR1/CM1, a `FETCH_FAILED` day must never read as a clean no-claim. A silent failure that looks like "nothing to claim" is exactly the failure mode SM2/CM1 guard against — it invisibly misses money. `engine.optimise` passes `DayResult.status` through unchanged; **`cli` (and `storage`) own the surfacing.** The run summary and the persisted output must show three distinct day outcomes: (1) OK + claim(s), (2) OK + no claim, (3) FETCH_FAILED = "not analysed". Do not write a failed day as a zero-row/zero-delay clean day.

### Offline-first wiring (NFR2, FR21)
- The HSP HTTP call is an **injectable seam** introduced in Story 2.1 (session/transport passed in). `cli.main` must accept/allow injecting that transport so the end-to-end BDD scenarios run with a fake transport — no network, no credentials.
- The default (production) path constructs a real `requests` session; the AVG-TLS `REQUESTS_CA_BUNDLE` handling (NFR3) lives inside `hsp_client` (Story 2.1), not here.

### FR21 — the recorded end-to-end scenario
- Fixtures to drive: `tests/fixtures/recorded_metrics_2026-05-28.json` and the `recorded_details_202605287679094.json … recorded_details_2026052876840*.json` set (real Darwin captures from a quiet Thu 2026-05-28; all ran, none cancelled — so this scenario exercises the delay/optimise path, not cancellation).
- This scenario is the **successor** to the old `late_trains.feature` `@recorded` scenario (removed in Story 1.1). The old expectation was "3-min delay row at 0708" under the discarded >1-min/worst-per-day model. Under the **new** claimable-delay model (≥15-min threshold), recompute the expected outcome from the fixtures: if no service reaches 15 min at its destination that day, the correct MVP result is **no claim rows** for 2026-05-28 (and the day must read as OK/no-claim, not "not analysed"). Assert the actual claim output the new model yields — do not port the old number.

### Config defaults (Story 3.1 dependency)
Default route GOD ⇄ WAT with per-direction windows and lookback come from `adapters/config` (Story 3.1, FR16). `cli` reads config; it does not hard-code the route. Credentials come from `HSP_CREDENTIALS_FILE` (FR17) via config — never inline, never committed.

### Dependencies & sequencing
Depends on **all** prior stories — build this **last**:
- Story 1.2 (`models`: Service/Claim/DayResult + status), 1.3 (`delay`), 1.4 (`optimiser.optimise`).
- Stories 2.1–2.5 (`hsp_client`: transport seam, metrics+all-RIDs, details→Service, cache, fetch-failure/status rollup).
- Story 3.1 (`config`), Story 3.2 (`storage`: CSV+JSON, SWR fields, sorted).

### Testing standards (AD-12, testing convention)
- Test-first; scenarios map one-to-one to ACs; fail-first then pass.
- `@offline` by default (no network/creds); `@recorded` also offline (fixture-driven); any `@live` scenario opt-in via the `live` marker and skips without `HSP_CREDENTIALS_FILE`.
- Keep `pytest.ini`'s `addopts = -m "not live"` intact.
- A dedicated test asserts sole-orchestrator: e.g. static/AST check or design test that `engine/*` contains no fetch/write calls and no adapter contains cross-adapter orchestration.

### Project Structure Notes
- New: `trainline/cli.py` (filled in from the Story 1.1 stub), optional `trainline/__main__.py`, `tests/features/claims_pipeline.feature`, `tests/test_bdd_claims_pipeline.py`.
- Output location for CSV+JSON is owned by `storage` (Story 3.2) and driven by config — `cli` passes it through, does not invent its own path scheme.
- No conflicts with the unified structure; this story only fills the composition root and adds end-to-end tests.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-8] composition root; #AD-1 pure core; #AD-2/#AD-9 dependency direction; #AD-5 failure vs no-claim
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#FR5] fetch-failure visible; #FR11 pure core; #FR13–FR15 output; #FR21 offline real-fixture grounding; #NFR2 offline-first
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#HSP JSON shape reference] fixture shapes; #The per-day optimisation, precisely
- Successor to removed `tests/features/late_trains.feature` @recorded scenario (Story 1.1)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
