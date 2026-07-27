"""Acceptance tests for Story 4.1 notification adapter + email config.

Maps one-to-one to ``tests/features/notification.feature``.
"""
from __future__ import annotations

import ast
import importlib
import os

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests._fakes import FakeSmtpTransport
from trainline.adapters.config import EmailConfig, EmailConfigError, load_email_config
from trainline.adapters.notification import render_digest
from trainline.engine.models import Band, Claim, DayResult, Direction, FetchStatus

scenarios("features/notification.feature")

REQUIRED = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "DIGEST_TO")
PKG_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "trainline"))


@pytest.fixture
def world(monkeypatch):
    for key in REQUIRED + ("DIGEST_FROM", "HSP_CREDENTIALS_FILE"):
        monkeypatch.delenv(key, raising=False)
    return {
        "error": None,
        "config": None,
        "module": None,
        "transport": None,
        "imports": set(),
        "day_results": [],
        "digest_html": None,
        "digest_text": None,
    }


def _full_env():
    return {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.test",
        "SMTP_PASSWORD": "s3cret",
        "DIGEST_TO": "simon@example.test",
    }


@given("no email environment variables are set")
def no_email_env(world, monkeypatch):
    for key in REQUIRED + ("DIGEST_FROM", "HSP_CREDENTIALS_FILE"):
        monkeypatch.delenv(key, raising=False)


@given(parsers.parse('email environment variables are set except "{keys}"'))
def partial_email_env(world, monkeypatch, keys):
    env = _full_env()
    skip = {k.strip() for k in keys.split(",") if k.strip()}
    for key, value in env.items():
        if key in skip:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


@given("valid email config")
def valid_email_config(world):
    env = _full_env()
    world["config"] = EmailConfig(
        smtp_host=env["SMTP_HOST"],
        smtp_port=int(env["SMTP_PORT"]),
        smtp_user=env["SMTP_USER"],
        smtp_password=env["SMTP_PASSWORD"],
        digest_to=env["DIGEST_TO"],
    )


@given("a fake SMTP transport")
def fake_transport(world):
    world["transport"] = FakeSmtpTransport()


@when("email config is loaded")
def load_config(world):
    try:
        world["config"] = load_email_config()
        world["error"] = None
    except EmailConfigError as exc:
        world["error"] = exc
        world["config"] = None


@when("the notification adapter module is imported")
def import_notification(world):
    world["module"] = importlib.import_module("trainline.adapters.notification")
    path = os.path.join(PKG_ROOT, "adapters", "notification.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            names.add(prefix + (node.module or ""))
    world["imports"] = names


@when(parsers.parse(
    'send_digest is called with subject "{subject}" html "{html}" text "{text}"'))
def call_send_digest(world, subject, html, text):
    from trainline.adapters.notification import send_digest

    send_digest(
        subject, html, text, world["config"], transport=world["transport"])


@then(parsers.parse('an email config error names "{keys}"'))
def error_names_keys(world, keys):
    assert world["error"] is not None
    message = str(world["error"])
    for key in keys.split(","):
        key = key.strip()
        assert key in message, f"{key} not in {message!r}"


@then(parsers.parse('the email config error does not name "{key}"'))
def error_does_not_name(world, key):
    assert world["error"] is not None
    assert key not in str(world["error"])


@then("it does not import hsp_client, storage, config, or claim_submission")
def no_peer_adapter_imports(world):
    forbidden = ("hsp_client", "storage", "config", "claim_submission")
    for name in world["imports"]:
        for peer in forbidden:
            assert peer not in name.split("."), (
                f"notification imported peer adapter via {name!r}")


@then("the fake transport received one message")
def one_message(world):
    assert len(world["transport"].sent) == 1


@then(parsers.parse('the message subject is "{subject}"'))
def message_subject(world, subject):
    msg, _ = world["transport"].sent[0]
    assert msg["Subject"] == subject


@then("the message recipient is the configured DIGEST_TO")
def message_to(world):
    msg, cfg = world["transport"].sent[0]
    assert msg["To"] == cfg.digest_to


def _sample_claim(**overrides) -> Claim:
    base = dict(
        date="2026-07-10",
        direction=Direction.OUTBOUND,
        origin="GOD",
        destination="WAT",
        scheduled_departure=480,
        scheduled_arrival=540,
        actual_arrival=560,
        delay=20,
        band=Band.B15_29,
        reason="Late",
    )
    base.update(overrides)
    return Claim(**base)


@given("day results with one claimable outbound claim")
def one_claim_day(world):
    world["day_results"] = [
        DayResult(
            date="2026-07-10",
            status=FetchStatus.OK,
            claims=(_sample_claim(),),
        ),
    ]


@given("day results with a fetch-failed day and a clean no-claim day")
def failed_and_no_claim(world):
    world["day_results"] = [
        DayResult(date="2026-07-08", status=FetchStatus.OK, claims=()),
        DayResult(date="2026-07-09", status=FetchStatus.FETCH_FAILED, claims=()),
    ]


@given("day results with only clean no-claim days")
def only_no_claim(world):
    world["day_results"] = [
        DayResult(date="2026-07-08", status=FetchStatus.OK, claims=()),
        DayResult(date="2026-07-09", status=FetchStatus.OK, claims=()),
    ]


@when("the digest is rendered")
def render(world):
    html, text = render_digest(world["day_results"])
    world["digest_html"] = html
    world["digest_text"] = text


@then(parsers.parse('the digest text includes "{a}" "{b}" "{c}" "{d}" "{e}" "{f}"'))
def digest_includes_fields(world, a, b, c, d, e, f):
    text = world["digest_text"]
    for token in (a, b, c, d, e, f):
        assert token in text, f"{token!r} not in {text!r}"


@then(parsers.parse('the digest marks "{date}" as not analysed'))
def marks_not_analysed(world, date):
    text = world["digest_text"]
    idx = text.casefold().index("not analysed")
    assert date in text[idx:]


@then(parsers.parse('the digest does not mark "{date}" as not analysed'))
def does_not_mark_not_analysed(world, date):
    text = world["digest_text"]
    idx = text.casefold().index("not analysed")
    assert date not in text[idx:]


@then("the digest text says no claimable rows were found")
def no_claimable(world):
    assert "no claimable" in world["digest_text"].casefold()
    assert "no claimable" in world["digest_html"].casefold()
