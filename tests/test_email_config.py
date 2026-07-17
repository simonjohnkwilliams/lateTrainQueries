"""Story 4.1 AC1: email / SMTP config loading from env (NFR9).

Offline — never reads real SMTP secrets; uses monkeypatch env only.
"""
from __future__ import annotations

import pytest

from trainline.adapters.config import EmailConfig, EmailConfigError, load_email_config


REQUIRED = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO")


def _set_all(monkeypatch, **overrides):
    base = {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.test",
        "SMTP_PASSWORD": "s3cret",
        "DIGEST_TO": "simon@example.test",
    }
    base.update(overrides)
    for key in REQUIRED + ("DIGEST_FROM",):
        monkeypatch.delenv(key, raising=False)
    for key, value in base.items():
        if value is not None:
            monkeypatch.setenv(key, value)
    return base


@pytest.mark.offline
def test_load_email_config_from_env(monkeypatch):
    _set_all(monkeypatch)
    cfg = load_email_config()
    assert isinstance(cfg, EmailConfig)
    assert cfg.smtp_host == "smtp.example.test"
    assert cfg.smtp_port == 587
    assert cfg.smtp_user == "sender@example.test"
    assert cfg.smtp_password == "s3cret"
    assert cfg.digest_to == "simon@example.test"
    assert cfg.digest_from is None


@pytest.mark.offline
def test_digest_from_optional(monkeypatch):
    _set_all(monkeypatch, DIGEST_FROM="digest@example.test")
    cfg = load_email_config()
    assert cfg.digest_from == "digest@example.test"


@pytest.mark.offline
def test_missing_all_keys_names_every_required_key(monkeypatch):
    for key in REQUIRED + ("DIGEST_FROM",):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(EmailConfigError) as excinfo:
        load_email_config()
    message = str(excinfo.value)
    for key in REQUIRED:
        assert key in message, f"expected {key} named in: {message}"


@pytest.mark.offline
def test_partial_missing_lists_only_absent_keys(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("SMTP_PASSWORD")
    monkeypatch.delenv("DIGEST_TO")
    with pytest.raises(EmailConfigError) as excinfo:
        load_email_config()
    message = str(excinfo.value)
    assert "SMTP_PASSWORD" in message
    assert "DIGEST_TO" in message
    assert "SMTP_HOST" not in message


@pytest.mark.offline
def test_blank_value_treated_as_missing(monkeypatch):
    _set_all(monkeypatch, SMTP_HOST="  ")
    with pytest.raises(EmailConfigError, match="SMTP_HOST"):
        load_email_config()


@pytest.mark.offline
def test_invalid_port_reports_clearly(monkeypatch):
    _set_all(monkeypatch, SMTP_PORT="not-a-number")
    with pytest.raises(EmailConfigError, match="SMTP_PORT"):
        load_email_config()


@pytest.mark.offline
def test_port_out_of_range_reports_clearly(monkeypatch):
    _set_all(monkeypatch, SMTP_PORT="0")
    with pytest.raises(EmailConfigError, match="SMTP_PORT"):
        load_email_config()


@pytest.mark.offline
def test_load_email_config_accepts_explicit_environ():
    env = {
        "SMTP_HOST": "h",
        "SMTP_PORT": "465",
        "SMTP_USER": "u",
        "SMTP_PASSWORD": "p",
        "DIGEST_TO": "t",
    }
    cfg = load_email_config(environ=env)
    assert cfg.smtp_port == 465
    assert cfg.smtp_host == "h"


@pytest.mark.offline
def test_load_email_config_from_credentials_file(tmp_path, monkeypatch):
    for key in REQUIRED + ("DIGEST_FROM", "HSP_CREDENTIALS_FILE"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "trainConfig.txt"
    path.write_text(
        "[configuration]\nusername=u\npassword=p\n"
        "## Email Digest ##\n"
        "SMTP_HOST=smtp.example.test\n"
        "SMTP_PORT=587\n"
        "SMTP_USER=sender@example.test\n"
        "SMTP_PASSWORD=abcd efgh ijkl mnop\n"
        "DIGEST_TO=simon@example.test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(path))
    cfg = load_email_config()
    assert cfg.smtp_host == "smtp.example.test"
    assert cfg.smtp_port == 587
    assert cfg.smtp_password == "abcdefghijklmnop"  # spaces stripped
    assert cfg.digest_to == "simon@example.test"
