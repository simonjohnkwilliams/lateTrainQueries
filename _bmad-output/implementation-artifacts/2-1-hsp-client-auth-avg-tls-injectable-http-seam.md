# Story 2.1: HSP client — auth + AVG-TLS + injectable HTTP seam

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As Simon,
I want an HSP client that authenticates and works under AVG TLS interception, with the HTTP call injectable,
so that real runs succeed on my machine and tests run offline.

## Acceptance Criteria

1. **Injectable transport → offline by default.** The client is constructed with an injectable transport/session; in a test a fake transport is used and **no real network call happens**. *(Epic 2 AC; NFR2, testing convention)*
2. **`REQUESTS_CA_BUNDLE` honoured.** When `REQUESTS_CA_BUNDLE` is set, a real request honours it so `requests` verifies TLS under AVG interception; the client never disables verification. *(Epic 2 AC; NFR3)*
3. **HTTP basic auth applied.** When credentials are supplied, every request carries HTTP basic auth. *(Epic 2 AC)*

> **TDD (AD-12):** Write each AC as a failing `@offline` test first (fake transport asserts no real socket + basic-auth header present; a test asserting the client leaves `verify` at its default so `REQUESTS_CA_BUNDLE` applies), watch red, then implement. The `@live` end-to-end path is opt-in and must skip cleanly with no credentials.

## Tasks / Subtasks

- [ ] **Task 1 — Define the HSP client with an injectable transport seam (AC: 1, 3)**
  - [ ] In `trainline/adapters/hsp_client.py` (stub from Story 1.1), add an `HspClient` that accepts a `session`/transport parameter defaulting to `requests.Session()`, plus the credentials (username, password) and, optionally, the base URL.
  - [ ] Apply HTTP basic auth from the supplied credentials — either `session.auth = (user, pw)` at construction or `auth=(user, pw)` per `POST`. Pick one and be consistent.
  - [ ] Expose a single low-level `_post(endpoint, json_body)` (or similar) used by Stories 2.2/2.3; higher-level `service_metrics(...)` / `service_details(...)` methods land in those stories — here just the transport + auth + a thin POST.
- [ ] **Task 2 — Honour `REQUESTS_CA_BUNDLE` for AVG-TLS (AC: 2)**
  - [ ] Do **not** pass `verify=False` and do **not** hard-code a `verify=<path>`. `requests` reads `REQUESTS_CA_BUNDLE` from the environment by default; leave verification at its default so the env var applies.
  - [ ] If you must set `verify` explicitly, source it from `os.environ.get("REQUESTS_CA_BUNDLE")` and fall back to the default (`True`) when unset — never to `False`.
