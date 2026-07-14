# Adversarial Review — ARCHITECTURE-SPINE.md (Late Train Query Engine)

**Reviewer stance:** adversary. Goal: find pairs of units, each obeying *every* AD to the
letter, that still build incompatibly. Ranked by real risk for a lean personal CLI whose
entire purpose is *not silently missing claimable money*.

**Verdict:** the layering ADs (AD-1, AD-2, AD-8, AD-9) are genuinely tight — I could not
construct a legal divergence there. The **data-shape and status contracts** (AD-3, AD-4,
AD-5) are under-specified at exactly the seams that matter, and there is one **internal
contradiction in the spine itself**. Six material holes below.

---

## H1 — `optimise` signature vs data-flow: no-claim/fetch-status days cannot be represented `[HIGH]`

**The two units:** `engine.optimiser` built to the AD-1 signature; `cli` / `storage` built
to the data-flow diagram.

- AD-1 (and the Capability Map) pin `engine.optimise(services, config) -> list[Claim]`.
- The data-flow diagram (line 130) says `engine.optimise -> "list of Claim + DayResult"`.
- AD-5 says `DayResult` carries `fetch_status`, and a fetch-failed day must never read as a
  clean no-claim.

**Divergence:** these are mutually inconsistent and both are "the spec."
1. `list[Claim]` structurally has no slot for a *no-claim* day. A day that was fetched fine
   and had nothing claimable simply vanishes from the return value — indistinguishable from
   a day that was never requested. The "analysed, nothing to claim" state (the reassuring
   output a claims tool exists to produce) has no representation.
2. `fetch_status` is knowledge that lives in `hsp_client`, not `engine`. If `optimise`
   receives only `services` (the ones that fetched OK), it *cannot* emit a `FETCH_FAILED`
   `DayResult` — it never saw the failed day. So either the engine invents fetch_status it
   doesn't have (violates AD-5's intent), or the adapter owns `DayResult` (fine) but then
   `optimise` returning `list[Claim]` throws the day identity away before the merge.

Two developers reading the same spine legitimately build `optimise -> list[Claim]` and a
`cli` that expects `list[DayResult]`. They do not compose.

**Fix (tighten AD-1 + AD-5):** make `DayResult` the unit of return and the single carrier of
day identity + status:
`optimise(days: list[DayInput], config) -> list[DayResult]`, where `DayInput` is produced by
`hsp_client` per requested day and already carries `fetch_status` + its `Service`s, and
`DayResult` has `date`, `fetch_status` (passed *through* unchanged — engine never authors it),
and `claim: Claim | None`. Delete the `-> list[Claim]` phrasing from AD-1 and the Capability
Map so there is one signature.

---

## H2 — AD-4 "minutes since midnight" has no shared day-base; cross-midnight breaks `calculate_delay` `[HIGH]`

**The two units:** `hsp_client` (owns `HHMM`→int and cross-midnight per AD-4);
`engine.delay.calculate_delay` (does "integer arithmetic only", `actual - scheduled`).

**Divergence:** "int minutes-since-midnight" is satisfied by *any* value in `0..1439`, but
it does not fix a *base*. For a 23:50→00:15 inbound leg:
- `hsp_client` dev A stores both as raw minutes-since-midnight: `gbtt_pta = 1450`,
  `actual_ta = 15`. `calculate_delay = 15 - 1450 = -1435` → looks 24h early → **silent
  no-claim on a genuinely late train.**
- `hsp_client` dev B offsets only the *arrival* past midnight by +1440 but forgets the same
  base for scheduled → `actual = 1460`, `scheduled = 15` → `+1445` → top band → **false
  giant claim.**

