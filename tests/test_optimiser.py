"""Story 1.4: feasibility, max-payout optimisation, tie-break (FR8-FR11, AD-10).

Offline unit tests grounded in the PRD addendum's worked examples. Pure engine
logic, no network/creds (NFR2).
"""
import pytest

from trainline.engine.models import (
    Direction,
    FetchedDay,
    FetchStatus,
    Service,
)
from trainline.engine.optimiser import _feasible, optimise


def _hm(h, m=0):
    return h * 60 + m


def outbound(dep, delay, rid, arr_sched=None):
    """GOD->WAT service departing `dep`, arriving `delay` min late at WAT."""
    arr_sched = arr_sched if arr_sched is not None else dep + 60
    return Service(
        rid=rid, direction=Direction.OUTBOUND, origin="GOD", destination="WAT",
        date="2026-05-28",
        scheduled_departure=dep, scheduled_arrival=arr_sched,
        actual_departure=dep, actual_arrival=arr_sched + delay,
    )


def inbound(dep, delay, rid, arr_sched=None, dep_actual=None):
    """WAT->GOD service departing WAT `dep`, arriving `delay` min late at GOD."""
    arr_sched = arr_sched if arr_sched is not None else dep + 60
    return Service(
        rid=rid, direction=Direction.INBOUND, origin="WAT", destination="GOD",
        date="2026-05-28",
        scheduled_departure=dep, scheduled_arrival=arr_sched,
        actual_departure=dep if dep_actual is None else dep_actual,
        actual_arrival=arr_sched + delay,
    )


def _day(outbounds=(), inbounds=(), status=FetchStatus.OK, date="2026-05-28"):
    return FetchedDay(date=date, status=status,
                      outbound=tuple(outbounds), inbound=tuple(inbounds))


def _one(day):
    results = optimise([day])
    assert len(results) == 1
    return results[0]


# --- AC1: feasibility (FR8) -------------------------------------------------
@pytest.mark.offline
def test_feasible_requires_inbound_departure_after_outbound_arrival():
    out = outbound(_hm(7), 20, "o1")            # arrives WAT 20 late
    in_ok = inbound(_hm(18), 20, "i1")          # departs WAT 18:00 — after
    in_bad = inbound(_hm(6), 20, "i2")          # departs WAT 06:00 — before
    assert _feasible(out, in_ok) is True
    assert _feasible(out, in_bad) is False


@pytest.mark.offline
def test_equal_times_are_not_feasible():
    out = outbound(_hm(7), 0, "o1", arr_sched=_hm(8))   # actual arrival == 08:00
    in_equal = inbound(_hm(9), 20, "i1", dep_actual=_hm(8))  # departs exactly 08:00
    assert out.actual_arrival == in_equal.actual_departure
    assert _feasible(out, in_equal) is False  # strict >


@pytest.mark.offline
def test_infeasible_pair_is_never_emitted_as_two_claims():
    # Both claimable (16 min each) but inbound departs before outbound arrives.
    out = outbound(_hm(7), 16, "o1")
    in_bad = inbound(_hm(6), 16, "i1")
    result = _one(_day([out], [in_bad]))
    # No feasible pair -> best single (tie 12.5 vs 12.5, outbound wins on
    # earliest-outbound tie-break).
    assert len(result.claims) == 1
    assert result.claims[0].direction is Direction.OUTBOUND


# --- AC2: max total payout, 0/1/2 rows, status passthrough ------------------
@pytest.mark.offline
def test_feasible_pair_claims_both_legs():
    out = outbound(_hm(7), 20, "o1")   # 12.5
    inb = inbound(_hm(18), 35, "i1")   # 30-59 band -> 25
    result = _one(_day([out], [inb]))
    assert len(result.claims) == 2
    dirs = {c.direction for c in result.claims}
    assert dirs == {Direction.OUTBOUND, Direction.INBOUND}


@pytest.mark.offline
def test_no_claimable_services_gives_zero_rows_ok():
    out = outbound(_hm(7), 5, "o1")    # sub-15, not claimable
    result = _one(_day([out]))
    assert result.status is FetchStatus.OK
    assert result.claims == ()


