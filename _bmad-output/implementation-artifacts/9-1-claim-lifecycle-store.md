---
story_key: 9-1-claim-lifecycle-store
epic: 9
status: review
created: 2026-07-27
baseline_commit: 0410d8394dd6fa3dbc94e77c9f8b54a7528c5da5
depends_on: []
blocks: [9-2, 9-3, 9-4]
supersedes: [7-5]
---

# Story 9.1: Claim lifecycle store

Status: review

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a developer,
I want a durable local claim-lifecycle JSON store with monotonic stage updates and Table 2 query helpers,
So that later stories can record filings, refresh from Gmail, and build idempotent Table 2 without inventing persistence.

## Acceptance Criteria

1. **Module + default path (AD-18).** `trainline.adapters.claim_lifecycle` exposes `LifecycleStore` and `DEFAULT_LIFECYCLE_PATH = Results/claim-lifecycle.json` (hyphen). Persisted statuses only: `submitted|received|approved|paid|failed`.
2. **Record shape (AD-18).** Each record has `claim_id`, `status`, `date`, `direction`, optional `amount_gbp`, `updated_at`, `reported_paid_at` (ISO string or null). Filing audit JSONL stays append-only elsewhere — this store is **current** status only.
3. **`record_submitted` (AD-19).** Upserts by claim id to status `submitted` with `date`, `direction`, `updated_at`; `reported_paid_at` remains null on create. Idempotent: second call same id → still one record (may refresh metadata/`updated_at`).
4. **`apply_stage` monotonic (AD-19, FR38).** Rank `submitted < received < approved < paid`. Never regress. Unknown/lower stage is a no-op. `failed` is terminal — does not advance to inbox stages.
5. **Table 2 helpers (AD-20, FR37, FR39).** `open_for_table2()` returns rows where `reported_paid_at` is null (including `paid` not yet reported). `mark_reported_paid(claim_ids, when)` sets `reported_paid_at` ISO timestamps.
6. **Hexagonal (AD-2).** Store module must not import `gmail` or `playwright`. No CLI wiring in this story (9.2–9.4).
7. **Offline TDD (AD-12).** `@pytest.mark.offline` tests under `tests/test_claim_lifecycle.py`; default suite needs no network. Align API names with AD-19 (`record_submitted` / `apply_stage`) — replace legacy 7.5 names `upsert_submitted` / `apply_inbox_stage`.

## Tasks / Subtasks

