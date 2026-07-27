# Architecture-Spine Rubric Review — Late Train Query Engine (2026-07-27)

**Verdict: PASS-WITH-FIXES**

Reviewed: `ARCHITECTURE-SPINE.md` (updated 2026-07-27, release 6) against the
good-spine rubric, driving PRD + addendum, Epic 7 inbox contract
(`epic-7-fr38-inbox-contract-2026-07-20.md`), stories 7.4/7.5, and brownfield
code under `trainline/` (especially `gmail/claim_mail.py`, `ops_email.py`,
`cli.py --weekly-ops`). Scope note honoured: infra/deployment/AWS deferral is
intentional and is **not** counted as a hole.

Focus: **AD-18..AD-21** (claim lifecycle + Table 2) plus regression check on
AD-1..17 and prior rubric findings.

---

## Summary judgement

The 2026-07-27 spine extension is a coherent, hand-off-ready substrate for Epic
7.4/7.5. The four new ADs pin the real divergence points that would otherwise
split story implementations:

- **Separate mutable lifecycle from append-only audit (AD-18 + AD-16)** — prevents
  rewriting `filing-audit.jsonl` or inventing status inside `ops_email`.
- **Single writer via composition root (AD-19 + AD-8 + AD-2)** — cli-only mutation,
  pure `claim_mail` parse, no adapter-to-adapter imports; matches existing
  `test_import_boundaries.py` enforcement and shipped `claim_mail.py`.
- **Pure renderer retained (AD-20)** — ratifies brownfield `render_ops_email(…,
  table2=…)`; Table 1 + Table 2 in one email.
- **Weekly chain ordering (AD-21)** — lifecycle refresh before ops email; marker
  after email success; extends AD-17 without weakening it.

Prior rubric medium findings (OQ2 cap signature, hsp_client injectable seam,
tie-break totality, FR15 sort) are **resolved** in the current spine (AD-10,
Testing convention, AD-10 rule, Data & formats row).

One **medium** gap in AD-20 misstates FR37/FR39 Table 2 inclusion logic and
could let two legal implementations diverge on when `paid` claims appear or
vanish. Two smaller AD-18/19 specification gaps round out the fix list. None
block epic/story creation once folded in.

---

## Findings

### [medium] AD-20 Table 2 query uses `status != paid`; FR37/FR39 require “not yet **reported** paid”

**Divergence:** Story 7.5 AC3 and FR37/FR39 (SM5) distinguish **inbox paid**
from **reported in a sent digest**. A claim can be `paid` in lifecycle (PAYMENT
SENT seen) but must still appear in Table 2 **once** so the operator sees
payment confirmation, then be omitted on subsequent runs after
`reported_paid_at` is set post-email.

AD-20 Rule: *“cli builds Table 2 rows from claim_lifecycle open claims where
`status != paid`”* — two developers obeying the spine could:

1. **Dev A (AD-20 literal):** omit all `paid` records from Table 2 as soon as
   Gmail refresh sets `paid` — never surfaces payment in the weekly digest
   (violates FR37/SM5).
2. **Dev B (story 7.5 / PRD):** include `paid` until `mark_reported_paid` after
   successful email — correct FR39 idempotency for Table 2 omission.

**Fix:** In AD-18, add `reported_paid_at: datetime | null` (or equivalent) on
each record and a query helper `open_for_table2()` = actioned claims where
`reported_paid_at is null` (regardless of current status, including `paid`).
Update AD-20 Rule to: cli builds Table 2 from `open_for_table2()`, and after
successful ops email calls `mark_reported_paid` for every row whose status was
`paid` in that digest. Bind FR39 explicitly on AD-20/AD-21, not only AD-18
binds line.

---

### [medium] AD-18 conflates `submitted` and `in_flight`; Table 2 display mapping unpinned

**Divergence:** AD-18 lists both `submitted` and `in_flight` as store statuses.
Epic 7 contract and story 7.5 define **`in_flight` as the Table 2 label** for
“filed locally, no inbox mail yet”, while the **store** status after successful
file is `submitted`. Two implementations could:

- store `in_flight` in JSON (matching Table 2 verbatim), or
- store `submitted` and map to `in_flight` only at render time.

Both satisfy AD-18’s allowed-status list; Table 2 rows would differ in raw
status strings and transition tests would diverge.

**Fix:** Pin one canonical store enum in AD-18: persist `submitted | received |
approved | paid | failed` only; Table 2 maps `submitted → in_flight` at cli
compose time (per `7-5-claim-lifecycle-state.md` status table). Drop
`in_flight` from the persisted allowed set or mark it display-only.

---

### [medium] AD-19 “monotonic progression” lacks enforceable stage order

**Divergence:** AD-19 requires monotonic `apply_stage` but does not name the
ordering. Shipped `claim_mail.ClaimMailStage` and story 7.5 imply
`submitted < received < approved < paid`. Without a pinned order, two
`claim_lifecycle` implementations could disagree on:

