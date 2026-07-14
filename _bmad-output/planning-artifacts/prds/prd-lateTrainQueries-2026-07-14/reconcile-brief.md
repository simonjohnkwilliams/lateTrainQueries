# Input Reconciliation — Brief → PRD

**Input (source):** `briefs/brief-Late-Train-Query-Engine-2026-07-14/` (brief.md + addendum.md)
**Distillation checked:** `prds/prd-lateTrainQueries-2026-07-14/` (prd.md + addendum.md)
**Date:** 2026-07-14

## Verdict

The PRD is a faithful and in places *enriched* distillation of the brief. Every
brief FR-candidate, scope item, roadmap step, risk, and constraint is carried
forward, and the PRD adds material the brief did not have (success/counter
metrics, HSP JSON-shape reference, season-ticket band proportions, SWR form
constraints, 28-day filing window). The findings below are the handful of places
where a concrete claim was **changed**, or a qualitative nuance was **softened or
dropped**. Only one is materially important.

---

## 1. DISTORTION (highest importance) — payout band values changed

The single most important reconciliation item. The brief states one set of
payout percentages; the PRD emits a different set.

- **Brief addendum band table:** 15–29 min → **25%**, 30–59 → **50%**, 60–119 →
  **100% of single fare**, 120+ → **100% of return fare**. The brief presents
  these as *the* SWR bands (all "% of the single fare" except the top row).
- **PRD addendum band table:** for the open-day-return track the payable
  percentages **halve** until the top band: 15–29 → **12.5%**, 30–59 → **25%**,
  60–119 → **50%**, 120+ → **100% of return fare**.

The PRD explicitly flags this as a deliberate correction ("Correction vs. the
brief's addendum: the brief's table … is correct for a **single** ticket") and
notes the band *ordering* is unchanged, so the optimisation's "higher band wins"
logic is unaffected — only the emitted percentage labels differ.

**Why it matters:** anyone working from the brief's numbers will emit the wrong
percentages. The change is defensible and well-documented, but it is a genuine
alteration of a concrete claim, and it is unverified — the PRD spawns a **new
open question (OQ2)** that does not exist in the brief: the 12.5/25/50/100 track
is derived from published policy but "not yet verified against one of Simon's
real claims." The brief carried no such caveat on its numbers. This should stay
visible until confirmed against a real filing.

## 2. MINOR LOSS — worked-example arithmetic genericised

The brief addendum's worked examples carry explicit numbers:
- "Two 16-min-late outbounds … **(both 25%)**"
- "07:00 is 16 min **(25%)** vs 08:00 is 39 min **(50%)**"

The PRD addendum keeps the same examples but strips the percentages, replacing
them with "same band" / "higher band". This is a consequence of item 1 (the
percentages changed, so the old labels would be wrong), but it does remove the
concrete, traceable arithmetic a reader could check by hand. Acceptable, but the
PRD examples are now less self-checking than the brief's.

## 3. QUALITATIVE SOFTENING — the "no product answers the real question" framing

The brief's Problem Statement ends on a deliberately rhetorical market-gap
framing: *"There is no product today that answers the real question: 'Given
everything that ran on my route this week, what is the maximum I can legitimately
claim, and what do I type into the SWR form?'"* This states the intent as an
unmet need in the world.

The PRD preserves the concrete critique of the existing tool ("solves the wrong
problem"), but the "no product answers the real question" framing — the *why this
is worth building at all* note — is dropped. This is the kind of intent nuance a
bulleted FR structure silently loses. Low importance for a personal tool, but it
is the clearest qualitative idea that did not survive.

## 4. MINOR — explicit "Python" language constraint not restated

The brief's Constraints section states plainly: **"Python; depends on the
National Rail HSP API."** The PRD carries the HSP dependency everywhere but never
restates Python as an explicit constraint in the NFRs (it is only implied by the
brownfield-rewrite context and the AVG/`REQUESTS_CA_BUNDLE` NFR3). Arguably a
language choice belongs in the architecture doc, so this is a defensible
omission, but the concrete claim is technically absent from the PRD.

---

## Checked and confirmed faithfully carried (no gap)

- Payout-maximising optimisation over *all* services (not journeys caught) — §1, §4.
- Open-day-return premise as the justification for "any train I could have caught" — §3.
- Correctness-first priority ("never surface non-claimable/infeasible; never miss a claimable day") — Goals, NFR1, and *enhanced* into SM1–SM3 / CM1–CM2.
- Delay measured at destination arrival; Delay Repay 15 threshold — §4, addendum.
- Feasibility rule using **actual** arrival at WAT — FR8.
- Tie-break earliest outbound then inbound, with "keeps return options open" rationale — FR10, §4.
- 0/1/2 claim rows per day — FR9, §4.
- Cancellations as fallback only; actual late trains win — FR12, addendum.
- Cancellation delay formula (next-catchable-service mechanic) — FR12, addendum.
- HSP cancellation data-quality risk + need for real fixtures — OQ1 (brief risk carried).
- Rewrite (not preserve) the old-model test suite (>1 min / both-legs / worst-per-day) — FR20; matches the brief's explicit risk and the MEMORY behaviour-regression note.
- MVP surfaces band, not £ — FR14 + assumption (brief's "confirm that's enough (assumed yes)" carried).
- AVG TLS interception CA-bundle workaround — NFR3.
- Config-driven route/window (GOD⇄WAT not hard-coded) — FR16.
- Pure-core / seams-now-build-MVP-only architecture principle; no AWS/Terraform until needed — FR11, §7, addendum.
- Season-ticket data model must not be precluded — FR18 (PRD *adds* the proportion detail).
- Roadmap steps 1–5 (email → auto-file → ticket upload → photo/OCR → cloud/Lambda) — §8, order preserved; PRD adds a 6th (season-ticket support).
- CLI/script MVP acceptable; value is correctness not UI — §3.
- SWR form field mapping validation deferred to automation phase (screenshot when we get there) — OQ3.

## Net assessment

One item (band values, #1) is a substantive, deliberate, and flagged change that
carries an unverified assumption forward — keep OQ2 open. The rest are cosmetic
or belong downstream. No brief scope item, roadmap step, or constraint was lost.
