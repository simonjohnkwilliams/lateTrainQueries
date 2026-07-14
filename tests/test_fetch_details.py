"""Story 2.3: fetch serviceDetails + map JSON → Service (FR2, AD-3, AD-4, AD-6).

Offline: real recorded details fixtures (FR21) plus synthetic edge cases.
"""
import json
import os

import pytest

from tests._fakes import FakeSession
from trainline.adapters.hsp_client import (
    SERVICE_DETAILS_URL,
    HspClient,
    map_service_details,
)
from trainline.engine.delay import calculate_delay
from trainline.engine.models import Direction

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _recorded(rid):
    with open(os.path.join(FIXTURE_DIR, f"recorded_details_{rid}.json")) as fh:
        return json.load(fh)


@pytest.mark.offline
def test_fetch_service_details_posts_rid():
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.fetch_service_details("202605287679538")
    assert session.calls[0]["url"] == SERVICE_DETAILS_URL
    assert session.calls[0]["json"] == {"rid": "202605287679538"}


@pytest.mark.recorded
def test_maps_recorded_god_to_wat_service():
    response = _recorded("202605287679538")
    svc = map_service_details(response, "GOD", "WAT", Direction.OUTBOUND)
    assert svc is not None
    assert svc.rid == "202605287679538"
    assert svc.date == "2026-05-28"
    assert svc.origin == "GOD" and svc.destination == "WAT"
    # GOD gbtt_ptd 0708 -> 428; WAT gbtt_pta 0753 -> 473, actual_ta 0756 -> 476.
    assert svc.scheduled_departure == 7 * 60 + 8
    assert svc.scheduled_arrival == 7 * 60 + 53
    assert svc.actual_arrival == 7 * 60 + 56
    assert calculate_delay(svc.actual_arrival, svc.scheduled_arrival) == 3
    assert svc.cancelled is False


@pytest.mark.offline
def test_service_not_serving_route_maps_to_none():
    response = _recorded("202605287679538")
    # This service does not call at ABC.
    assert map_service_details(response, "GOD", "ABC", Direction.OUTBOUND) is None


@pytest.mark.offline
def test_empty_actual_maps_to_none_not_zero():
    response = {
        "serviceAttributesDetails": {
            "date_of_service": "2026-05-28",
            "rid": "r1",
            "locations": [
                {"location": "GOD", "gbtt_ptd": "0708", "gbtt_pta": "",
                 "actual_td": "0708", "actual_ta": "", "late_canc_reason": ""},
                {"location": "WAT", "gbtt_ptd": "", "gbtt_pta": "0753",
                 "actual_td": "", "actual_ta": "", "late_canc_reason": ""},
            ],
        }
    }
    svc = map_service_details(response, "GOD", "WAT", Direction.OUTBOUND)
    assert svc.actual_arrival is None
    assert svc.cancelled is False  # no reason -> not cancelled, just no actual


@pytest.mark.offline
def test_cross_midnight_uses_origin_day_relative_minutes():
    response = {
        "serviceAttributesDetails": {
            "date_of_service": "2026-05-28",
            "rid": "r-midnight",
            "locations": [
                {"location": "GOD", "gbtt_ptd": "2350", "gbtt_pta": "",
                 "actual_td": "2352", "actual_ta": "", "late_canc_reason": ""},
                {"location": "WAT", "gbtt_ptd": "", "gbtt_pta": "0015",
                 "actual_td": "", "actual_ta": "0020", "late_canc_reason": ""},
            ],
        }
    }
    svc = map_service_details(response, "GOD", "WAT", Direction.OUTBOUND)
    # 00:15 becomes 15 + 1440 = 1455; 00:20 -> 1460. Delay = 5, not -1435.
    assert svc.scheduled_arrival == 15 + 1440
    assert svc.actual_arrival == 20 + 1440
    assert calculate_delay(svc.actual_arrival, svc.scheduled_arrival) == 5


@pytest.mark.offline
def test_cancelled_service_from_empty_actual_plus_reason():
    response = {
        "serviceAttributesDetails": {
            "date_of_service": "2026-05-28",
            "rid": "r-cancel",
            "locations": [
                {"location": "GOD", "gbtt_ptd": "0708", "gbtt_pta": "",
                 "actual_td": "", "actual_ta": "", "late_canc_reason": "Signal failure"},
                {"location": "WAT", "gbtt_ptd": "", "gbtt_pta": "0753",
                 "actual_td": "", "actual_ta": "", "late_canc_reason": "Signal failure"},
            ],
        }
    }
    svc = map_service_details(response, "GOD", "WAT", Direction.OUTBOUND)
    assert svc.cancelled is True
    assert svc.reason == "Signal failure"
    assert svc.actual_arrival is None  # raw signal only; no fallback delay here
