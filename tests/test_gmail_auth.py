"""Unit tests for Gmail auth (file-token port from financeTracker_SW).

All Google API calls are mocked — no network.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trainline.adapters.gmail.auth import (
    GMAIL_SCOPES,
    GmailConfig,
    get_credentials,
    run_auth_flow,
    store_credentials,
)
from trainline.adapters.gmail.errors import GmailAuthError


def _make_fake_creds(
    *,
    expiry: datetime | None = None,
    token: str = "access-tok",
    refresh_token: str = "refresh-tok",
) -> MagicMock:
    creds = MagicMock()
    creds.token = token
    creds.refresh_token = refresh_token
    creds.expiry = expiry
    creds.to_json.return_value = json.dumps({
        "token": token,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": list(GMAIL_SCOPES),
    })
    return creds


def _cfg(tmp_path: Path, **kwargs) -> GmailConfig:
    defaults = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "token_path": tmp_path / "gmail_token.json",
        "digest_to": "simon@example.com",
    }
    defaults.update(kwargs)
    return GmailConfig(**defaults)


@pytest.mark.offline
def test_run_auth_flow_requests_readonly_and_send_scopes():
    fake = _make_fake_creds()
    with patch(
        "trainline.adapters.gmail.auth.InstalledAppFlow.from_client_config"
    ) as mock_flow_cls:
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = fake
        mock_flow_cls.return_value = mock_flow
        run_auth_flow(_cfg(Path(".")))
        scopes = mock_flow_cls.call_args[1]["scopes"]
        assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
        assert "https://www.googleapis.com/auth/gmail.send" in scopes
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes


@pytest.mark.offline
def test_store_and_get_credentials_round_trip(tmp_path):
    cfg = _cfg(tmp_path)
    creds = _make_fake_creds()
    store_credentials(creds, cfg)
    assert cfg.token_path.is_file()

    with patch(
        "trainline.adapters.gmail.auth.Credentials.from_authorized_user_info"
    ) as from_info:
        loaded = MagicMock()
        loaded.expiry = datetime.now(UTC) + timedelta(hours=1)
        from_info.return_value = loaded
        got = get_credentials(cfg)
        assert got is loaded
        raw = json.loads(cfg.token_path.read_text(encoding="utf-8"))
        assert raw["token"] == "access-tok"


@pytest.mark.offline
def test_get_credentials_missing_token_raises(tmp_path):
    with pytest.raises(GmailAuthError, match="gmail-auth"):
        get_credentials(_cfg(tmp_path))


@pytest.mark.offline
def test_get_credentials_refreshes_near_expiry(tmp_path):
    cfg = _cfg(tmp_path)
    store_credentials(_make_fake_creds(), cfg)
    near = datetime.now(UTC) + timedelta(seconds=30)
    refreshed = MagicMock()
    refreshed.expiry = datetime.now(UTC) + timedelta(hours=1)
    refreshed.to_json.return_value = json.dumps({"token": "new"})

    with patch(
        "trainline.adapters.gmail.auth.Credentials.from_authorized_user_info"
    ) as from_info, patch(
        "trainline.adapters.gmail.auth.Request"
    ), patch(
        "trainline.adapters.gmail.auth.store_credentials"
    ) as store:
        stale = MagicMock()
        stale.expiry = near
        stale.refresh = MagicMock()
        from_info.return_value = stale
        # After refresh, get_credentials returns same object
        got = get_credentials(cfg)
        stale.refresh.assert_called_once()
        store.assert_called_once()
        assert got is stale


@pytest.mark.offline
def test_inject_truststore_sets_ca_bundle_without_manual_env(tmp_path, monkeypatch):
    """AVG CA: project creds/ca-bundle.pem is applied via setdefault (NFR3)."""
    from trainline.adapters.gmail.auth import _inject_truststore

    monkeypatch.chdir(tmp_path)
    for key in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(key, raising=False)
    ca = tmp_path / "creds" / "ca-bundle.pem"
    ca.parent.mkdir(parents=True)
    ca.write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    _inject_truststore()
    assert Path(os.environ["REQUESTS_CA_BUNDLE"]).resolve() == ca.resolve()
    assert Path(os.environ["SSL_CERT_FILE"]).resolve() == ca.resolve()


@pytest.mark.offline
def test_inject_truststore_does_not_override_existing_env(tmp_path, monkeypatch):
    from trainline.adapters.gmail.auth import _inject_truststore

    monkeypatch.chdir(tmp_path)
    other = tmp_path / "other.pem"
    other.write_text("x")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(other))
    ca = tmp_path / "creds" / "ca-bundle.pem"
    ca.parent.mkdir(parents=True)
    ca.write_text("y")
    _inject_truststore()
    assert os.environ["REQUESTS_CA_BUNDLE"] == str(other)