- whether an out-of-order Gmail fetch (e.g. RECEIVED after APPROVED already
  stored) is a no-op vs an error;
- whether `failed` is a terminal overlay or a ranked stage;
- whether `submitted` can be overwritten by inbox stages (it should not regress).

**Fix:** One line in AD-19 Rule:
`RANK: submitted(0) < received(1) < approved(2) < paid(3); failed terminal;
apply_stage only if new_rank > current_rank (same rank: no-op).`

Cross-reference Deferred “failure-mail → failed” so `failed` does not compete
with inbox ranks until characterised.

---

### [low] Lifecycle default path naming: hyphen vs underscore

AD-18: `Results/claim-lifecycle.json`. Story 7.5 suggested layout:
`Results/claim_lifecycle.json`. Brownfield state dir consistently uses capital
`Results/` (cli, weekly_marker, claim_submission). The hyphen/underscore split
is a trivial but real story divergence.

**Fix:** Pick one filename in AD-18 (recommend `claim_lifecycle.json` to match
story 7.5 and Python module name).

---

### [low] AD-16 audit path casing still lowercase (`results/`) vs brownfield `Results/`

Pre-existing from AD-16; brownfield code and AD-18 use `Results/`. Not introduced
by AD-18..21 but worth aligning when touching lifecycle paths.

**Fix:** AD-16 default → `Results/filing-audit.jsonl`.

---

## AD-18..21 focused scorecard

| AD | Enforceable? | Prevents stated divergence? | Weakens AD-1..17? | Brownfield ratified? |
| --- | --- | --- | --- | --- |
| AD-18 | Yes (adapter + path + no audit rewrite) | Partial — missing `reported_paid_at` / enum clarity | No | Yes — new adapter; defers SQLite per story 7.5 |
| AD-19 | Yes (cli-only writer; no gmail import in store) | Partial — monotonic order unpinned | No — strengthens AD-2, AD-8 | Yes — `claim_mail.py` pure parse exists |
| AD-20 | Yes (pure renderer; cli composes rows) | **Partial — Table 2 inclusion rule wrong** | No — preserves AD-2 | Yes — `render_ops_email` already accepts `table2` |
| AD-21 | Yes (ordered chain + marker gate) | Yes for refresh-before-email | No — extends AD-17/AD-8 | Yes — current `--weekly-ops` lacks lifecycle step; AD-21 pins the insert |

---

## Full rubric scorecard

| Rubric criterion | Result |
| --- | --- |
| Fixes real divergence points for epics/stories below | **Partial** — lifecycle/Table 2 seams mostly pinned; Table 2 inclusion + store enum need tightening (medium) |
| Every AD Rule enforceable & prevents its divergence | **Pass** on AD-1..17, AD-21; **Partial** on AD-18..20 (gaps above) |
| Nothing Deferred lets two units diverge | **Pass** — failure-mail → `failed` explicitly deferred with AD-20 assumption; SQLite revisit named; no hidden Table 2 ambiguity in Deferred |
| Ratifies rather than contradicts brownfield where reused | **Pass** — claim_mail parser, ops_email renderer, Results/ layout, append-only audit, cli composition root |
| Covers driving PRD capabilities (FR37–FR39 slice) | **Partial** — FR37/FR38 well bound; FR39 Table 2 omission under-specified in AD-20 |
| No new AD weakens AD-1..17 | **Pass** |
| Every altitude dimension decided / deferred / OQ | **Pass** at feature altitude — paradigm, layers, stack, testing, lifecycle state, weekly ops chain decided; infra/deployment, failure-mail characterisation, SQLite, preprocessor deferred |

---

## Regression on prior review (2026-07-14)

| Prior finding | Status in 2026-07-27 spine |
| --- | --- |
| OQ2 cap reshapes optimiser objective | **Fixed** — AD-10 optional per-day cap |
| hsp_client offline seam (NFR2/FR21) | **Fixed** — Testing convention injectable seam |
| Tie-break inconsistency | **Fixed** — AD-10 three-level total order |
| FR15 sort order | **Fixed** — Data & formats row |

---

## Recommended action

Fold **three medium fixes** into the spine before story 7.4/7.5 dev:

1. `reported_paid_at` + `open_for_table2()` / `mark_reported_paid()` (AD-18,
   AD-20, FR39).
2. Canonical store statuses vs Table 2 display mapping (AD-18).
3. Explicit monotonic rank in AD-19.

Address low path-casing items inline. No re-architecture required; AD-18..21
structure is sound.

---

## Verdict rationale

**PASS-WITH-FIXES** — the spine is lean, coherent, and safe to hand to epic/story
creation after the Table 2 inclusion rule and lifecycle enum/rank clarifications.
Failures would be warranted only if AD-18..21 were absent or contradicted AD-2/AD-8;
neither applies.
