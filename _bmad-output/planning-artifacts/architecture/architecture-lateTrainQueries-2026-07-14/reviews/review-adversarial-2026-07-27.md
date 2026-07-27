# Adversarial Review — ARCHITECTURE-SPINE.md (Late Train Query Engine)

**Date:** 2026-07-27  
**Reviewer stance:** adversary. Goal: find pairs of units, each obeying *every* AD to the
letter, that still build incompatibly — with emphasis on AD-18..21 (lifecycle store,
mutation ownership, Table 2, weekly chain) and AD-2 (no adapter→adapter).

**Spine reviewed:** `ARCHITECTURE-SPINE.md` (release 6, updated 2026-07-27).

**Verdict:** **FAIL on the lifecycle / Table 2 slice.** AD-1..17 tightening (DayResult
return, origin-day minutes, fetch aggregation, tie-break, Band.NONE) closed the
Release 1 money-loss holes from the prior adversarial pass. AD-2 layering remains
genuinely tight for import arrows. **AD-18..21 introduce a new contradiction with
FR37/FR39 and with pre-written Story 7.5 tests**, plus several unpinned seams where
two AD-compliant builders produce incompatible lifecycle, Table 2, and weekly-chain
behaviour. Five material holes below; H1–H2 block correct Table 2 / idempotency.

---

## H1 — AD-20 Table 2 filter contradicts FR37/FR39 and Story 7.5 `[HIGH]`

**The two units:** `cli` Table 2 builder (reads AD-20); `claim_lifecycle.LifecycleStore`
+ Story 7.5 / `tests/test_claim_lifecycle.py` (reads FR37, FR39, AC3).

- **AD-20:** `cli` builds Table 2 rows from `claim_lifecycle` open claims where
  **`status != paid`**.
- **FR37 / Story 7.4 AC2:** Table 2 lists claims *not yet reported as successful (paid)
  in the last digest*, and **may show rows whose inbox status is `paid`** until that
  paid outcome has appeared in a sent digest.
- **Story 7.5 AC3 / tests:** `open_for_table2()` omits rows where
  **`reported_paid_at`** is set — a flag independent of `status == paid`.

**Divergence:** both readings are anchored in binding sources.

| Event | Dev A (AD-20 literal) | Dev B (FR37/39 + tests) |
| --- | --- | --- |
| Inbox reaches `PAYMENT SENT` | Row **drops out** of Table 2 immediately (`status == paid`) | Row **stays in** Table 2 with status `paid` |
| Digest sent including that paid row | N/A — already omitted | `mark_reported_paid(...)` sets `reported_paid_at` |
| Next weekly run | Claim never shown as paid in any digest | Claim omitted — FR39 satisfied |

Dev A satisfies AD-20 and violates FR37 (“follow-up until paid **reported**”).
Dev B satisfies FR37/FR39 and violates AD-20’s `status != paid` filter.
Acceptance tests in `tests/test_claim_lifecycle.py::test_open_for_table2_omits_reported_paid`
encode Dev B; the spine encodes Dev A. They do not compose.

**Fix (tighten AD-18 + AD-20):** add `reported_paid_at: datetime | null` to the lifecycle
record (AD-18). Replace AD-20’s filter with: *Table 2 rows come from
`open_for_table2()` — all claims where `reported_paid_at is null`, regardless of
inbox stage; display status may be `paid`.* Pin that `mark_reported_paid(claim_ids,
when)` runs in `cli` **after** a successful ops email send (AD-19/AD-21), for every
claim id whose Table 2 row had `status == paid` in that render.

---

## H2 — AD-18 record shape omits the FR39 idempotency field `[HIGH]`

**The two units:** `adapters/claim_lifecycle` built from AD-18; `cli` weekly idempotency
(FR39, AD-21) + Story 7.5.

- **AD-18** pins: claim id, statuses, `date`, `direction`, optional `amount`. No
  `reported_paid_at`, no query contract beyond “current status”.
- **Story 7.5 / tests** require `mark_reported_paid`, `open_for_table2()`, and
  omission keyed on **reported**, not **inbox-paid**.

**Divergence:** two AD-18-compliant stores are both legal:

1. **Store dev A:** query helper `open_claims() -> [row where status != paid]` — matches
   AD-20 wording; no `reported_paid_at` field needed.
2. **Store dev B:** adds `reported_paid_at`, `open_for_table2()` — matches tests;
   AD-20’s `status != paid` filter is wrong for this store but AD-18 does not forbid
   the extra field.

Downstream `cli` and `ops_email` cannot share one query without picking a winner.
Weekly re-runs (FR39) diverge: Dev A never surfaces paid-in-inbox claims in the digest;
Dev B shows them once, then omits after `mark_reported_paid`.

**Fix:** extend AD-18 Rule explicitly:

```text
Record fields: …, reported_paid_at (optional ISO timestamp).
Query: open_for_table2() → reported_paid_at is null.
Statuses paid in inbox remain in Table 2 until reported_paid_at is set.
```

