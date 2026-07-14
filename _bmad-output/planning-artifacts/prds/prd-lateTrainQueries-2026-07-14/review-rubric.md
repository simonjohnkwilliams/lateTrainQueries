# PRD Quality Review — Late Train Query Engine

## Overall verdict

This is a genuinely good lean PRD: it has a real thesis (the existing tool solves the wrong problem), a tightly-scoped MVP, product-specific NFRs, and honest gating of the one blocked feature (FR12/OQ1). It is close to build-ready. What is at risk is the **payout semantics** at the heart of the optimisation: "maximum total payout (sum of bands)" is stated loosely enough that an implementer could reasonably build two different objective functions, and the real-world validity of stacking two claims against one open day return is assumed rather than pinned. Tighten the payout/summation model and one feasibility edge and this is safe to hand to epics.

**Gate: PASS-WITH-FIXES.**

## Decision-readiness — strong

A decision-maker can act on this. The core bet is stated as a rewrite, not a feature list ("solves the wrong problem", §1). Trade-offs are named with what was given up: cancellations are explicitly a fallback that loses to real late trains (§4, FR12); the band-track correction vs the brief is called out with its reasoning (addendum, "Correction vs. the brief's addendum"). Open Questions are actually open — OQ1 genuinely blocks FR12 and says why (no HSP flag, no fixture), rather than being rhetorical. The Rejected/superseded section (addendum) records paths not taken (journey-matching, single tickets). No smoothing-to-neutral.

## Substance over theater — strong

Almost no furniture. No persona theater (one user, correctly). NFRs are product-specific and earned, not boilerplate: AVG TLS interception + `REQUESTS_CA_BUNDLE` (NFR3), offline-first testing (NFR2), "scale is trivial, no performance engineering" (NFR5) — the PRD refuses to invent an NFR where none is warranted, which is the opposite of NFR theater. The Vision (§1) could not be swapped into another PRD; it is specific to Simon's commute and the money mechanic.

### Findings
- **low** SM3 target ("Run one command, eyeball the output") is a description, not a measure (§2). *Fix:* acceptable for hobby stakes; optionally phrase as a bound (e.g. "single invocation, no manual data edits").

## Strategic coherence — strong

There is a clear arc: correctness-maximising claim extraction now, additive automation later behind fixed seams (§7, §8). Feature priority follows the thesis — the optimisation engine (FR6–FR11) is MVP core, automation is explicitly deferred and ordered. Success metrics validate the thesis (correctness/completeness, SM1/SM2) rather than measuring activity, and counter-metrics (CM1/CM2) guard against gaming SM2 by emitting speculative rows. The MVP scope kind is coherently "problem-solving," and the seam design keeps later phases from being rewrites.

## Done-ness clarity — adequate (this is where the fixes live)

Most FRs carry a testable consequence: FR6 (clamp early/on-time to 0), FR7 (discard sub-15), FR8 (a concrete inequality), FR10 (deterministic tie-break), FR3 (all RIDs not `[0]`). FR21/FR19 make the correctness harness itself a deliverable. But the objective function — the single most important thing to get right in a "correctness first" product — is under-specified in three ways:

### Findings
- **high** Payout base and claim-stacking are assumed, not specified (§4, FR9, addendum band table). The model files up to two rows/day and sums their payouts, but the PRD never states (a) that SWR permits two separate Delay Repay claims against one open day return, nor (b) what each band is a percentage *of* — full return fare per claim, or a split. At the extreme the objective yields 100% + 100% = 200% of return fare, which is exactly the kind of over-claim NFR1/CM1 forbid. OQ2 only verifies the *track values* (12.5/25/50/100), not the legitimacy of summing two claims. *Fix:* add an explicit `[ASSUMPTION]`/OQ: "each delayed journey on an open day return is separately claimable; each pays the return-track % of the return fare; two claims may stack." Confirm against one real filing.
- **medium** "Sum of bands" is imprecise for an optimiser (FR9, addendum step 3). A band is an ordinal label; the objective must sum *payout percentages*. Two 12.5% legs (25% total) must be comparable against one 50% leg. State that the optimiser sums the numeric percentage each band maps to. *Fix:* define `payout(band)` numerically and say the objective maximises `Σ payout`.
- **medium** FR8 feasibility has an unhandled boundary and no interchange buffer (§4, FR8, addendum step 2). Strict `>` means equal actual times are silently infeasible, and a 0-minute WAT turnaround counts as feasible — unrealistic for a real change of platform. *Fix:* decide and state a minimum interchange margin at WAT (even if 0), and define the equal-time tie.
- **medium** Tie-break (FR10) is phrased only for pairs. It does not say how to break a tie between a pair and a single-leg of equal total, or between two single-leg results. *Fix:* extend FR10 to cover single-leg and mixed cases (e.g. prefer more legs? prefer earliest?).
- **low** SM2 ("0 claimable days missed") is not independently measurable without a ground-truth reference — the tool is the only thing computing claimability. *Fix:* note how a miss would be detected (e.g. spot-check against SWR site for the SM1 week).

## Scope honesty — strong

Omissions are explicit, not inferred. Out-of-scope AWS/Terraform is stated twice (§7, §8, addendum). Roadmap is ordered and clearly deferred. Rejected paths are recorded (addendum). Inline `[ASSUMPTION]` tags appear on the real inferences (band track, £-vs-band, 28-day window). Open-items density is low and appropriate for the stakes; nothing here blocks the MVP except the already-gated FR12. One gap: assumptions are tagged inline but there is no consolidated Assumptions Index — tolerable at this size (see Mechanical notes).

## Downstream usability — adequate

This PRD is chain-top (feeds epics → architecture → stories), so traceability matters more here than for a standalone. FR IDs are contiguous and unique (FR1–FR21); SM/CM/NFR/OQ IDs are clean; cross-references (§7, §9, addendum, FR12↔OQ1) all resolve. The addendum grounds the JSON shapes in real fixtures, which is exactly what architecture will need. Sections mostly stand alone.

### Findings
- **medium** No Glossary despite chain-top status (whole PRD). Load-bearing domain nouns — *claimable*, *band*, *feasible*, *open day return*, *next catchable service*, *destination arrival* — are defined inline but scattered. A short Glossary would let epic/story extraction pull each term without re-reading §4 + addendum. *Fix:* add a 6–8 term Glossary; it doubles as the single source for the payout definitions above.

## Shape fit — strong

Correctly shaped as a single-operator capability spec: no User Journeys (right call for a solo CLI — UJs would be overhead), operational rather than user-experience success metrics, rigor kept light. It is neither over-formalized (no invented personas/UX flows) nor under-formalized (the core algorithm is specified, not waved at). The addendum carries implementation-depth detail out of the narrative cleanly. Good instinct throughout.

## Mechanical notes

- **Glossary:** absent (see Downstream usability). Term usage is otherwise consistent — "band", "claimable", "feasible", "open day return" do not drift in case or meaning across §4, FRs, and addendum.
- **ID continuity:** FR1–FR21 contiguous, no gaps or duplicates; SM1–3, CM1–2, NFR1–5, OQ1–3 all clean. Cross-refs (FR11→§7, FR12→OQ1/§9, FR18→§8, addendum links) resolve.
- **Assumptions roundtrip:** inline `[ASSUMPTION]` tags in §9 are not collected into a dedicated index, and OQ2 carries an `[ASSUMPTION]` tag inline. Low priority at this size, but a small Assumptions Index would tidy the roundtrip.
- **Fixtures:** addendum notes all recorded fixtures are 2026-05-28 and none contain a cancellation — consistent with OQ1. Accurate brownfield reference.
