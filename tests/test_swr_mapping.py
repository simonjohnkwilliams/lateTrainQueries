"""Story 6.1 — SWR field mapping (offline)."""
from __future__ import annotations

import pytest

from trainline.adapters.swr_mapping import (
    SWR_REASON_CANCELLED,
    SWR_REASON_DELAYED,
    map_claim_for_swr,
    station_name,
)
from trainline.engine.models import Band, Claim, Direction


def _claim(**kwargs) -> Claim:
    base = dict(
        date="2026-07-10",
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=7 * 60 + 22,
        scheduled_arrival=8 * 60 + 10,
        actual_arrival=8 * 60 + 40,
        delay=30,
        band=Band.B30_59,
        reason=None,
    )
    base.update(kwargs)
    return Claim(**base)


@pytest.mark.offline
def test_crs_wat_and_god_map_to_station_names():
    assert station_name("WAT") == "London Waterloo"
    assert station_name("GOD") == "Godalming"
    assert station_name("wat") == "London Waterloo"


@pytest.mark.offline
def test_map_claim_delayed_en_route():
    fields = map_claim_for_swr(_claim())
    assert fields.origin_station == "Godalming"
    assert fields.destination_station == "London Waterloo"
    assert fields.delay_reason == SWR_REASON_DELAYED
    assert fields.raw_reason_code is None
    assert fields.scheduled_departure == "07:22"
    assert fields.actual_arrival == "08:40"
    assert fields.journey_date == "2026-07-10"


@pytest.mark.offline
def test_map_claim_cancelled_uses_train_cancelled_category():
    fields = map_claim_for_swr(_claim(reason="911"))
    assert fields.delay_reason == SWR_REASON_CANCELLED
    assert fields.raw_reason_code == "911"


@pytest.mark.offline
def test_map_claim_crs_table_extensible():
    fields = map_claim_for_swr(
        _claim(origin="XYZ", destination="WAT"),
        crs_names={"XYZ": "Test Town", "WAT": "London Waterloo"},
    )
    assert fields.origin_station == "Test Town"


@pytest.mark.offline
def test_ticket_medium_for_path_pdf_is_eticket():
    from trainline.adapters.swr_mapping import ticket_medium_for_path

    assert ticket_medium_for_path("07-24-X.pdf") == "E-ticket/M-ticket"
    assert ticket_medium_for_path("07-24-X.PDF") == "E-ticket/M-ticket"
    assert ticket_medium_for_path("07-24-X.jpg") == "Paper"
    assert ticket_medium_for_path("07-24-X.png") == "Paper"
