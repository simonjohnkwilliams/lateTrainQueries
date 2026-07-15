"""Story 2.1: HSP client auth + AVG-TLS + injectable transport (NFR2, NFR3).

Offline by default via the fake transport; one opt-in @live test.
"""
import configparser
from pathlib import Path
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
def test_verify_is_never_disabled(monkeypatch, tmp_path):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.chdir(tmp_path)  # no local creds/ca-bundle.pem
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert session.calls[0]["verify"] is not False


@pytest.mark.offline
def test_raise_for_status_propagates():
    err = RuntimeError("500 Server Error")
    session = FakeSession(handler=lambda url, kw: FakeResponse({}, status_error=err))
    client = HspClient("u", "p", session=session)
    with pytest.raises(RuntimeError):
        client.post_json(SERVICE_METRICS_URL, {"x": 1})


@pytest.mark.live
def test_live_authenticated_request():
    from trainline.adapters.config import CredentialsError, load_credentials
    try:
        username, password = load_credentials()
    except CredentialsError as exc:
        pytest.skip(str(exc))
    client = HspClient(username, password)
    body = client.post_json(SERVICE_METRICS_URL, {
        "from_loc": "GOD", "to_loc": "WAT",
        "from_time": "0700", "to_time": "0900",
        "from_date": "2026-05-28", "to_date": "2026-05-28",
        "days": "WEEKDAY",
    })
    assert "Services" in body


@pytest.mark.offline
def test_auto_uses_project_ca_bundle_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.chdir(tmp_path)
    ca = tmp_path / "creds" / "ca-bundle.pem"
    ca.parent.mkdir()
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    session = FakeSession()
    client = HspClient("u", "p", session=session)
    client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert Path(session.calls[0]["verify"]) == ca.resolve()


@pytest.mark.offline
def test_ssl_error_with_ca_bundle_falls_back_to_system(monkeypatch, tmp_path):
    from requests.exceptions import SSLError
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.chdir(tmp_path)
    ca = tmp_path / "creds" / "ca-bundle.pem"
    ca.parent.mkdir()
    ca.write_text("-----BEGIN CERTIFICATE-----\n")

    def handler(url, kw):
        if kw.get("verify") == str(ca.resolve()):
            return FakeResponse({}, status_error=SSLError("avg mitm?"))
        return FakeResponse({"Services": []})

    session = FakeSession(handler=handler)
    client = HspClient("u", "p", session=session)
    body = client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert body == {"Services": []}
    assert len(session.calls) == 2
    assert session.calls[0]["verify"] == str(ca.resolve())
    assert session.calls[1]["verify"] is True


@pytest.mark.offline
def test_ssl_error_without_ca_retries_with_bundle(monkeypatch, tmp_path):
    from requests.exceptions import SSLError
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.chdir(tmp_path)
    ca = tmp_path / "creds" / "ca-bundle.pem"
    ca.parent.mkdir()
    ca.write_text("-----BEGIN CERTIFICATE-----\n")

    # Force primary = system by temporarily hiding prefer path: make resolve
    # try system first — simulate by raising on verify=True then succeeding on CA.
    # With prefer_ca_bundle=True primary is CA; reverse the handler for the
    # case where CA is missing on first resolve then appears — instead monkeypatch
    # resolve to return True first via removing file mid-call is hard.
    # Explicitly: primary CA fails... covered above. Here: pretend no prefer —
    # remove CA, call would use True; add CA and inject SSL on True.
    # Simpler approach: monkeypatch resolve_tls_verify to return True first attempt
    # is awkward. Delete CA so primary=True, handler SSL on True — then create CA
    # before fallback lookup.
    calls = {"n": 0}

    def handler(url, kw):
        calls["n"] += 1
        if kw.get("verify") is True:
            # Create CA so fallback can find it
            if not ca.is_file():
                ca.write_text("-----BEGIN CERTIFICATE-----\n")
            return FakeResponse({}, status_error=SSLError("no avg ca"))
        return FakeResponse({"ok": True})

    ca.unlink()
    session = FakeSession(handler=handler)
    client = HspClient("u", "p", session=session)
    # primary True (no ca), SSL error, then default_ca_bundle_path finds file created in handler
    # Wait — we unlink then handler creates on first call. Good.
    body = client.post_json(SERVICE_METRICS_URL, {"x": 1})
    assert body == {"ok": True}
    assert session.calls[0]["verify"] is True
    assert Path(session.calls[1]["verify"]) == ca.resolve()

