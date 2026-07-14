"""Story 2.4: idempotent on-disk response cache (FR4, NFR4).

Offline via the fake transport; the cache is a private detail of HspClient.
"""
import pytest

from tests._fakes import FakeResponse, FakeSession
from trainline.adapters.hsp_client import HspClient


def _metrics_session(counter):
    def handler(url, kw):
        counter.append(1)
        return FakeResponse({"Services": [{"serviceAttributesMetrics": {"rids": ["r1"]}}]})
    return FakeSession(handler=handler)


@pytest.mark.offline
def test_second_run_uses_cache_no_api_call(tmp_path):
    calls_a = []
    client_a = HspClient("u", "p", session=_metrics_session(calls_a),
                         cache_dir=str(tmp_path))
    client_a.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls_a) == 1  # first run hits the API and writes the cache

    # A fresh run (new client + new transport) over the same cache dir.
    calls_b = []
    client_b = HspClient("u", "p", session=_metrics_session(calls_b),
                         cache_dir=str(tmp_path))
    client_b.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls_b) == 0  # cache hit — no API call


@pytest.mark.offline
def test_details_cached_per_rid(tmp_path):
    calls = []
    session = FakeSession(handler=lambda url, kw: (calls.append(kw["json"]["rid"])
                                                   or FakeResponse({"serviceAttributesDetails": {}}))
                          )
    client = HspClient("u", "p", session=session, cache_dir=str(tmp_path))
    client.fetch_service_details("rid-1")
    client.fetch_service_details("rid-1")  # cached
    client.fetch_service_details("rid-2")
    assert calls == ["rid-1", "rid-2"]  # rid-1 fetched once, rid-2 once


@pytest.mark.offline
def test_force_refresh_refetches(tmp_path):
    calls_a = []
    HspClient("u", "p", session=_metrics_session(calls_a),
              cache_dir=str(tmp_path)).fetch_service_metrics(
        "GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls_a) == 1

    calls_b = []
    client = HspClient("u", "p", session=_metrics_session(calls_b),
                       cache_dir=str(tmp_path), force_refresh=True)
    client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls_b) == 1  # force_refresh bypasses the cache


@pytest.mark.offline
def test_clear_cache_forces_refetch(tmp_path):
    calls = []
    client = HspClient("u", "p", session=_metrics_session(calls),
                       cache_dir=str(tmp_path))
    client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    client.clear_cache()
    client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls) == 2  # cleared -> re-fetched


@pytest.mark.offline
def test_idempotent_output_across_runs(tmp_path):
    client_a = HspClient("u", "p", session=_metrics_session([]),
                         cache_dir=str(tmp_path))
    first = client_a.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    client_b = HspClient("u", "p", session=_metrics_session([]),
                         cache_dir=str(tmp_path))
    second = client_b.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert first == second


@pytest.mark.offline
def test_no_cache_dir_always_calls(tmp_path):
    calls = []
    client = HspClient("u", "p", session=_metrics_session(calls))  # no cache_dir
    for _ in range(3):
        client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(calls) == 3


@pytest.mark.offline
def test_failed_fetch_is_not_cached(tmp_path):
    boom = FakeSession(handler=lambda url, kw: FakeResponse(
        {}, status_error=RuntimeError("500")))
    client = HspClient("u", "p", session=boom, cache_dir=str(tmp_path))
    with pytest.raises(RuntimeError):
        client.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    # Nothing cached -> a later successful run re-fetches, never reads a "failed" cache.
    ok_calls = []
    ok = HspClient("u", "p", session=_metrics_session(ok_calls),
                   cache_dir=str(tmp_path))
    ok.fetch_service_metrics("GOD", "WAT", "0000", "2359", "2026-05-28", "2026-05-28")
    assert len(ok_calls) == 1
