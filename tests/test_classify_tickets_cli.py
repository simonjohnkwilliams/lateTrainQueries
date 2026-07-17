"""CLI --classify-tickets with injectable FakeOcr (offline)."""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from trainline import cli
from trainline.adapters.ticket_intake import FakeOcrEngine, OcrResult, tickets_layout


@pytest.mark.offline
def test_cli_classify_tickets_with_fake_ocr(tmp_path, monkeypatch):
    root = tmp_path / "tickets"
    layout = tickets_layout(root)
    layout.ensure()
    (layout.unclassified / "a.jpg").write_bytes(b"A")
    (layout.unclassified / "b.jpg").write_bytes(b"B")

    fake = FakeOcrEngine({
        "a.jpg": OcrResult(
            "Godalming to London Waterloo 10/07/2026 Ref ZX99YY", 90.0),
        "b.jpg": OcrResult("blur", 5.0),
    })
    monkeypatch.setattr(cli, "ensure_ollama_reachable", lambda: True)
    monkeypatch.setattr(cli, "list_ollama_models", lambda: ["trainline-ticket"])
    monkeypatch.setattr(cli, "OllamaVisionOcrEngine", lambda **kwargs: fake)

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main([
            "--classify-tickets",
            "--tickets-root", str(root),
        ])
    assert code == 0, err.getvalue()
    assert list(layout.unclassified.iterdir()) == []
    assert len(list(layout.ready_to_claim.iterdir())) == 1
    rejected_files = [
        p for p in layout.rejected.iterdir()
        if p.is_file() and p.suffix.casefold() in {".jpg", ".jpeg", ".png", ".pdf"}
    ]
    assert len(rejected_files) == 1
    log = err.getvalue()
    assert "reading" in log.casefold() or "[1/" in log
    assert "READY" in log or "ready" in log.casefold()
    assert "REJECT" in log or "rejected" in log.casefold()
    assert "ollama:trainline-ticket" in log.casefold()


@pytest.mark.offline
def test_cli_classify_empty_inbox_explains_next_steps(tmp_path, monkeypatch):
    root = tmp_path / "tickets"
    layout = tickets_layout(root)
    layout.ensure()
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["--classify-tickets", "--tickets-root", str(root)])
    assert code == 0
    combined = err.getvalue()
    assert "Nothing to do" in combined
    assert "unclassified" in combined.casefold()
    assert "inventory" in combined.casefold() or "ready_to_claim" in combined


@pytest.mark.offline
def test_cli_classify_errors_when_ollama_down(tmp_path, monkeypatch):
    root = tmp_path / "tickets"
    layout = tickets_layout(root)
    layout.ensure()
    (layout.unclassified / "a.jpg").write_bytes(b"A")
    monkeypatch.setattr(cli, "ensure_ollama_reachable", lambda: False)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["--classify-tickets", "--tickets-root", str(root)])
    assert code == 2
    assert "Ollama is not reachable" in err.getvalue()


@pytest.mark.offline
def test_help_lists_classify_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--classify-tickets" in help_text
    assert "--tickets-root" in help_text
    assert "--ocr-engine" not in help_text