Delete the `status != paid` phrasing from AD-20 (see H1).

---

## H3 — AD-21 lifecycle refresh: step boundary, failure policy, and `mark_reported_paid` timing unpinned `[HIGH]`

**The two units:** `cli._run_weekly_ops` chain orchestrator (AD-21, AD-8); `cli` post-email
bookkeeping (FR39, Story 7.5 AC3).

- **AD-21:** order is `… → file → lifecycle refresh → ops email`; completion marker
  **only after email succeeds**.
- **AD-19:** Gmail search → parse → `apply_stage` **before** ops email.
- **Neither AD** names: (a) what happens if lifecycle refresh fails, (b) when
  `mark_reported_paid` runs relative to marker/email, (c) whether refresh is a named
  function or folded into the email step.

**Divergences (all AD-compliant):**

1. **Refresh failure policy**
   - Dev A: refresh exception → abort chain, no email, no marker (mirrors file-step
     failure in current `cli.py`).
   - Dev B: refresh exception → log warning, email Table 1 + stale Table 2 anyway,
     marker on email success.
   Both satisfy AD-21’s ordering *when refresh succeeds*; neither AD forbids proceeding
   on refresh failure. Table 2 is wrong in Dev B; weekly marker is set in Dev B while
   lifecycle is stale — FR37 follow-up silently wrong until `--weekly-ops-force`.

2. **`mark_reported_paid` timing**
   - Dev A: call **before** `send_digest` (pre-mark ids about to appear as `paid`).
   - Dev B: call **after** successful send (Story 7.5 intent).
   If email fails after Dev A’s pre-mark, paid claims vanish from Table 2 without ever
   appearing in a digest — FR37 violated. Dev B is correct; Dev A is AD-21-compliant
   (AD-21 silent on this sub-step).

3. **Step placement**
   - Dev A: explicit `_run_lifecycle_refresh()` between `_run_weekly_file` and
     `_run_weekly_ops_email` (matches AD-21 diagram).
   - Dev B: refresh inside `_run_weekly_ops_email` before `render_ops_email`.
   Both mutate lifecycle only via `cli` (AD-19). Story boundaries and test seams
   diverge; a test mocking “refresh” misses Dev B’s embedding.

**Fix (tighten AD-21 + AD-19):** add explicit sub-rules:

- Lifecycle refresh failure → **non-zero exit, no ops email, no marker** (same strictness
  as file failure).
- `mark_reported_paid` → **only after successful ops email send**, ids = Table 2 rows
  rendered with `status == paid` in that send.
- Name the composition-root function (`refresh_claim_lifecycle_from_gmail`) and its
  place in the chain so Dev B’s embedding is out of spec.

---

## H4 — `submitted` vs `in_flight`: dual vocabulary for the same pre-inbox state `[MEDIUM]`

**The two units:** `claim_lifecycle` persistence (AD-18); `cli` Table 2 row builder +
`ops_email` renderer (AD-20, FR37).

- **AD-18** allows stored statuses: `submitted` **and** `in_flight`.
- **AD-20 assumption:** “missing inbox stages stay `in_flight` / `submitted`” — does not
  pick one for storage or display.
- **FR37 / Story 7.4:** Table 2 display set is
  `received | approved | paid | failed | in_flight` — **`submitted` is not a display
  status**; Story 7.4 maps “submitted locally, no mail” → **`in_flight`**.

**Divergence:**

| Layer | Dev A | Dev B |
| --- | --- | --- |
| Store after file | `status = submitted` | `status = in_flight` |
| Table 2 label | passes through `submitted` (AD-18 legal) | maps to `in_flight` (FR37 legal) |
| Ops email HTML | column shows “submitted” | column shows “in flight” |

Both obey AD-18 (both statuses allowed). FR37 expects one user-facing label. BDD
assertions on Table 2 status strings flake depending on builder.

**Fix (tighten AD-18 + AD-20):** *On `record_submitted`, persist `status = submitted`.
Table 2 display maps `submitted` → `in_flight`. Store never writes `in_flight` as a
stored status (reserve for display only), **or** drop `in_flight` from the stored enum
and derive it at render time.*

---

## H5 — AD-19 audit backfill + AD-2: two legal parsers, incompatible claim-id keys `[MEDIUM]`

**The two units:** `cli` one-shot backfill helper (AD-19); `claim_lifecycle` upsert on
live file (AD-19 path 1).

- **AD-19:** optional backfill from audit success lines is a **`cli` import helper
  only**; `claim_lifecycle` does not import Gmail.
- **AD-2:** no adapter imports another adapter — backfill must not live in
  `claim_lifecycle` if it imports `claim_submission` audit DTOs.
- **AD-16:** audit is append-only JSONL; shape owned by `claim_submission`.

**Divergence:** both AD-compliant, incompatible keys in the same store:

1. **Cli dev A:** backfill reads JSONL with ad-hoc `json.loads`; extracts claim id via
   regex on the `message` / `confirmation` string field.
