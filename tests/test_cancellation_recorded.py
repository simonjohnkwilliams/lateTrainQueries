"""Story 1.5 follow-up: OQ1 resolved with a REAL cancelled-train fixture.

When the story shipped, the AD-6 cancellation fallback was gated OFF because no
real cancelled-service JSON existed to pin the HSP shape (OQ1). These fixtures
are real serviceDetails captured from HSP:

  * ``recorded_details_cancelled_202607107679744.json`` — the 18:30 London
    Waterloo → Portsmouth Harbour on 2026-07-10, cancelled at Waterloo. Every
    calling point has empty ``actual_ta``/``actual_td`` and a ``late_canc_reason``
    ("911"). It calls at GOD (scheduled arrival 19:15).
  * ``recorded_details_catchable_202607107679102.json`` — the 18:45 Waterloo
    service that actually ran and reached GOD at 19:33 (the next catchable
    train after the cancelled 18:30).

These prove the real JSON maps to ``Service.cancelled == True`` and that, with
the fallback ON, the optimiser derives the correct next-catchable delay. Offline
(NFR2): fixtures only, no network.
"""
import json
import os
from types import SimpleNamespace

import pytest

from trainline.adapters.hsp_client import map_service_details
from trainline.engine.models import Band, Direction, FetchedDay, FetchStatus
from trainline.engine.optimiser import optimise

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

CANCELLED_RID = "202607107679744"  # 18:30 WAT->PMH, cancelled at Waterloo
CATCHABLE_RID = "202607107679102"  # 18:45 WAT service, ran, reached GOD 19:33


def _recorded(name):
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def _cancelled_service():
    return map_service_details(
        _recorded(f"recorded_details_cancelled_{CANCELLED_RID}.json"),
        "WAT", "GOD", Direction.INBOUND, date="2026-07-10",
    )


def _catchable_service():
    return map_service_details(
        _recorded(f"recorded_details_catchable_{CATCHABLE_RID}.json"),
        "WAT", "GOD", Direction.INBOUND, date="2026-07-10",
    )


@pytest.mark.recorded
def test_real_cancelled_service_maps_to_cancelled():
    """OQ1: a real cancelled HSP service maps to ``cancelled=True`` (AD-3/AD-6)."""
    svc = _cancelled_service()
    assert svc is not None
    assert svc.cancelled is True
    assert svc.actual_arrival is None  # no actual = None, never on-time 0
    assert svc.reason == "911"
    assert svc.scheduled_arrival == 19 * 60 + 15  # GOD scheduled arrival 19:15


@pytest.mark.recorded
def test_fallback_off_yields_no_claim_for_real_cancellation():
    """With the gate OFF, the real cancelled service contributes nothing (AC1)."""
    day = FetchedDay(
        date="2026-07-10", status=FetchStatus.OK,
        outbound=(), inbound=(_cancelled_service(), _catchable_service()),
    )
    result = optimise([day], config=SimpleNamespace(enable_cancellation_fallback=False))[0]
    assert result.claims == ()


@pytest.mark.recorded
def test_fallback_on_derives_next_catchable_delay_from_real_data():
    """With the gate ON, delay = next-catchable arrival − cancelled schedule (AC2).

    Cancelled 18:30 was due at GOD 19:15; next catchable (18:45) reached GOD at
    19:33 → 18 minutes late, band 15-29.
    """
    day = FetchedDay(
        date="2026-07-10", status=FetchStatus.OK,
        outbound=(), inbound=(_cancelled_service(), _catchable_service()),
    )
    result = optimise([day], config=SimpleNamespace(enable_cancellation_fallback=True))[0]
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.direction is Direction.INBOUND
    assert claim.delay == 18
    assert claim.band is Band.B15_29
    assert claim.reason == "911"
    assert claim.scheduled_departure == 18 * 60 + 30  # anchored to the cancelled slot
