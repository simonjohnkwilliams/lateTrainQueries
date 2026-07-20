"""Story 7.1: digest send prefers Gmail API; SMTP is legacy fallback (FR35, AD-2).

Offline — mocked Gmail client / credentials; no network.
"""
from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests._fakes import FakeSession
from trainline import cli
from trainline.adapters.gmail.errors import GmailAuthError
from trainline.adapters.hsp_client import HspClient
from trainline.engine.models import FetchStatus, FetchedDay


def _stub_assess(monkeypatch, tmp_path):
    """Minimal assess path that writes claims and returns OK."""
    creds = tmp_path / "creds.txt"
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n",
        encoding="utf-8",
    )

    def fake_fetch_day(client, day, *args, **kwargs):
        return FetchedDay(date=day, status=FetchStatus.OK)

    monkeypatch.setattr(cli, "fetch_day", fake_fetch_day)
    monkeypatch.setattr(
        cli,
        "build_client",
        lambda **kw: HspClient("u", "p", session=FakeSession()),
    )
    # Do not inject SMTP transport — exercise real digest resolution.
    monkeypatch.setattr(cli, "_digest_transport", None)
    return creds


def _gmail_section(token_path: Path) -> str:
    return (
        "## Gmail API ##\n"
        "GOOGLE_CLIENT_ID=cid\n"
        "GOOGLE_CLIENT_SECRET=csecret\n"
        f"GMAIL_TOKEN_PATH={token_path.name}\n"
        "DIGEST_TO=simon@example.test\n"
    )


@pytest.mark.offline
def test_digest_prefers_gmail_when_config_and_token_present(monkeypatch, tmp_path):
    creds = _stub_assess(monkeypatch, tmp_path)
    token = tmp_path / "gmail_token.json"
    token.write_text("{}", encoding="utf-8")
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n\n" + _gmail_section(token),
        encoding="utf-8",
    )

    sent: list[EmailMessage] = []

    class FakeGmailClient:
        def __init__(self, credentials):
            pass

        def send_message(self, message: EmailMessage):
            sent.append(message)
            return {"id": "gmail-1"}

    monkeypatch.setattr(
        "trainline.adapters.gmail.auth.get_credentials",
        lambda cfg: MagicMock(),
    )
    monkeypatch.setattr(
        "trainline.adapters.gmail.client.GmailClient",
        FakeGmailClient,
    )

    out = tmp_path / "Results"
    rc = cli.main([
        "--digest",
        "--from-date", "2026-07-08",
        "--to-date", "2026-07-08",
        "--out-dir", str(out),
        "--credentials-file", str(creds),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0
    assert (out / "claims.json").is_file()
    assert len(sent) == 1
    assert sent[0]["To"] == "simon@example.test"
    assert "Delay Repay digest" in sent[0]["Subject"]


@pytest.mark.offline
def test_digest_missing_gmail_token_explains_auth_assess_still_writes(
        monkeypatch, tmp_path, capsys):
    creds = _stub_assess(monkeypatch, tmp_path)
    token = tmp_path / "gmail_token.json"  # not created
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n\n" + _gmail_section(token),
        encoding="utf-8",
    )

    def boom(cfg):
        raise GmailAuthError(
            "No Gmail credentials stored. Run: python -m trainline --gmail-auth"
        )

    monkeypatch.setattr("trainline.adapters.gmail.auth.get_credentials", boom)

    out = tmp_path / "Results"
    rc = cli.main([
        "--digest",
        "--from-date", "2026-07-08",
        "--to-date", "2026-07-08",
        "--out-dir", str(out),
        "--credentials-file", str(creds),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0
    assert (out / "claims.json").is_file()
    assert (out / "claims.csv").is_file()
    captured = capsys.readouterr()
    text = (captured.out + captured.err).casefold()
    assert "gmail-auth" in text


@pytest.mark.offline
def test_digest_falls_back_to_smtp_when_gmail_not_configured(
        monkeypatch, tmp_path):
    creds = _stub_assess(monkeypatch, tmp_path)
    # HSP only — no Gmail section
    for key, value in {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.test",
        "SMTP_PASSWORD": "s3cret",
        "DIGEST_TO": "simon@example.test",
    }.items():
        monkeypatch.setenv(key, value)

    smtp_calls: list[str] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            smtp_calls.append("init")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            smtp_calls.append(msg["Subject"])

    monkeypatch.setattr(
        "trainline.adapters.notification.smtplib.SMTP", FakeSMTP)

    out = tmp_path / "Results"
    rc = cli.main([
        "--digest",
        "--from-date", "2026-07-08",
        "--to-date", "2026-07-08",
        "--out-dir", str(out),
        "--credentials-file", str(creds),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0
    assert (out / "claims.json").is_file()
    assert "init" in smtp_calls
    assert any("Delay Repay digest" in c for c in smtp_calls if c != "init")


@pytest.mark.offline
def test_digest_neither_gmail_nor_smtp_mentions_gmail_auth(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_digest_transport", None)
    for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO",
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GMAIL_TOKEN_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    creds = tmp_path / "creds.txt"
    creds.write_text(
        "[configuration]\nusername=u\npassword=p\n",
        encoding="utf-8",
    )
    rc = cli._maybe_send_digest([], strict=False, credentials_path=str(creds))
    assert rc == 2
    captured = capsys.readouterr()
    text = (captured.err + captured.out).casefold()
    assert "gmail-auth" in text


@pytest.mark.offline
def test_notification_module_does_not_import_gmail():
    """AD-2: notification must not import gmail or config."""
    import trainline.adapters.notification as notif

    src = Path(notif.__file__).read_text(encoding="utf-8")
    assert "gmail" not in src.casefold()
    assert "from trainline.adapters.config" not in src
    assert "import trainline.adapters.config" not in src
