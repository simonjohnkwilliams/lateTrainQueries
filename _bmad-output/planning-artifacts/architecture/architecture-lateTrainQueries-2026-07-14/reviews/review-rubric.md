# Architecture-Spine Rubric Review — Late Train Query Engine

**Verdict: PASS-WITH-FIXES**

Reviewed: `ARCHITECTURE-SPINE.md` (2026-07-14) against the good-spine rubric, the
driving PRD + addendum, and the brownfield `TrainLine/*.py` being replaced.
Scope note honoured: infra/deployment/AWS deferral is intentional and is **not**
counted as a hole.

## Summary judgement

This is a genuinely lean, coherent spine that is safe to hand to epic/story
creation. The hexagonal boundaries are real and enforceable, all 21 FRs are
mapped, and the correctness-critical seams are pinned:

- **AD-5 (fetch-failure ≠ no-claim)** directly defends SM2/CM1 — the money-losing
  failure mode of the old tool — and is enforceable via `DayResult.fetch_status`.
- **AD-7** ratifies the two brownfield behaviours worth keeping (NFR3 AVG-TLS
  `REQUESTS_CA_BUNDLE`, NFR4 idempotent skip-if-cached fetch) while discarding
  the inverted old model. Confirmed against `TestFileGenerator.py`: the old
  `rids[0]`-only extraction (FR3), `>1 min` threshold, both-legs-drop, and
  worst-per-day pick are correctly superseded, and the old
  `tests/test_late_train_pipeline.py` + `late_trains.feature` are slated for
  rewrite (FR20) — a legitimate greenfield replacement, not a violation.
- **AD-1/AD-2/AD-9** give a checkable import rule ("no adapter imports another
  adapter"; engine imports no I/O) that prevents layering divergence.
- **AD-4** pins integer minutes-since-midnight and, crucially, assigns
  cross-midnight ownership to `hsp_client` — a subtle real divergence point.
- **AD-6** gates the cancellation path off until OQ1, preventing unverified logic
  shipping.

Findings below are all medium/low; none block hand-off.

## Findings

### [medium] OQ2 stacking cap is deferred as "config", but it reshapes the optimiser objective
The Deferred section says `payout(...)` is parameterised by ticket type so OQ2
"is a config/data change, not a structural one." That holds for the band→percent
values, but **not** for OQ2(c): if SWR caps a day at ticket value, the objective
changes from `maximise Σ payout` to `maximise min(Σ payout, cap)`. A cap alters
which combination wins and interacts with the FR10 tie-break (fewer-rows-first
can flip once two legs are capped to equal a single leg). Two story
implementations could diverge on whether/where the cap applies. **Fix:** have the
spine pin the optimiser objective signature now to accept an optional per-day cap
(applied inside `engine.optimiser`), so resolving OQ2(c) is a value change, not a
re-architecture. Low blast radius today (band-only output + SM1 manual verify),
hence medium not high.

### [medium] No invariant enforces offline/seam-testability of the `hsp_client` adapter (NFR2 / FR21)
`binds` omits NFR2, and the capability map routes FR19–FR21 through AD-7 only
(the greenfield rule). AD-1 makes the *engine* trivially offline-testable, but
nothing pins how `hsp_client` is exercised without network/credentials — the
seam a story needs to honour "offline tests by default, live tests opt-in."
Stories could diverge (monkeypatch `requests` vs. inject a fetch callable vs.
read cache fixtures). **Fix:** add a one-line convention or AD — the HTTP call is
an injectable/replaceable seam and default tests read recorded fixtures — binding
NFR2/FR21.

### [low] Tie-break definition is inconsistent across sources; spine pins neither
PRD FR10 orders the tie-break as (a) fewer rows, (b) earliest outbound, (c)
earliest inbound, while addendum step 4 and PRD §4 say only "earliest outbound
then earliest inbound" (no fewer-rows rule). Determinism is an NFR1 correctness
invariant, yet the spine leaves the ordering to the algorithm layer without
naming the canonical form. **Fix:** state the authoritative tie-break ordering
(FR10's three-level rule) once, so `engine.optimiser` has a single source.

### [low] Minor coverage gaps in Consistency conventions
FR15 sort order (by date, then direction) and NFR5 (trivial scale) are unbound.
NFR5 needs nothing. FR15's ordering is a determinism-of-output detail that would
sit naturally in the Data & formats row — worth one clause so output ordering is
not a story-by-story choice.

## Rubric scorecard

| Rubric criterion | Result |
| --- | --- |
| Fixes real divergence points for epics/stories, misses none | Pass — one testability seam under-specified (medium) |
| Every AD Rule enforceable & prevents its divergence | Pass — all 9 ADs checkable |
| Nothing Deferred lets two units diverge | Partial — OQ2 cap can reshape the objective (medium) |
| Ratifies rather than contradicts brownfield where reused | Pass — AD-7 greenfield decision honoured; NFR3/NFR4 re-implemented |
| Covers the driving PRD's capabilities | Pass — FR1–FR21 all mapped; NFR2 the only under-bound NFR |
| Every owned dimension decided / deferred / open | Pass — testability strategy is the one soft spot |

Recommended action: fold the two medium fixes (OQ2 cap in the objective
signature; adapter testability seam/NFR2) into the spine before story creation;
the low findings can be addressed inline. No re-architecture required.