- [ ] **Task 3 — Tests (AC: 1, 2, 3)**
  - [ ] `tests/test_hsp_client.py` `@offline`: construct the client with a fake transport (a stub session whose `.post` records the call and returns a canned response); assert (a) no real network occurs, (b) the recorded call carries basic auth, (c) it POSTs to the expected endpoint/body shape.
  - [ ] `@offline`: assert the client does not disable TLS verification (e.g. the fake session's `.post` is never called with `verify=False`, or the client honours a `REQUESTS_CA_BUNDLE` value passed via monkeypatched env).
  - [ ] `@live` (opt-in): a smoke test that skips cleanly when `HSP_CREDENTIALS_FILE` is unset/missing (NFR2), and otherwise makes one real authenticated call. Reuse the `live` marker already in `pytest.ini` (deselected by default via `addopts`).

## Dev Notes

### Why this story exists
This is the first Epic 2 story. It stands up the **transport backbone** every later HSP story depends on: an authenticated, AVG-TLS-tolerant HTTP client whose network call is an **injectable seam** so all of Epic 2 is testable offline (NFR2, FR21). Per AD-7 this is re-implemented **fresh** — do not port the old `TrainLine/TestFileGenerator.py` request code (which was removed in Story 1.1); only the *behaviours* NFR3 (CA-bundle) and, later, NFR4 (cache, Story 2.4) survive.

### The injectable seam (testing convention — the crux of this story)
The architecture's testing convention says *"the HTTP call in `hsp_client` is an injectable seam (session/transport passed in), so default tests run offline against fixtures with no network or credentials."* Concretely:
- Constructor signature roughly: `HspClient(credentials, session=None, base_url="https://hsp-prod.rockshore.net/api/v1")`, where `session` defaults to `requests.Session()`.
- Offline tests pass a fake `session` object exposing `.post(url, json=..., auth=..., timeout=...)` that returns a canned response and records what it was called with — **zero** sockets opened.
- This seam is what Stories 2.2 (`serviceMetrics`), 2.3 (`serviceDetails`), 2.4 (cache), and 2.5 (failure contract) all drive in their offline tests.

### NFR3 — AVG TLS interception (do not skip; Windows-specific)
Simon's machine runs AVG, which MITM-intercepts TLS, so Python `requests` cannot verify the real Darwin chain — it must trust the project-local CA bundle that AVG presents, pointed at by the `REQUESTS_CA_BUNDLE` environment variable.
- `requests` reads `REQUESTS_CA_BUNDLE` **automatically** when `verify` is left at its default (`True`). So the correct implementation is to **leave `verify` alone**.
- **Never** use `verify=False` — it defeats NFR3's intent (verified TLS) and would ship an insecure default. The whole point is to verify *against the AVG bundle*, not to skip verification.
- Live runs set both `HSP_CREDENTIALS_FILE` and `REQUESTS_CA_BUNDLE` (see `scripts`-era usage). Cloud runners won't need the CA bundle (no AVG), so honouring the env var (absent → default) is the portable design.

### Boundary rules (AD-2)
- `hsp_client` imports `trainline.engine.models` only (plus stdlib `os` and third-party `requests`). It must **not** import `trainline.adapters.config` or `trainline.adapters.storage` (no adapter imports another adapter — enforced by the Story 1.1 import-boundary test).
- `hsp_client` does **not** read credentials from a file — credential loading from `HSP_CREDENTIALS_FILE` is `adapters/config`'s job (Story 3.1, FR17). The composition root (`cli.py`, Story 3.3) loads creds via `config` and passes them into `HspClient`. Keep this story's client credential-source-agnostic: it receives a (user, pw) pair.

### HSP endpoints & request shape (addendum reference)
- POST `https://hsp-prod.rockshore.net/api/v1/serviceMetrics`
- POST `https://hsp-prod.rockshore.net/api/v1/serviceDetails`
- Bodies are JSON; the specific body fields (`from_loc`/`to_loc`/`days:'WEEKDAY'` for metrics; `{rid}` for details) are the concern of Stories 2.2/2.3 — this story only needs the generic authenticated POST.

### Credentials for live testing (never commit)
`creds/trainConfig.txt` (INI: `[configuration]` / `username=` / `password=`) holds real HSP usernames + endpoints. It is git-ignored and **must never be committed** — it exists solely to point `HSP_CREDENTIALS_FILE` at for opt-in `@live` tests. Offline tests never touch it.

### Testing standards (AD-12, testing convention)
- Default suite is `@offline`: no network, no credentials (NFR2). Prove the fake transport is used and no real socket opens.
- Keep the `live` marker deselected by default (already configured in `pytest.ini` `addopts = -m "not live"`); the `@live` smoke test must `pytest.skip(...)` when `HSP_CREDENTIALS_FILE` is unset.
- Recorded fixtures (`tests/fixtures/recorded_*`) preserved in Story 1.1 are the raw material for 2.2/2.3 offline tests; this story's fake responses can be minimal canned dicts.

### Project Structure Notes
- Fills the `trainline/adapters/hsp_client.py` stub created in Story 1.1. No new top-level dirs.
- No change to `engine/` (pure core stays untouched).

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1] — user story + ACs
- [Source: _bmad-output/planning-artifacts/architecture/architecture-lateTrainQueries-2026-07-14/ARCHITECTURE-SPINE.md#AD-2] inward-only deps; #AD-7 greenfield (re-implement NFR3 fresh); #Consistency Conventions → Testing (injectable seam); #Stack (requests>=2.31)
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/prd.md#NFR2] offline-first; #NFR3 AVG-TLS `REQUESTS_CA_BUNDLE`; #FR17 creds from `HSP_CREDENTIALS_FILE`
- [Source: _bmad-output/planning-artifacts/prds/prd-lateTrainQueries-2026-07-14/addendum.md#HSP JSON shape reference] endpoints + POST shapes

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.

### File List
