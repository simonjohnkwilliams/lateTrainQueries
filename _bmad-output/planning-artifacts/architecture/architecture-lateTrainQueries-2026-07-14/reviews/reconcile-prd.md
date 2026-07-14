# PRD ↔ Architecture Spine Reconciliation

**Reconciled:** 2026-07-14
**PRD:** `../../../prds/prd-lateTrainQueries-2026-07-14/prd.md` (+ `addendum.md`)
**Spine:** `../ARCHITECTURE-SPINE.md`

Scope note: the spine is deliberately tight (module boundaries, greenfield
migration, cancellation seam). Deferred infra/deployment (AWS, Terraform, roadmap
adapters) is **correctly** deferred and is **not** flagged here. This review only
surfaces PRD requirements or qualitative intent that the spine failed to *place*
or *govern*.

---

## Coverage check — every FR/NFR

| Req | Home in spine? | Notes |
| --- | --- | --- |
| FR1–FR5 | ✅ Capability map → `hsp_client` (AD-3/4/5/7) | Covered |
| FR6–FR10 | ⚠️ Placed (`engine`, AD-1/4) but tie-break determinism ungoverned | See Gap 3 |
| FR11 | ✅ AD-1, AD-8 | Covered |
| FR12 | ✅ AD-6 (gated) | Covered |
| FR13–FR14 | ✅ `storage`, AD-3 | Covered |
| FR15 | ⚠️ Bundled under AD-3 but ordering intent dropped | See Gap 4 |
| FR16–FR18 | ✅ `config`, `models`, AD-3 | Covered |
| FR19–FR21 | ✅ `tests/`, AD-7 | Covered |
| NFR1 | ✅ In `binds`, AD-5 | Covered |
| NFR2 | ❌ **Not in `binds`, not in Capability map** | See Gap 2 |
| NFR3 | ✅ AD-7 | Covered |
| NFR4 | ✅ AD-7 | Covered |
| NFR5 | ❌ Not placed (benign) | See Gap 5 |
| NFR6 | ✅ Stack (Python) | Covered |

`binds:` in the spine front-matter lists NFR1, NFR3, NFR4, NFR6 — **NFR2 and
NFR5 are silently absent.**

---

## Ranked gaps

### Gap 1 — OQ2 payout **cap** is a structural correctness nuance, mis-scoped as config `[HIGH]`

The spine's *Deferred* section reduces OQ2 to: *"`engine.delay.payout(...)` is
parameterised by ticket type so the resolution … is a config/data change, not a
structural one."*

That drops half of OQ2. Both the PRD (§9 OQ2c, FR9) and the addendum are explicit
that the **claim-stacking cap** is a question about the *objective function*, not
the payout value:

> "The optimiser sums two claims (FR9), so if (c) is capped the objective must
> cap too." (PRD §9)
> "The optimiser sums two claims; if SWR caps, the objective must cap too."
> (addendum)

A change from "maximise `sum(payout)`" to "maximise `min(sum(payout), ticket
value)`" is a change to the **shape of the optimisation** in `engine.optimiser`,
not a config/data swap in `engine.delay.payout`. The spine's framing would let an
implementer treat OQ2 as fully absorbed by a parameter, leaving the optimiser
objective unable to express a cap. NFR1 (correctness-first, never over-claim)
makes this the highest-value miss. No AD governs the objective-function contract
or its capped variant.

### Gap 2 — NFR2 (offline-first testing) has no home `[MED-HIGH]`

NFR2 — *"The default test invocation needs no network and no secrets; live API
tests are opt-in and skip cleanly without credentials"* — appears in neither
`binds:` nor the Capability → Architecture map. FR21 partially overlaps
("offline tests run with no network and no credentials by default"), and AD-7
covers idempotent/cached fetching, but **the opt-in live-test path that must
skip cleanly when credentials are absent is governed by nothing.** This is a
testability invariant (how the credential/network seam behaves under test), not
mere infra, so it is not covered by the deferral. It deserves either a binds
entry against FR21/AD-5 or an explicit convention.

### Gap 3 — Deterministic tie-break (FR10) placed but not governed; PRD internally inconsistent `[MED]`

FR10 is a **three-key** deterministic tie-break: *(a) fewer claim rows, then
(b) earliest outbound, then (c) earliest inbound.* But PRD §4 and addendum step 4
state only a **two-key** rule (earliest outbound, then earliest inbound) — the
"fewer claim rows" key is missing there. This internal PRD inconsistency was
never surfaced or reconciled by the spine.

The spine places FR10 in `engine/optimiser` (AD-1/AD-4) but **no invariant
requires deterministic, stable ordering of optimiser output.** The "fewer rows"
key is not cosmetic: it encodes product value (SM3 minimal manual effort — less
to file for the same money). A determinism AD would both lock the behaviour and
force the §4-vs-FR10 discrepancy to be resolved.

### Gap 4 — FR15 output ordering/grouping intent dropped `[LOW-MED]`

FR15 — *"grouped/sorted so a week reads at a glance (by date, then direction)"* —
is folded into the FR13–FR15 row under AD-3. But AD-3 governs only the
single-source data shape and the serialisation boundary; it says nothing about
sort/grouping. The Consistency Conventions cover CSV+JSON *format* but not
*order*. The "reads at a glance" qualitative intent (a usability nuance for the
sole human checker, tied to SM3) is unplaced.

### Gap 5 — NFR5 (trivial scale) unplaced `[LOW / benign]`

NFR5 ("scale is trivial; no performance engineering beyond the response cache")
is neither bound nor mapped. It is a non-constraint and its omission is harmless,
but for completeness the spine's silence means the "no perf engineering" licence
is undocumented — worth a one-line acknowledgement rather than an AD.

---

## Secondary observations (not ranked — within deferred/gated scope)

- **AD-6 omits the FR12 precedence rule.** The invariant *"actual late trains
  always take precedence over cancellation-derived claims"* is core FR12 content
  but AD-6's rule only covers gating + adapter/engine split. Since the path is
  gated off for MVP this is low-urgency, but the precedence should be captured
  where the fallback logic lands.
- **CM1/CM2 correctness counter-metrics** ("0 non-claimable/infeasible rows",
  "0 rows needing manual correction") are only implicitly satisfied via FR7/FR8
  and FR13. No explicit invariant asserts the optimiser never emits a
  non-claimable/infeasible row — acceptable, but it rests on implementation
  discipline rather than a governed rule.
