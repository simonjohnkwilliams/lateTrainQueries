"""Story 4.1: notification adapter — injectable SMTP transport (AD-13).

Offline — never opens a real SMTP connection.
"""
from __future__ import annotations

from email.message import EmailMessage

import pytest

from tests._fakes import FakeSmtpTransport
from trainline.adapters.config import EmailConfig
from trainline.adapters.notification import send_digest


def _config(**overrides) -> EmailConfig:
    base = dict(
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_user="sender@example.test",
        smtp_password="s3cret",
        digest_to="simon@example.test",
        digest_from=None,
    )
    base.update(overrides)
    return EmailConfig(**base)


@pytest.mark.offline
def test_send_digest_uses_injected_transport():
    transport = FakeSmtpTransport()
    send_digest(
        "Weekly Delay Repay digest",
        "<p>Hello</p>",
        "Hello",
        _config(),
        transport=transport,
    )
    assert len(transport.sent) == 1
    msg, cfg = transport.sent[0]
    assert isinstance(msg, EmailMessage)
    assert msg["Subject"] == "Weekly Delay Repay digest"
    assert msg["To"] == "simon@example.test"
    assert msg["From"] == "sender@example.test"
    assert cfg.smtp_host == "smtp.example.test"


@pytest.mark.offline
def test_send_digest_from_overrides_user():
    transport = FakeSmtpTransport()
    send_digest(
        "Subj",
        "<b>x</b>",
        "x",
        _config(digest_from="noreply@example.test"),
        transport=transport,
    )
    msg, _cfg = transport.sent[0]
    assert msg["From"] == "noreply@example.test"


@pytest.mark.offline
def test_send_digest_includes_text_and_html_parts():
    transport = FakeSmtpTransport()
    send_digest(
        "Subj",
        "<p>HTML body</p>",
        "Text body",
        _config(),
        transport=transport,
    )
    msg, _ = transport.sent[0]
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Text body"
    assert "HTML body" in msg.get_body(preferencelist=("html",)).get_content()


@pytest.mark.offline
def test_send_digest_without_transport_uses_callable_default_path(monkeypatch):
    """Ensure default path is invoked only when transport is None — stub SMTP."""
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("init", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, msg):
            calls.append(("send_message", msg["Subject"]))

    monkeypatch.setattr(
        "trainline.adapters.notification.smtplib.SMTP", FakeSMTP)

    send_digest("S", "<p>h</p>", "t", _config())
    assert ("init", "smtp.example.test", 587, 30) in calls
    assert ("starttls",) in calls
    assert ("login", "sender@example.test", "s3cret") in calls
    assert ("send_message", "S") in calls


@pytest.mark.offline
def test_send_digest_port_465_uses_smtp_ssl(monkeypatch):
    calls = []

    class FakeSMTP_SSL:
        def __init__(self, host, port, timeout=None):
            calls.append(("ssl_init", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            calls.append(("login", user))

        def send_message(self, msg):
            calls.append(("send_message",))

    monkeypatch.setattr(
        "trainline.adapters.notification.smtplib.SMTP_SSL", FakeSMTP_SSL)

    send_digest("S", "<p>h</p>", "t", _config(smtp_port=465))
    assert ("ssl_init", "smtp.example.test", 465, 30) in calls
    assert ("login", "sender@example.test") in calls
    assert ("send_message",) in calls


@pytest.mark.offline
def test_send_digest_strips_blank_digest_from():
    transport = FakeSmtpTransport()

    class Cfg:
        smtp_host = "h"
        smtp_port = 587
        smtp_user = "user@example.test"
        smtp_password = "p"
        digest_to = "to@example.test"
        digest_from = "   "

    send_digest("S", "<p>h</p>", "t", Cfg(), transport=transport)
    msg, _ = transport.sent[0]
    assert msg["From"] == "user@example.test"
