"""Offline tests for SWR credential loading (no secrets printed)."""
from __future__ import annotations

import pytest

from trainline.adapters.config import SwrConfigError, load_swr_credentials


@pytest.mark.offline
def test_load_swr_credentials_from_section(tmp_path, monkeypatch):
    monkeypatch.delenv("SWR_USERNAME", raising=False)
    monkeypatch.delenv("SWR_PASSWORD", raising=False)
    monkeypatch.delenv("SWR_URL", raising=False)
    creds = tmp_path / "trainConfig.txt"
    creds.write_text(
        "## SWR Login ##\n"
        "swr_username=user@example.com\n"
        "swr_password=secret\n"
        "url=https://delayrepay.southwesternrailway.com\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(creds))
    loaded = load_swr_credentials(credentials_path=str(creds))
    assert loaded.username == "user@example.com"
    assert loaded.password == "secret"
    assert loaded.base_url.endswith("/")


@pytest.mark.offline
def test_load_swr_credentials_env_overrides(tmp_path, monkeypatch):
    creds = tmp_path / "trainConfig.txt"
    creds.write_text(
        "## SWR Login ##\nswr_username=file@example.com\nswr_password=filepass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("SWR_USERNAME", "env@example.com")
    monkeypatch.setenv("SWR_PASSWORD", "envpass")
    loaded = load_swr_credentials(credentials_path=str(creds))
    assert loaded.username == "env@example.com"
    assert loaded.password == "envpass"


@pytest.mark.offline
def test_load_swr_credentials_missing_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("SWR_USERNAME", raising=False)
    monkeypatch.delenv("SWR_PASSWORD", raising=False)
    creds = tmp_path / "trainConfig.txt"
    creds.write_text("[configuration]\nusername=u\npassword=p\n", encoding="utf-8")
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(creds))
    with pytest.raises(SwrConfigError):
        load_swr_credentials(credentials_path=str(creds))


@pytest.mark.offline
def test_load_ticket_form_defaults_from_section(tmp_path, monkeypatch):
    from trainline.adapters.config import load_ticket_form_defaults

    monkeypatch.delenv("SWR_TICKET_PRICE", raising=False)
    monkeypatch.delenv("SWR_TICKET_REFERENCE", raising=False)
    creds = tmp_path / "trainConfig.txt"
    creds.write_text(
        "## SWR Delay Repay ##\n"
        "swr_username=user@example.com\n"
        "swr_password=secret\n"
        "ticket_price=18.40\n"
        "ticket_reference=98765\n",
        encoding="utf-8",
    )
    loaded = load_ticket_form_defaults(credentials_path=str(creds))
    assert loaded.ticket_price == "18.40"
    assert loaded.ticket_reference == "98765"


@pytest.mark.offline
def test_load_ticket_form_defaults_from_section(tmp_path, monkeypatch):
    from trainline.adapters.config import load_ticket_form_defaults

    monkeypatch.delenv("SWR_TICKET_PRICE", raising=False)
    monkeypatch.delenv("SWR_TICKET_REFERENCE", raising=False)
    creds = tmp_path / "trainConfig.txt"
    creds.write_text(
        "## SWR Delay Repay ##\n"
        "swr_username=user@example.com\n"
        "swr_password=secret\n"
        "ticket_price=18.40\n"
        "ticket_reference=98765\n",
        encoding="utf-8",
    )
    loaded = load_ticket_form_defaults(credentials_path=str(creds))
    assert loaded.ticket_price == "18.40"
    assert loaded.ticket_reference == "98765"
