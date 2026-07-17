"""Story 3.3: CLI composition-root unit checks (AD-8, batching).

Complements the end-to-end BDD scenarios in test_bdd_pipeline.py.
"""
import ast
import os
from datetime import date

import pytest

from tests._fakes import FakeResponse, FakeSession, FakeSmtpTransport
from trainline import cli
from trainline.adapters.config import make_config
from trainline.adapters.hsp_client import HspClient

PKG_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, "trainline"))


@pytest.mark.offline
def test_batches_helper_chunks_correctly():
    assert list(cli._batches([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(cli._batches([1, 2, 3], 10)) == [[1, 2, 3]]
    assert list(cli._batches([], 3)) == []


@pytest.mark.offline
def test_all_dates_processed_even_with_batch_size_one(tmp_path):
    def handler(url, kw):
        if "serviceMetrics" in url:
            return FakeResponse({"Services": []})  # no services any day
        return FakeResponse({"serviceAttributesDetails": {}})

    client = HspClient("u", "p", session=FakeSession(handler=handler))
    cfg = make_config(batch_size=1)
    dates = ["2026-05-25", "2026-05-26", "2026-05-27"]
    summary, _day_results = cli.run(
        cfg, dates, str(tmp_path / "c.csv"), str(tmp_path / "c.json"),
        client=client)
    assert summary["days_total"] == 3
    assert summary["analysed"] == 3
    assert summary["total_claims"] == 0


@pytest.mark.offline
def test_cli_is_sole_orchestrator():
    # AD-8: only cli imports the fetch/write adapters; nothing else orchestrates.
    orchestration_targets = ("adapters.hsp_client", "adapters.storage")
    offenders = {}
    for root, _dirs, files in os.walk(PKG_ROOT):
        if "__pycache__" in root:
            continue
        for name in files:
            if not name.endswith(".py") or name == "cli.py":
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
                elif isinstance(node, ast.Import):
                    imports.update(a.name for a in node.names)
            bad = {m for m in imports
                   if any(t in m for t in orchestration_targets)}
            if bad:
                offenders[os.path.relpath(path, PKG_ROOT)] = sorted(bad)
    assert not offenders, f"non-cli modules orchestrate adapters: {offenders}"


@pytest.mark.offline
def test_lookback_weekdays_skips_weekends():
    from trainline.adapters.config import make_config
    cfg = make_config(to_date="2026-07-13", lookback_days=3)  # Mon
    days = cli.lookback_weekdays(cfg, today=date(2026, 7, 15))
    assert days == ["2026-07-09", "2026-07-10", "2026-07-13"]


@pytest.mark.offline
def test_main_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


@pytest.mark.offline
def test_help_lists_digest_flags(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--digest" in help_text
    assert "--no-digest" in help_text
    assert "--digest-strict" in help_text
    assert "--check-tickets" in help_text
    assert "--ticket-dir" in help_text
    assert "--classify-tickets" in help_text
    assert "--tickets-root" in help_text
    assert "--file" in help_text
    assert "--live-submit" in help_text


@pytest.mark.offline
def test_digest_body_marks_fetch_failed_distinct_from_no_claim(
        monkeypatch, tmp_path):
    """Manual case 6 offline: digest text separates FETCH_FAILED from no-claim."""
    from trainline.engine.models import FetchStatus, FetchedDay

    calls = {"n": 0}

    def fake_fetch_day(client, day, *args, **kwargs):
        calls["n"] += 1
        if day == "2026-07-09":
            return FetchedDay(date=day, status=FetchStatus.FETCH_FAILED)
        return FetchedDay(date=day, status=FetchStatus.OK)

    transport = FakeSmtpTransport()
    monkeypatch.setattr(cli, "_digest_transport", transport)
    monkeypatch.setattr(cli, "fetch_day", fake_fetch_day)
    monkeypatch.setattr(
        cli, "build_client",
        lambda **kw: HspClient("u", "p", session=FakeSession()))

    for key, value in {
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USER": "sender@example.test",
        "SMTP_PASSWORD": "s3cret",
        "DIGEST_TO": "simon@example.test",
    }.items():
        monkeypatch.setenv(key, value)

    creds = tmp_path / "creds.txt"
    creds.write_text("[configuration]\nusername=u\npassword=p\n", encoding="utf-8")
    rc = cli.main([
        "--digest",
        "--from-date", "2026-07-08",
        "--to-date", "2026-07-09",
        "--out-dir", str(tmp_path / "Results"),
        "--credentials-file", str(creds),
        "--cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == 0
    assert len(transport.sent) == 1
    msg, _ = transport.sent[0]
    text = msg.get_body(preferencelist=("plain",)).get_content()
    idx = text.casefold().index("not analysed")
    failed_section = text[idx:]
    assert "2026-07-09" in failed_section
    assert "2026-07-08" not in failed_section


@pytest.mark.offline
def test_no_cancellations_flag_disables_fallback(monkeypatch, tmp_path):
    # --no-cancellations should turn the AD-6 gate off for the run's config.
    captured = {}

    def fake_run(config, dates, out_csv, out_json, **kw):
        captured["config"] = config
        return cli.summarise([]), []

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["--from-date", "2026-07-10", "--to-date", "2026-07-10",
              "--out-dir", str(tmp_path), "--no-cancellations"])
    assert captured["config"].enable_cancellation_fallback is False


@pytest.mark.offline
def test_cancellations_enabled_by_default(monkeypatch, tmp_path):
    captured = {}

    def fake_run(config, dates, out_csv, out_json, **kw):
        captured["config"] = config
        return cli.summarise([]), []

    monkeypatch.setattr(cli, "run", fake_run)
    cli.main(["--from-date", "2026-07-10", "--to-date", "2026-07-10",
              "--out-dir", str(tmp_path)])
    assert captured["config"].enable_cancellation_fallback is True
