"""Story 2.5: fetch-failure contract, per-day status (FR5, AD-5, NFR1).

A failed fetch must never masquerade as "no claim". Offline via fake transport.
"""
import logging

import pytest

from tests._fakes import FakeResponse, FakeSession
from trainline.adapters.hsp_client import fetch_day
from trainline.engine.models import FetchStatus

WINDOW = ("0000", "2359")

_DETAILS_DOC = {
    "serviceAttributesDetails": {
        "date_of_service": "2026-05-28",
        "rid": "rid-GOD",
        "locations": [
            {"location": "GOD", "gbtt_ptd": "0708", "gbtt_pta": "",
             "actual_td": "0710", "actual_ta": "", "late_canc_reason": ""},
            {"location": "WAT", "gbtt_ptd": "", "gbtt_pta": "0753",
             "actual_td": "", "actual_ta": "0830", "late_canc_reason": ""},
        ],
    }
}


def _ok_handler(url, kw):
    if "serviceMetrics" in url:
        from_loc = kw["json"]["from_loc"]
        return FakeResponse(
            {"Services": [{"serviceAttributesMetrics": {"rids": [f"rid-{from_loc}"]}}]})
    return FakeResponse(_DETAILS_DOC)


@pytest.mark.offline
def test_all_required_fetches_ok_gives_status_ok():
    client_session = FakeSession(handler=_ok_handler)
    from trainline.adapters.hsp_client import HspClient
    client = HspClient("u", "p", session=client_session)
    day = fetch_day(client, "2026-05-28", "GOD", "WAT", WINDOW, WINDOW)
    assert day.status is FetchStatus.OK
    assert len(day.outbound) == 1  # GOD->WAT service mapped


@pytest.mark.offline
def test_metrics_failure_marks_day_fetch_failed():
    from trainline.adapters.hsp_client import HspClient

    def handler(url, kw):
        if "serviceMetrics" in url:
            return FakeResponse({}, status_error=RuntimeError("500 metrics"))
        return FakeResponse(_DETAILS_DOC)

    client = HspClient("u", "p", session=FakeSession(handler=handler))
    day = fetch_day(client, "2026-05-28", "GOD", "WAT", WINDOW, WINDOW)
    assert day.status is FetchStatus.FETCH_FAILED


@pytest.mark.offline
def test_details_failure_marks_day_fetch_failed():
    from trainline.adapters.hsp_client import HspClient

    def handler(url, kw):
        if "serviceMetrics" in url:
            return FakeResponse(
                {"Services": [{"serviceAttributesMetrics": {"rids": ["r1"]}}]})
        return FakeResponse({}, status_error=RuntimeError("500 details"))

    client = HspClient("u", "p", session=FakeSession(handler=handler))
    day = fetch_day(client, "2026-05-28", "GOD", "WAT", WINDOW, WINDOW)
    # Even though metrics succeeded, a required details fetch failed (AD-5).
    assert day.status is FetchStatus.FETCH_FAILED


@pytest.mark.offline
def test_a_failing_day_does_not_abort_the_run():
    from trainline.adapters.hsp_client import HspClient

    def bad_handler(url, kw):
        return FakeResponse({}, status_error=RuntimeError("down"))

    dates = ["2026-05-27", "2026-05-28"]
    results = []
    for i, date in enumerate(dates):
        session = FakeSession(handler=_ok_handler if i == 0 else bad_handler)
        client = HspClient("u", "p", session=session)
        results.append(fetch_day(client, date, "GOD", "WAT", WINDOW, WINDOW))
    # The run completed for both days; the failure did not abort it.
    assert results[0].status is FetchStatus.OK
    assert results[1].status is FetchStatus.FETCH_FAILED


@pytest.mark.offline
def test_failure_is_logged(caplog):
    from trainline.adapters.hsp_client import HspClient

    client = HspClient("u", "p", session=FakeSession(
        handler=lambda url, kw: FakeResponse({}, status_error=RuntimeError("boom"))))
    with caplog.at_level(logging.WARNING):
        fetch_day(client, "2026-05-28", "GOD", "WAT", WINDOW, WINDOW)
    assert any("fetch failed" in rec.message for rec in caplog.records)