Both obey AD-4 to the letter ("hsp_client owns cross-midnight; engine does integer
arithmetic"). The letter never says the two operands must share a monotonic base, and never
says *whether* `calculate_delay` or `hsp_client` is responsible for the wrap. It reads as
two owners of one concern.

**Fix (tighten AD-4):** state the invariant explicitly — *within one `Service`, `actual_ta`
and `gbtt_pta` are on the same origin-day base such that a normal arrival satisfies
`0 <= actual - scheduled` and a cross-midnight arrival is stored as `minutes + 1440` (may
exceed 1439)*. `calculate_delay` is then a pure subtraction and is the *sole* delay owner;
`hsp_client` performs no delay math. Add a guard: `calculate_delay` treating any result
`< -MAX_EARLY` as a base error (raise, not silently drop).

---

## H3 — Missing/`None` actual time and the `cancelled` sentinel are unpinned `[HIGH]`

**The two units:** `engine.models.Service` + `hsp_client` (populates it, AD-3/AD-6);
`engine.optimiser`/`delay` (consumes times as ints, AD-4).

**Divergence:** AD-6 says `hsp_client` sets `Service.cancelled` from *empty actual times* +
`late_canc_reason`. So a cancelled (or not-yet-arrived) service has **no** actual arrival.
But `Service.actual_ta` is "int minutes." What goes in the empty slot?
- `hsp_client` dev picks `None` → `calculate_delay = None - gbtt_pta` → **TypeError, run
  aborts a leg** (and AD-5 only promised fetch failures don't abort — this is a *parse* path).
- `hsp_client` dev picks `0` or `-1` sentinel → `calculate_delay` = large negative → looks
  early → **silently dropped**, the exact failure mode AD-5 exists to prevent, one layer down.

Nothing in any AD requires the optimiser to check `cancelled`/missing *before* arithmetic,
and nothing pins the empty representation. Both units are AD-compliant.

**Fix (tighten AD-3 + AD-4):** type it as `actual_ta: int | None`, define `None` as the
*only* legal "no actual arrival" value (no numeric sentinels), and add a rule: *the engine
must exclude any `Service` where `cancelled or actual_ta is None` from normal delay
computation.* See H6 for what happens to the day when a required leg is so excluded.

---

## H4 — `fetch_status` per-day vs per-service: partial-leg failure silently degrades to no-claim `[HIGH]`

**The two units:** `hsp_client` (records status, AD-5); the merge/mapper that sets
`DayResult.fetch_status`.

**Divergence:** AD-5 says status is recorded "per-day/per-service" — *both* granularities,
with no aggregation rule. A claimable day needs **both legs** (per the project's both-legs
threshold rule). If leg-1's service-detail fetch succeeds and leg-2's fails:
- Aggregator dev A: "any required fetch failed → day = `FETCH_FAILED`." Correct.
- Aggregator dev B: "the *metrics/day* fetch succeeded, an individual service-detail miss
  just means no arrival data" → leg-2 delay treated as on-time → **day emitted as clean
  NO_CLAIM.** Money missed invisibly — the precise thing AD-5 was written to stop, defeated
  through the unspecified aggregation from per-service to per-day.

Both obey AD-5 literally (a `fetch_status` exists and no clean no-claim was emitted *for the
failed fetch itself* — dev B just didn't classify it as failed).

**Fix (tighten AD-5):** define the aggregation and its owner. *A `DayResult` may be emitted
as claim/no-claim only if **every** required leg/service for that day fetched successfully;
if any required fetch failed, `fetch_status = FAILED` and no claim/no-claim verdict is
produced.* Name the owner (the cli/mapper merge point), not "somewhere."

---

## H5 — `band`/`payout` contract: no-claim band, signature arity, and return unit all ambiguous `[MEDIUM]`

**The two units:** `engine.delay.band`/`payout`; `engine.optimiser` (calls them to rank).

**Divergences (three, same seam):**
1. **No-claim band value.** `band(delay)` for a sub-threshold delay returns *something*
   (`None`? `"NONE"`? `Band.NONE`?). `payout(None)` → `KeyError`/crash, or `0`? The optimiser
   calls `payout(band(delay))` on *every* candidate to find the max; the no-claim case is the
   common case. Unpinned → crash vs 0.
2. **Signature arity.** Structural seed pins `payout(band)`; OQ2 says `payout` is
   *parameterised by ticket type*. One dev builds `payout(band)`, the other builds an
   optimiser calling `payout(band, config)`. Direct signature clash.
3. **Return unit / meaning.** "band as a named value with a numeric payout" — is the number a
   *percentage* (25/50/100) or *absolute pence*? The optimiser maximises "payout"; if `band`
   yields a percentage but the optimiser needs absolute money (fares differ by ticket per
   OQ2), the ranking is wrong whenever two days have different fare bases. Also float
   percentages reintroduce non-determinism into ties (H6).

**Fix (tighten the payout convention + OQ2):** pin one signature and unit:
`payout(band, fare_context) -> int` in **pence**; define an explicit `Band.NONE` with
`payout == 0` (never `None`/exception) so ranking is total; state that the optimiser
maximises the integer-pence payout.

---

## H6 — Optimiser determinism: tie-break rule, feasibility owner, and cancelled-leg-with-flag-off `[MEDIUM]`

**The two units:** `engine.optimiser`; `adapters/config` (owns route/window) and `storage`
(FR15 "sorted") / the BDD suite (FR19-21).

**Divergences:**
1. **Tie-break is named as a capability (FR10) but no AD pins the rule.** When two feasible
   services yield equal max payout, dev A picks earliest scheduled departure, dev B picks
   latest / by delay. If candidates are held in a `set`/`dict`, the choice follows hash
   order → **different `Claim` chosen run-to-run** → non-idempotent CSV/JSON output, flaky
   BDD, and it undercuts NFR4's idempotency spirit. All AD-compliant (no determinism AD).
2. **Feasibility window has two possible owners.** `config` owns the time window and
   `hsp_client` fetches by it; the optimiser also decides which services are "feasible."
   Inclusive-vs-exclusive boundary disagreement between the config filter and the optimiser
   filter drops or double-counts a boundary service. One concern, two owners.
3. **Cancelled required leg with AD-6 flag OFF.** AD-6 gates the *fallback delay*, but is
   silent on what the day *becomes* meanwhile. With the flag off, a day whose required leg is
   `cancelled` (H3-excluded) computes on the surviving leg → **clean NO_CLAIM**, silently
   burying a real cancellation claim — again the AD-5 failure mode, uncovered because there
   is no status for "cancelled, not analysable yet."

**Fix (add one AD "Optimiser is deterministic & total"):** `optimise` is a pure deterministic
function — iterate services in a defined order (scheduled departure, then RID); tie-break
equal payouts by `(earliest departure, then RID)`. Feasibility is filtered in exactly one
place (the optimiser) against a config window with a stated inclusive/exclusive rule;
`hsp_client` only over-fetches, never final-filters. And mirror AD-5 for cancellations: a day
with a cancelled *required* leg and the fallback flag off is emitted with a distinct status
(e.g. `CANCELLED_UNANALYSED`), never a clean NO_CLAIM.

---

## What's genuinely tight (no legal divergence found)

- **AD-1 / AD-2 / AD-9** — the pure-core + inward-only + explicit import-arrow set is
  airtight; "no adapter imports another adapter" plus the mermaid whitelist leaves no room
  for two modules to build against incompatible layering.
- **AD-8** — single composition root with future roots as *additional* roots calling the
  same `optimise` is unambiguous.
- **AD-7** — greenfield + the two must-keep behaviours (NFR3 TLS bundle, NFR4 idempotent
  fetch) are concrete and owned.

The weakness is uniformly in the **payload contracts** (AD-3/4/5 + the payout/optimiser
conventions), not the topology. Closing H1–H4 removes the money-loss and crash paths; H5–H6
remove non-determinism and wrong-ranking.