2. **Cli dev B:** backfill calls a typed helper exported from `claim_submission`
   (`parse_audit_success(record) -> claim_id`) — legal because **`cli` may import
   everything** (AD-2).
3. **Live-file dev C:** `record_submitted` uses claim id from Playwright submit result
   object field `swr_claim_id`.

If regex (A) and submit result (C) disagree on normalisation (`SWR-0218-108-579` vs
embedded in a longer string), backfill creates a **second row** for the same physical
claim. `open_for_table2()` then duplicates follow-up rows; FR39 idempotent omission
applies to one id only. Both builders obey AD-2 (no adapter→adapter); AD-19 does not
pin a single claim-id extraction owner.

**Fix (tighten AD-19 + AD-16):** *Claim id for lifecycle keys is extracted in exactly
one place — a pure function (e.g. `engine.models` or `adapters/swr_mapping`) or a
`claim_submission.audit_claim_id(line)` helper imported only by `cli`. Backfill and
live-file paths must call the same function. Regex-only duplicate parsing is forbidden.*

---

## H6 — AD-18 default path vs AD-16 / codebase `Results/` convention `[LOW]`

**The two units:** `claim_lifecycle` default path (AD-18); `cli` / AD-16 audit defaults.

- **AD-18:** default `Results/claim-lifecycle.json` (hyphen).
- **AD-16 / `cli.py`:** `out_dir / "filing-audit.jsonl"` under `Results/` (no hyphen in
  filename pattern; story 7.5 also documents `claim_lifecycle.json` underscore).
- **Deferred:** SQLite revisit — until then, two files must align by convention.

**Divergence:** on case-sensitive filesystems, Dev A uses `claim-lifecycle.json`, Dev B
uses `claim_lifecycle.json` — two empty stores, Table 2 always empty in one path while
file step writes the other. Both satisfy AD-18 (path is default, configurable) if each
hardcodes their reading of “the default.”

**Fix:** pin one filename in AD-18 (`Results/claim-lifecycle.json`) and reference the
same string in Story 7.5 / tests; add a Consistency row.

---

## AD-2 — inward-only layering: no legal adapter→adapter divergence found `[PASS]`

**Checked pairs:** `claim_lifecycle` ↔ `gmail`; `ops_email` ↔ `claim_lifecycle`;
`claim_submission` ↔ `claim_lifecycle`; backfill ↔ store.

- AD-9 mermaid whitelist + “no adapter imports another adapter” leaves no legal edge
  between sibling adapters.
- Gmail parse stays in `gmail/claim_mail` (pure string→DTO); mutation stays in `cli`;
  render stays in `ops_email` — **topology is tight**.
- The **residual AD-2 risk is not an illegal import** but H5: `cli` may legally import
  two adapters’ conflicting parsers and compose incompatible keys without violating
  AD-2.

---

## AD-1..17 residual (brief)

Prior adversarial holes H1–H6 (optimise return type, cross-midnight base, None actuals,
fetch aggregation, band/payout, tie-break) are **addressed in the current spine** (AD-1
`list[DayResult]`, AD-4 origin-day base, AD-3 `int | None`, AD-5 all-legs rule, AD-10
tie-break, AD-11 `Band.NONE`). No new legal divergence pairs found there without
stretching the updated wording.

**Remaining low seam:** AD-6 cancellation fallback “on by default” (Deferred) vs a day whose
required leg is cancelled and excluded — AD-5-style distinct day status for
“cancelled-unanalysed” is still absent; not lifecycle-critical.

---

## Summary table

| ID | Area | Severity | AD-compliant pair diverges? |
| --- | --- | --- | --- |
| H1 | AD-20 filter vs FR37/FR39 | HIGH | Yes — Table 2 membership |
| H2 | AD-18 missing `reported_paid_at` | HIGH | Yes — query contract |
| H3 | AD-21 refresh / mark timing | HIGH | Yes — weekly chain + FR39 |
| H4 | `submitted` vs `in_flight` | MEDIUM | Yes — display vs store |
| H5 | Backfill claim-id extraction | MEDIUM | Yes — duplicate keys |
| H6 | Default filename | LOW | Yes — empty store |
| AD-2 | Adapter imports | PASS | No illegal pair |

---

## Recommended spine edits (minimal)

1. **AD-18:** add `reported_paid_at`; define `open_for_table2()`.
2. **AD-20:** replace `status != paid` with `open_for_table2()`; Table 2 may show
   `paid` until reported.
3. **AD-19:** add post-email `mark_reported_paid`; single claim-id extractor shared
   with audit backfill.
4. **AD-21:** refresh failure aborts chain; pin function name and ordering.
5. **AD-18/20:** pin stored `submitted` → displayed `in_flight` mapping.
6. **Consistency table:** one lifecycle filename under `Results/`.

Until H1–H3 are closed, Epic 7 stories 7.4 and 7.5 **will** build incompatible Table 2
and idempotency behaviour while each citing the spine as authority.
