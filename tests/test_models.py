"""Story 1.2: domain model invariants (AD-3, AD-4, AD-5, FR18).

Offline unit tests — no network or credentials (NFR2).
"""
import dataclasses

import pytest

from trainline.engine import models
from trainline.engine.models import (
    Band,
    Claim,
    DayResult,
    Direction,
    FetchStatus,
    Service,
)


def _service(**overrides):
    base = dict(
        rid="202605280727001",
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        date="2026-05-28",
        scheduled_departure=7 * 60 + 27,
        scheduled_arrival=8 * 60 + 30,
    )
    base.update(overrides)
    return Service(**base)


@pytest.mark.offline
def test_shapes_defined_only_in_engine_models():
    # AC1: the shapes live here and nowhere else.
    for shape in (Service, Claim, DayResult, Band, FetchStatus, Direction):
        assert shape.__module__ == "trainline.engine.models"


@pytest.mark.offline
def test_missing_actual_arrival_is_none_not_zero():
    # AC2: no actual recorded -> None, distinct from an on-time 0.
    svc = _service()
    assert svc.actual_arrival is None
    assert svc.actual_departure is None
    on_time = _service(actual_arrival=8 * 60 + 30)
    assert on_time.actual_arrival == 510
    assert on_time.actual_arrival is not None


@pytest.mark.offline
def test_cancelled_is_representable():
    # AC2: cancelled + reason carried as raw signal.
    svc = _service(cancelled=True, reason="Signal failure")
    assert svc.cancelled is True
    assert svc.reason == "Signal failure"
    assert _service().cancelled is False


@pytest.mark.offline
def test_service_is_frozen():
    svc = _service()
    with pytest.raises(dataclasses.FrozenInstanceError):
        svc.actual_arrival = 999  # type: ignore[misc]


@pytest.mark.offline
def test_failed_day_is_distinct_from_clean_no_claim():
    # AC (AD-5): FETCH_FAILED must be tellable apart from OK + zero claims.
    failed = DayResult(date="2026-05-28", status=FetchStatus.FETCH_FAILED)
    no_claim = DayResult(date="2026-05-28", status=FetchStatus.OK)
    assert failed.claims == ()
    assert no_claim.claims == ()
    assert failed.status is FetchStatus.FETCH_FAILED
    assert no_claim.status is FetchStatus.OK
    assert failed != no_claim


@pytest.mark.offline
def test_dayresult_holds_zero_one_or_two_claims():
    claim = Claim(
        date="2026-05-28",
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=447,
        scheduled_arrival=510,
        actual_arrival=533,
        delay=23,
        band=Band.B15_29,
        reason=None,
    )
    for n in (0, 1, 2):
        day = DayResult(
            date="2026-05-28",
            status=FetchStatus.OK,
            claims=tuple(claim for _ in range(n)),
        )
        assert len(day.claims) == n


@pytest.mark.offline
def test_claim_exposes_all_swr_form_fields():
    # AC (FR13): every field the SWR form needs is present.
    fields = {f.name for f in dataclasses.fields(Claim)}
    assert {
        "date",
        "origin",
        "destination",
        "scheduled_departure",
        "scheduled_arrival",
        "actual_arrival",
        "delay",
        "band",
        "reason",
    } <= fields


@pytest.mark.offline
def test_band_ordering_is_ticket_agnostic():
    # FR18: band ordering (higher wins) is independent of the payout track, so a
    # future season-ticket track is an additive payout concern, not a shape change.
    assert Band.NONE < Band.B15_29 < Band.B30_59 < Band.B60_119 < Band.B120_PLUS
    # The enum carries no percentage — payout lives in engine.delay (AD-11).
    assert not hasattr(Band.B15_29, "payout")
