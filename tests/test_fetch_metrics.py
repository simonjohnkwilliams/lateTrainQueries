"""Story 2.2: fetch serviceMetrics + extract ALL RIDs (FR1, FR3).

Offline via fake transport and the real recorded metrics fixture (FR21).
"""
import json
import os

import pytest

from tests._fakes import FakeResponse, FakeSession
from trainline.adapters.hsp_client import (
    SERVICE_METRICS_URL,
    HspClient,
    extract_rids,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _recorded_metrics():
    with open(os.path.join(FIXTURE_DIR, "recorded_metrics_2026-05-28.json")) as fh:
        return json.load(fh)


@pytest.mark.offline
def test_service_metrics_post_body_shape():
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.fetch_service_metrics("GOD", "WAT", "0000", "2359",
                                 "2026-05-28", "2026-05-28")
    call = session.calls[0]
    assert call["url"] == SERVICE_METRICS_URL
    assert call["json"] == {
        "from_loc": "GOD",
        "to_loc": "WAT",
        "from_time": "0000",
        "to_time": "2359",
        "from_date": "2026-05-28",
        "to_date": "2026-05-28",
        "days": "WEEKDAY",
    }


@pytest.mark.offline
def test_both_directions_are_queried():
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    client.fetch_service_metrics("WAT", "GOD", "0000", "2359", "2026-05-28", "2026-05-28")
    assert session.calls[0]["json"]["from_loc"] == "GOD"
    assert session.calls[0]["json"]["to_loc"] == "WAT"
    assert session.calls[1]["json"]["from_loc"] == "WAT"
    assert session.calls[1]["json"]["to_loc"] == "GOD"


@pytest.mark.recorded
def test_extract_all_rids_from_recorded_metrics():
    metrics = _recorded_metrics()
    rids = extract_rids(metrics)
    # The fixture has 9 services; every RID must be extracted, not just the first.
    assert len(rids) == 9
    assert len(set(rids)) == 9
    assert "202605287679538" in rids


@pytest.mark.offline
def test_extract_rids_returns_every_rid_per_service():
    # FR3 regression: a service with multiple RIDs yields all of them.
    response = {
        "Services": [
            {"serviceAttributesMetrics": {"rids": ["a", "b"]}},
            {"serviceAttributesMetrics": {"rids": ["c"]}},
            {"serviceAttributesMetrics": {"rids": []}},
        ]
    }
    assert extract_rids(response) == ["a", "b", "c"]


@pytest.mark.offline
def test_extract_rids_dedupes_preserving_order():
    response = {
        "Services": [
            {"serviceAttributesMetrics": {"rids": ["a", "b"]}},
            {"serviceAttributesMetrics": {"rids": ["b", "c"]}},
        ]
    }
    assert extract_rids(response) == ["a", "b", "c"]


@pytest.mark.offline
def test_extract_rids_empty_response():
    assert extract_rids({}) == []
    assert extract_rids({"Services": []}) == []
