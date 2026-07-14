"""Story 1.5: gated cancellation fallback (FR12, AD-6, OQ1).

The fallback is OFF by default and gated on ``config.enable_cancellation_fallback``.
Production-enable is blocked on OQ1 (no real cancelled-train fixture yet), so
these tests use SYNTHETIC cancelled services only. Offline (NFR2).
"""
from types import SimpleNamespace

import pytest

from trainline.engine.models import (
    Band,
    Direction,
    FetchedDay,
    FetchStatus,
    Service,
)
from trainline.engine.optimiser import optimise


def _hm(h, m=0):
    return h * 60 + m


def outbound(dep, delay, rid, arr_sched=None, cancelled=False):
    arr_sched = arr_sched if arr_sched is not None else dep + 60
    actual = None if cancelled else arr_sched + delay
    return Service(
        rid=rid, direction=Direction.OUTBOUND, origin="GOD", destination="WAT",
        date="2026-05-28",
        scheduled_departure=dep, scheduled_arrival=arr_sched,
        actual_departure=None if cancelled else dep,
        actual_arrival=actual,
        cancelled=cancelled,
        reason="Cancelled" if cancelled else None,
    )


def _day(outbounds=(), inbounds=()):
    return FetchedDay(date="2026-05-28", status=FetchStatus.OK,
                      outbound=tuple(outbounds), inbound=tuple(inbounds))


_ON = SimpleNamespace(enable_cancellation_fallback=True)
_OFF = SimpleNamespace(enable_cancellation_fallback=False)


# --- AC1: flag OFF by default -> no cancellation-derived claims --------------
@pytest.mark.offline
def test_no_cancellation_claims_by_default():
    cancelled = outbound(_hm(8), 0, "c1", arr_sched=_hm(9), cancelled=True)
    catchable = outbound(_hm(8, 30), 0, "n1", arr_sched=_hm(9, 30))  # ran, on its own on-time
    result = optimise([_day([cancelled, catchable])])[0]  # config=None -> off
    assert result.claims == ()


@pytest.mark.offline
def test_no_cancellation_claims_when_flag_explicitly_off():
    cancelled = outbound(_hm(8), 0, "c1", arr_sched=_hm(9), cancelled=True)
    catchable = outbound(_hm(8, 30), 0, "n1", arr_sched=_hm(9, 30))
    result = optimise([_day([cancelled, catchable])], config=_OFF)[0]
    assert result.claims == ()


# --- AC2: flag ON -> next-catchable delay; actual-late precedence -----------
@pytest.mark.offline
def test_cancellation_derived_delay_uses_next_catchable():
    # Cancelled 08:00 (sched arrival 09:00). Next catchable departs 08:30 and
    # arrives 09:30 -> derived delay = 09:30 - 09:00 = 30 min (B30_59).
    cancelled = outbound(_hm(8), 0, "c1", arr_sched=_hm(9), cancelled=True)
    catchable = outbound(_hm(8, 30), 0, "n1", arr_sched=_hm(9, 30))  # arrives 09:30 on its own schedule
    result = optimise([_day([cancelled, catchable])], config=_ON)[0]
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.delay == 30
    assert claim.band is Band.B30_59
    assert claim.reason == "Cancelled"
    # The derived claim is anchored to the cancelled train's slot.
    assert claim.scheduled_departure == _hm(8)


@pytest.mark.offline
def test_actual_late_train_takes_precedence_over_cancellation():
    # Same leg has BOTH a cancelled service (would derive 30 min) and an
    # actual-late train (16 min). Actual always wins for the leg (AD-6).
    cancelled = outbound(_hm(8), 0, "c1", arr_sched=_hm(9), cancelled=True)
    catchable = outbound(_hm(8, 30), 0, "n1", arr_sched=_hm(9, 30))
    actual_late = outbound(_hm(7), 16, "a1")  # 16 min late, ran
    result = optimise([_day([cancelled, catchable, actual_late])], config=_ON)[0]
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.delay == 16  # the actual-late claim...
    assert claim.scheduled_departure == _hm(7)
    assert claim.reason is None  # ...not the cancellation-derived one (delay 30, "Cancelled")


@pytest.mark.offline
def test_cancellation_with_no_catchable_yields_no_claim():
    # Cancelled train with nothing running after it -> nothing to derive from.
    cancelled = outbound(_hm(23), 0, "c1", arr_sched=_hm(23, 45), cancelled=True)
    result = optimise([_day([cancelled])], config=_ON)[0]
    assert result.claims == ()


@pytest.mark.offline
def test_cancellation_derived_below_threshold_not_claimable():
    # Next catchable arrives only 5 min after the cancelled train's schedule.
    cancelled = outbound(_hm(8), 0, "c1", arr_sched=_hm(9), cancelled=True)
    catchable = outbound(_hm(8, 2), 0, "n1", arr_sched=_hm(9, 5))  # arrives 09:05
    result = optimise([_day([cancelled, catchable])], config=_ON)[0]
    assert result.claims == ()
