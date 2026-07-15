"""Per-day max-payout optimiser — sole owner of feasibility + tie-break (AD-10).

``optimise(days, config) -> list[DayResult]`` is pure (AD-1): no I/O, no global
state, deterministic. For each day it selects the combination of at most one
outbound and one inbound claim that maximises total payout, subject to
feasibility, and breaks ties deterministically. Emits 0, 1, or 2 claims per day.

Cancellation fallback (AD-6, FR12) is a gated path: OFF unless
``config.enable_cancellation_fallback`` is true. OQ1 is now resolved (real
cancelled-train fixtures exist), so ``RunConfig`` enables it by default; this
function keeps its own default OFF so a bare ``optimise(days)`` is unchanged.
When on, an actual late train always takes precedence over a cancellation-derived
claim **for the same leg**.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trainline.engine.delay import band, calculate_delay, payout
from trainline.engine.models import (
    Band,
    Claim,
    DayResult,
    FetchedDay,
    FetchStatus,
    Service,
)

# Sentinel used in tie-break sort keys for a "missing" leg so that, at equal
# payout and row count, a candidate that actually has an (earlier) outbound or
# inbound is preferred deterministically.
_LATEST = float("inf")


@dataclass(frozen=True)
class _Candidate:
    claims: tuple[Claim, ...]
    total_payout: float
    outbound_departure: float  # scheduled dep minutes, or _LATEST if no outbound
    inbound_departure: float


def optimise(days: Iterable[FetchedDay], config=None) -> list[DayResult]:
    """Optimise each fetched day into a ``DayResult`` (FR9, FR10, FR11)."""
    per_day_cap = getattr(config, "per_day_cap", None)
    enable_cancellation = getattr(config, "enable_cancellation_fallback", False)
    return [
        _optimise_day(day, per_day_cap, enable_cancellation) for day in days
    ]


def _optimise_day(day: FetchedDay, per_day_cap, enable_cancellation) -> DayResult:
    # AD-5: a failed fetch is passed straight through, never optimised into a
    # clean no-claim.
    if day.status is not FetchStatus.OK:
        return DayResult(date=day.date, status=day.status, claims=())

    outbound_claims = _leg_claimables(day.outbound, enable_cancellation)
    inbound_claims = _leg_claimables(day.inbound, enable_cancellation)

    best = _best_candidate(outbound_claims, inbound_claims, per_day_cap)
    return DayResult(date=day.date, status=FetchStatus.OK, claims=best.claims)


def _leg_claimables(services, enable_cancellation):
    """Claimable (feasibility-service, claim) pairs for one leg/direction.

    Actual late trains take precedence for a leg (AD-6): only when a leg has no
    actual-late claim does the gated cancellation fallback contribute.
    """
    actual = _actual_claimables(services)
    if actual:
        return actual
    if enable_cancellation:
        return _cancellation_claimables(services)
    return []


def _actual_claimables(services) -> list[tuple[Service, Claim]]:
    """(service, claim) for every service claimable on its own actual arrival.

    Skips cancelled services and services with no recorded destination actual
    (AD-3) — a missing actual is not delay 0.
    """
    result = []
    for svc in services:
        if svc.cancelled or svc.actual_arrival is None:
            continue
        delay = calculate_delay(svc.actual_arrival, svc.scheduled_arrival)
        if band(delay) is Band.NONE:
            continue
        result.append((svc, _to_claim(svc, delay)))
    return _sorted(result)


def _cancellation_claimables(services) -> list[tuple[Service, Claim]]:
    """Cancellation-derived claims (AD-6, FR12) — gated; synthetic-tested (OQ1).

    For each cancelled service, delay = actual_arrival(next catchable) -
    scheduled_arrival(cancelled), where "next catchable" is the earliest service
    that actually ran departing at/after the cancelled train's scheduled
    departure. Represented as an effective ``Service`` (real schedule, next
    catchable's actuals) so it flows through the same feasibility/pairing logic.
    """
    ran = [s for s in services if not s.cancelled and s.actual_arrival is not None]
    result = []
    for cancelled in services:
        if not cancelled.cancelled:
            continue
        catchable = [
            s for s in ran
            if s.scheduled_departure >= cancelled.scheduled_departure
        ]
        if not catchable:
            continue
        nxt = min(catchable, key=lambda s: (s.scheduled_departure, s.rid))
        delay = calculate_delay(nxt.actual_arrival, cancelled.scheduled_arrival)
        if band(delay) is Band.NONE:
            continue
        effective = Service(
            rid=cancelled.rid,
            direction=cancelled.direction,
            origin=cancelled.origin,
            destination=cancelled.destination,
            date=cancelled.date,
            scheduled_departure=cancelled.scheduled_departure,
            scheduled_arrival=cancelled.scheduled_arrival,
            actual_departure=nxt.actual_departure,
            actual_arrival=nxt.actual_arrival,
            cancelled=False,
            reason=cancelled.reason,
        )
        result.append((effective, _to_claim(effective, delay)))
    return _sorted(result)


def _sorted(pairs):
    pairs.sort(key=lambda sc: (sc[0].scheduled_departure, sc[0].rid))
    return pairs


def _to_claim(svc: Service, delay: int) -> Claim:
    return Claim(
        date=svc.date,
        direction=svc.direction,
        origin=svc.origin,
        destination=svc.destination,
        scheduled_departure=svc.scheduled_departure,
        scheduled_arrival=svc.scheduled_arrival,
        actual_arrival=svc.actual_arrival,
        delay=delay,
        band=band(delay),
        reason=svc.reason,
    )


def _feasible(outbound: Service, inbound: Service) -> bool:
    """AD-10/FR8: inbound actual departure strictly after outbound actual arrival.

    Strict ``>`` (equal is NOT feasible), no interchange buffer. Both actuals
    must be known to establish feasibility.
    """
    if outbound.actual_arrival is None or inbound.actual_departure is None:
        return False
    return inbound.actual_departure > outbound.actual_arrival


def _capped(total: float, per_day_cap) -> float:
    return total if per_day_cap is None else min(total, per_day_cap)


def _best_candidate(outbound_claims, inbound_claims, per_day_cap) -> _Candidate:
    candidates: list[_Candidate] = [
        _Candidate(claims=(), total_payout=0.0,
                   outbound_departure=_LATEST, inbound_departure=_LATEST)
    ]

    # Single-leg options.
    for svc, claim in outbound_claims:
        candidates.append(_Candidate(
            claims=(claim,),
            total_payout=_capped(payout(claim.band), per_day_cap),
            outbound_departure=svc.scheduled_departure,
            inbound_departure=_LATEST,
        ))
    for svc, claim in inbound_claims:
        candidates.append(_Candidate(
            claims=(claim,),
            total_payout=_capped(payout(claim.band), per_day_cap),
            outbound_departure=_LATEST,
            inbound_departure=svc.scheduled_departure,
        ))

    # Feasible (outbound, inbound) pairs.
    for out_svc, out_claim in outbound_claims:
        for in_svc, in_claim in inbound_claims:
            if not _feasible(out_svc, in_svc):
                continue
            total = payout(out_claim.band) + payout(in_claim.band)
            candidates.append(_Candidate(
                claims=(out_claim, in_claim),
                total_payout=_capped(total, per_day_cap),
                outbound_departure=out_svc.scheduled_departure,
                inbound_departure=in_svc.scheduled_departure,
            ))

    # Maximise total payout; tie-break: fewer rows, earliest outbound, earliest
    # inbound (FR10). Deterministic total order (AD-10).
    candidates.sort(key=lambda c: (
        -c.total_payout,
        len(c.claims),
        c.outbound_departure,
        c.inbound_departure,
    ))
    return candidates[0]