- [x] RED: rewrite `tests/test_claim_lifecycle.py` to AD-19 API + ACs; prove importorskip / failures before module exists (AC: #1–#7)
  - [x] `record_submitted` → `submitted` + fields
  - [x] promote received → approved → paid
  - [x] no downgrade paid → received
  - [x] `failed` terminal
  - [x] `open_for_table2` omits reported-paid; keeps unreported paid
  - [x] idempotent same claim id
  - [x] source has no gmail/playwright
  - [x] default path constant uses `claim-lifecycle.json`
- [x] GREEN: implement `trainline/adapters/claim_lifecycle.py` (AC: #1–#6)
  - [x] `ClaimLifecycleRecord` (frozen or dataclass) + status rank helpers
  - [x] `LifecycleStore(path)` load/save JSON map keyed by claim id (DropHashStore-style rewrite)
  - [x] `record_submitted`, `apply_stage`, `get`, `all`, `open_for_table2`, `mark_reported_paid`
  - [x] `DEFAULT_LIFECYCLE_PATH`
- [x] Confirm `python -m pytest -q --tb=line tests/test_claim_lifecycle.py` green; full offline suite no regressions
- [x] Do **not** wire CLI, Gmail refresh, or ops email Table 2 (Stories 9.2–9.4)

## Dev Notes

### Architecture compliance (must follow)

| Decision | Rule for this story |
| --- | --- |
| AD-18 | New adapter only; path `Results/claim-lifecycle.json`; statuses listed above; `reported_paid_at` |
| AD-19 | API: `record_submitted`, `apply_stage`; monotonic rank; no Gmail import in store |
| AD-2 | No adapter→adapter; store is pure persistence + status rules |
| AD-12 | Tests first; offline default |
| AD-16 | Do not rewrite filing-audit.jsonl as status |

### Naming drift to resolve (locked for Epic 9)

| Legacy (Story 7.5 / old tests) | Epic 9 / spine |
| --- | --- |
| `upsert_submitted` | `record_submitted` |
| `apply_inbox_stage` | `apply_stage` |
| `Results/claim_lifecycle.json` | `Results/claim-lifecycle.json` |
| `journey_date` / `summary` | `date` / `direction` (AD-18) |

Do not keep aliases unless a one-line shim is needed for a mid-migration test — prefer updating tests to AD names.

### Suggested record / API sketch

```python
DEFAULT_LIFECYCLE_PATH = Path("Results") / "claim-lifecycle.json"

STATUSES = ("submitted", "received", "approved", "paid", "failed")
# rank for monotonic advance; failed separate/terminal

@dataclass
class ClaimLifecycleRecord:
    claim_id: str
    status: str
    date: str          # journey date YYYY-MM-DD
    direction: str     # e.g. outbound / inbound / route summary
    amount_gbp: float | None = None
    updated_at: str    # ISO
    reported_paid_at: str | None = None

class LifecycleStore:
    def __init__(self, path: Path = DEFAULT_LIFECYCLE_PATH): ...
    def record_submitted(self, claim_id, *, date, direction, when=..., amount_gbp=None) -> ClaimLifecycleRecord: ...
    def apply_stage(self, claim_id: str, stage: str, when=...) -> ClaimLifecycleRecord | None: ...
    def get(self, claim_id: str) -> ClaimLifecycleRecord | None: ...
    def all(self) -> list[ClaimLifecycleRecord]: ...
    def open_for_table2(self) -> list[ClaimLifecycleRecord]: ...
    def mark_reported_paid(self, claim_ids: list[str], when=...) -> None: ...
```

`apply_stage` stage strings should accept the store values (`received`/`approved`/`paid`/`failed`) and ideally `ClaimMailStage` `.value` from callers later — store itself must not import `claim_mail`.

### Persistence pattern (reuse)

Mirror `trainline/adapters/ticket_drop.py::DropHashStore`: inject `Path`, load JSON if present, `mkdir(parents=True)`, rewrite whole file with `indent=2` + trailing newline. File shape: single JSON object map `{ "<claim_id>": { ...fields } }` (AD-18).

### Display vs store

Table 2 may show `submitted` as `in_flight` — **presentation only in CLI/ops_email (Story 9.4)**. Store never persists `in_flight`.

### Out of scope

- CLI `record_submitted` on live file (9.2)
- Gmail search refresh (9.3)
- `render_ops_email` Table 2 wiring + `mark_reported_paid` after send (9.4)
- Paper-ticket preprocessor; SQLite; cloud

### Prior art / do not reinvent

| Existing | Role |
| --- | --- |
| `tests/test_claim_lifecycle.py` | Pre-written 7.5 contract — **rewrite** to AD names |
| `trainline/adapters/gmail/claim_mail.py` | Stage values `received`/`approved`/`paid` — do not import here |
| `trainline/adapters/ops_email.py` | Pure renderer; leave alone this story |
| `Results/` gitignored | Durable local state |
| Deferred `7-5-claim-lifecycle-state.md` | Superseded — do not implement that story file |

### Automated tests

| File | Notes |
| --- | --- |
| `tests/test_claim_lifecycle.py` | Primary offline unit TDD for this story |
| pytest-bdd feature | Optional; Epic 7 store used unit style — prefer matching that |

### References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 9 / Story 9.1]
- [Source: `_bmad-output/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` — AD-18, AD-19]
- [Source: `_bmad-output/implementation-artifacts/epic-7-fr38-inbox-contract-2026-07-20.md`]
- [Source: `trainline/adapters/ticket_drop.py` — JSON rewrite idiom]

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent)

### Debug Log References

- RED: collection ImportError for missing `claim_lifecycle`
- Docstring mention of "gmail" tripped source-scan AC; rephrased to mail-client / browser-automation

### Completion Notes List

- Implemented `LifecycleStore` with AD-19 API (`record_submitted`, `apply_stage`, `open_for_table2`, `mark_reported_paid`).
- Default path `Results/claim-lifecycle.json`; statuses `submitted|received|approved|paid|failed`; `failed` terminal; monotonic rank.
- Rewrote offline tests from legacy 7.5 names; 10 passed; full suite 455 passed, 2 skipped.
- No CLI / Gmail / ops_email wiring (deferred to 9.2–9.4).

### File List

- `trainline/adapters/claim_lifecycle.py` (new)
- `tests/test_claim_lifecycle.py` (rewritten)
- `_bmad-output/planning-artifacts/epics.md` (Epic 9 GWT ACs)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/9-1-claim-lifecycle-store.md`

## Change Log

- 2026-07-27 — Story context created (ready-for-dev); supersedes deferred 7.5
- 2026-07-27 — Implemented lifecycle store; status → review
