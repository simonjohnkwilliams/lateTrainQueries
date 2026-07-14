"""Per-day max-payout optimiser — sole owner of feasibility + tie-break (AD-10).

``optimise(days, config) -> list[DayResult]`` is pure (AD-1): no I/O, no global
state, deterministic. For each day it selects the combination of at most one
outbound and one inbound claim that maximises total payout, subject to
feasibility, and breaks ties deterministically. Emits 0, 1, or 2 claims per day.

Cancellation-derived claims are NOT produced here — that is the gated path in
Story 1.5 (AD-6), off by default. This story ignores cancelled services.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trainline.engine.delay import band, calculate_delay, payout
from trainline.engine.models import (
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
    return [_optimise_day(day, per_day_cap) for day in days]


def _optimise_day(day: FetchedDay, per_day_cap) -> DayResult:
    # AD-5: a failed fetch is passed straight through, never optimised into a
    # clean no-claim.
    if day.status is not FetchStatus.OK:
        return DayResult(date=day.date, status=day.status, claims=())

    outbound_claims = _claimable(day.outbound)
    inbound_claims = _claimable(day.inbound)

    best = _best_candidate(outbound_claims, inbound_claims, per_day_cap)
    return DayResult(date=day.date, status=FetchStatus.OK, claims=best.claims)


def _claimable(services: tuple[Service, ...]) -> list[tuple[Service, Claim]]:
    """Return (service, claim) for every service that is claimable (>= 15 min).

    Skips cancelled services and services with no recorded destination actual
    (AD-3) — a missing actual is not delay 0. Sorted deterministically.
    """
    result = []
    for svc in services:
        if svc.cancelled or svc.actual_arrival is None:
            continue
        delay = calculate_delay(svc.actual_arrival, svc.scheduled_arrival)
        if band(delay) == band(0):  # Band.NONE — sub-15-min, not claimable
            continue
        result.append((svc, _to_claim(svc, delay)))
    result.sort(key=lambda sc: (sc[0].scheduled_departure, sc[0].rid))
    return result


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
