"""Story 2.1: HSP client auth + AVG-TLS + injectable transport (NFR2, NFR3).

Offline by default via the fake transport; one opt-in @live test.
"""
import configparser
import os

import pytest

from tests._fakes import FakeResponse, FakeSession
from trainline.adapters.hsp_client import (
    SERVICE_METRICS_URL,
    HspClient,
)


@pytest.mark.offline
def test_uses_injected_transport_no_network():
    session = FakeSession(handler=lambda url, kw: FakeResponse({"Services": []}))
    client = HspClient("user", "pw", session=session)
    body = client.post_json(SERVICE_METRICS_URL, {"from_loc": "GOD"})
    assert body == {"Services": []}
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == SERVICE_METRICS_URL


@pytest.mark.offline
def test_http_basic_auth_applied():
    session = FakeSession()
    client = HspClient("alice", "hunter2", session=session)
    client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert session.calls[0]["auth"] == ("alice", "hunter2")


@pytest.mark.offline
def test_requests_ca_bundle_is_honoured(monkeypatch, tmp_path):
    ca = tmp_path / "avg-ca-bundle.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca))
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert session.calls[0]["verify"] == str(ca)


@pytest.mark.offline
def test_verify_is_never_disabled(monkeypatch):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.post_json(SERVICE_METRICS_URL, {"x": 1})
    # Without the env var we don't pass verify at all → requests defaults to True.
    assert session.calls[0].get("verify", True) is not False


@pytest.mark.offline
def test_raise_for_status_propagates():
    err = RuntimeError("500 Server Error")
    session = FakeSession(handler=lambda url, kw: FakeResponse({}, status_error=err))
    client = HspClient("u", "p", session=session)
    with pytest.raises(RuntimeError):
        client.post_json(SERVICE_METRICS_URL, {"x": 1})


@pytest.mark.live
def test_live_authenticated_request():
    path = os.environ.get("HSP_CREDENTIALS_FILE")
    if not path or not os.path.isfile(path):
        pytest.skip("HSP_CREDENTIALS_FILE not set — live test needs real creds")
    cfg = configparser.ConfigParser()
    cfg.read(path)
    if not cfg.has_option("configuration", "username"):
        pytest.skip("credentials file missing [configuration] username/password")
    client = HspClient(
        cfg.get("configuration", "username"),
        cfg.get("configuration", "password"),
    )
    body = client.post_json(SERVICE_METRICS_URL, {
        "from_loc": "GOD", "to_loc": "WAT",
        "from_time": "0700", "to_time": "0900",
        "from_date": "2026-05-28", "to_date": "2026-05-28",
        "days": "WEEKDAY",
    })
    assert "Services" in body