@pytest.mark.offline
def test_fetch_failed_status_passed_through_unchanged():
    out = outbound(_hm(7), 40, "o1")   # would be claimable, but day failed
    result = _one(_day([out], status=FetchStatus.FETCH_FAILED))
    assert result.status is FetchStatus.FETCH_FAILED
    assert result.claims == ()


@pytest.mark.offline
def test_cancelled_service_is_skipped_here():
    # Cancellation-derived claims are Story 1.5 (gated); 1.4 skips cancelled.
    out = Service(
        rid="o1", direction=Direction.OUTBOUND, origin="GOD", destination="WAT",
        date="2026-05-28", scheduled_departure=_hm(7), scheduled_arrival=_hm(8),
        actual_departure=None, actual_arrival=None, cancelled=True,
        reason="Cancelled",
    )
    result = _one(_day([out]))
    assert result.claims == ()


@pytest.mark.offline
def test_missing_actual_arrival_is_not_treated_as_delay_zero():
    out = Service(
        rid="o1", direction=Direction.OUTBOUND, origin="GOD", destination="WAT",
        date="2026-05-28", scheduled_departure=_hm(7), scheduled_arrival=_hm(8),
        actual_departure=_hm(7), actual_arrival=None,
    )
    result = _one(_day([out]))
    assert result.claims == ()


# --- AC3: worked examples (addendum) ---------------------------------------
@pytest.mark.offline
def test_two_equal_band_outbounds_pick_earliest():
    early = outbound(_hm(7), 16, "o-early")
    late = outbound(_hm(8), 16, "o-late")
    result = _one(_day([late, early]))  # order shouldn't matter
    assert len(result.claims) == 1
    assert result.claims[0].scheduled_departure == _hm(7)


@pytest.mark.offline
def test_higher_band_beats_earliness():
    early = outbound(_hm(7), 16, "o-early")   # 12.5
    later_bigger = outbound(_hm(8), 39, "o-late")  # 30-59 -> 25
    result = _one(_day([early, later_bigger]))
    assert len(result.claims) == 1
    assert result.claims[0].scheduled_departure == _hm(8)
    assert result.claims[0].delay == 39


# --- AC4: tie-break + determinism (FR10, AD-10, FR11) -----------------------
@pytest.mark.offline
def test_tie_break_prefers_fewer_rows():
    # Single 39-min outbound (25) vs a feasible 16+16 pair (12.5+12.5 = 25).
    o_big = outbound(_hm(7), 39, "o-big")          # 25, infeasible with i1 below
    o_small = outbound(_hm(9), 16, "o-small")      # 12.5
    i1 = inbound(_hm(18), 16, "i1")                # 12.5, feasible with o_small
    # Ensure o_big is NOT feasible with i1 would still pair to 37.5; make i1
    # depart before o_big arrives so o_big+i1 is infeasible, leaving the tie.
    o_big = outbound(_hm(17), 39, "o-big", arr_sched=_hm(18, 30))  # arrives 18:30+
    # i1 departs 18:00 < o_big arrival (~19:09) -> infeasible with o_big.
    result = _one(_day([o_big, o_small], [i1]))
    # Max total is 25 either way; fewer rows wins -> the single o_big.
    assert len(result.claims) == 1
    assert result.claims[0].delay == 39


@pytest.mark.offline
def test_deterministic_identical_input_identical_output():
    out = outbound(_hm(7), 20, "o1")
    inb = inbound(_hm(18), 35, "i1")
    a = optimise([_day([out], [inb])])
    b = optimise([_day([out], [inb])])
    assert a == b


@pytest.mark.offline
def test_single_inbound_only_option():
    inb = inbound(_hm(18), 40, "i1")   # 30-59 -> 25, no outbound claimable
    result = _one(_day([], [inb]))
    assert len(result.claims) == 1
    assert result.claims[0].direction is Direction.INBOUND
