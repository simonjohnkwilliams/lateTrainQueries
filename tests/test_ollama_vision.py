"""Ollama vision OCR — offline helpers + live golden quality gate.

Live gate (all golden accept + reject photos vs local Ollama):
  pytest --vision-gate
  # or
  $env:TRAINLINE_VISION_GATE = "1"; python -m pytest
  # or vision-only
  python -m pytest -m vision -o addopts=
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainline.adapters.ollama_vision import (
    TicketVisionFields,
    parse_vision_json,
    vision_fields_to_transcript,
)
from trainline.adapters.ticket_intake import (
    assess_ticket_content,
    is_god_wat_route,
    resolve_journey_date,
)

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "tickets" / "golden"
EXPECTED_PATH = GOLDEN / "expected.json"


def _expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _accept_names() -> list[str]:
    return sorted(_expected()["accept"].keys())


def _reject_names() -> list[str]:
    return sorted(_expected()["reject"].keys())


def _resolve_vision_model(names: list[str]) -> str | None:
    if "trainline-ticket" in names or "trainline-ticket:latest" in names:
        return "trainline-ticket"
    if "qwen2.5vl:7b" in names:
        return "qwen2.5vl:7b"
    return None


# --- Offline helpers --------------------------------------------------------


@pytest.mark.offline
def test_parse_vision_json_plain_and_fenced():
    raw = '{"document_type":"journey_ticket","origin":"Godalming"}'
    assert parse_vision_json(raw)["origin"] == "Godalming"
    fenced = 'Here you go:\n```json\n{"document_type":"receipt","readable":true}\n```\n'
    assert parse_vision_json(fenced)["document_type"] == "receipt"


@pytest.mark.offline
def test_vision_fields_to_transcript_day_return_and_weekly():
    day = TicketVisionFields.from_dict({
        "document_type": "journey_ticket",
        "ticket_kind": "anytime_day_return",
        "origin": "Godalming",
        "destination": "London Terminals",
        "date_of_travel": "2025-01-07",
        "price": "£28.90",
        "ticket_number": "12345",
        "readable": True,
    })
    text = vision_fields_to_transcript(day)
    assert is_god_wat_route(text)
    assert resolve_journey_date(text, "x.jpg").date().isoformat() == "2025-01-07"
    assert "Price 28.90" in text
    assert "Ticket number 12345" in text

    weekly = TicketVisionFields.from_dict({
        "document_type": "journey_ticket",
        "ticket_kind": "travelcard_7day",
        "origin": "Godalming",
        "destination": "London Zones 1-6",
        "start_date": "2020-01-27",
        "valid_until": "2020-02-02",
        "readable": True,
    })
    wtext = vision_fields_to_transcript(weekly)
    assert is_god_wat_route(wtext)
    assert resolve_journey_date(wtext, "w.jpg").date().isoformat() == "2020-01-27"


@pytest.mark.offline
def test_normalise_digital_wallet_same_day_sets_date_of_travel():
    from trainline.adapters.ollama_vision import normalise_vision_fields

    raw = TicketVisionFields.from_dict({
        "document_type": "journey_ticket",
        "ticket_kind": "anytime_day_return",
        "origin": "London Terminals",
        "destination": "Godalming",
        "start_date": "2026-07-24",
        "valid_until": "2026-07-24",
        "date_of_travel": None,
        "ticket_number": "SRBYE8PNEF3",
        "readable": True,
    })
    fixed = normalise_vision_fields(raw)
    assert fixed.date_of_travel == "2026-07-24"
    assert fixed.ticket_kind == "anytime_day_return"
    text = vision_fields_to_transcript(fixed)
    assert is_god_wat_route(text)
    assert resolve_journey_date(text, "digital.png").date().isoformat() == "2026-07-24"
    assert "SRBYE8PNEF3" in text or "Ticket number" in text


@pytest.mark.offline
def test_digital_wallet_fixture_exists_and_is_image():
    path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "tickets"
        / "digital"
        / "national_rail_wallet_lon_god_2026-07-24.png"
    )
    assert path.is_file()
    assert path.stat().st_size > 1000


@pytest.mark.offline
def test_normalise_swaps_inverted_weekly_range():
    from trainline.adapters.ollama_vision import normalise_vision_fields

    raw = TicketVisionFields.from_dict({
        "document_type": "journey_ticket",
        "ticket_kind": "travelcard_7day",
        "origin": "Godalming",
        "destination": "London Zones 1-6",
        "start_date": "10-APR-19",
        "valid_until": "04-APR-19",
        "readable": True,
    })
    fixed = normalise_vision_fields(raw)
    assert fixed.start_date == "04-APR-19"
    assert fixed.valid_until == "10-APR-19"
    text = vision_fields_to_transcript(fixed)
    assert resolve_journey_date(text, "w.jpg").date().isoformat() == "2019-04-04"


# --- Live Ollama quality gate -----------------------------------------------


@pytest.fixture(scope="module")
def vision_engine():
    """Shared Ollama engine for the golden vision gate (one model load)."""
    from trainline.adapters.ollama_vision import (
        OllamaVisionOcrEngine,
        ensure_ollama_reachable,
        list_ollama_models,
    )

    if not ensure_ollama_reachable():
        pytest.skip("Ollama not reachable at http://127.0.0.1:11434")
    model = _resolve_vision_model(list_ollama_models())
    if model is None:
        pytest.skip("Install trainline-ticket or qwen2.5vl:7b for the vision gate")
    return OllamaVisionOcrEngine(model=model)


def _reject_expect_verdict(fail_reasons: list[str]) -> str:
    """Map golden fail_reasons → content verdict we expect from vision text."""
    joined = " ".join(fail_reasons)
    if "multiple_tickets" in joined or "wrong_document" in joined:
        return "wrong_document"
    if "wrong_route" in joined:
        return "wrong_route"
    return "not_accept"


@pytest.mark.vision
@pytest.mark.parametrize("name", _accept_names(), ids=lambda n: n[:40])
def test_vision_gate_accept_golden(name, vision_engine):
    """Quality gate: every golden accept photo → GOD route + expected journey date."""
    rec = _expected()["accept"][name]
    if rec.get("vision_xfail"):
        pytest.xfail(rec["vision_xfail"])
    path = GOLDEN / name
    assert path.is_file(), name
    result = vision_engine.extract(path)
    assert result.text.strip(), f"{name}: empty vision text"
    assert is_god_wat_route(result.text), f"{name}: not GOD↔London\n{result.text}"
    content = assess_ticket_content(result.text)
    assert content.verdict == "accept", f"{name}: {content.verdict} {content.reasons}\n{result.text}"
    got = resolve_journey_date(result.text, name)
    assert got is not None, f"{name}: no journey date\n{result.text}"
    assert got.date().isoformat() == rec["journey_date"], (
        f"{name}: want {rec['journey_date']} got {got.date().isoformat()}\n{result.text}"
    )


@pytest.mark.vision
@pytest.mark.parametrize("name", _reject_names(), ids=lambda n: n[:40])
def test_vision_gate_reject_golden(name, vision_engine):
    """Quality gate: every golden reject photo must not classify as accept."""
    rec = _expected()["reject"][name]
    path = GOLDEN / "reject" / name
    assert path.is_file(), name
    result = vision_engine.extract(path)
    want = _reject_expect_verdict(rec["fail_reasons"])
    text = result.text or ""
    content = assess_ticket_content(text) if text.strip() else None

    if want == "wrong_document":
        ok = (
            "MULTIPLE TICKETS" in text.upper()
            or (content is not None and content.verdict == "wrong_document")
        )
        assert ok, f"{name}: expected wrong_document / multi-ticket\n{text!r}"
        return

    if want == "wrong_route":
        assert content is not None and content.verdict == "wrong_route", (
            f"{name}: expected wrong_route, got "
            f"{content.verdict if content else 'empty'}\n{text!r}"
        )
        return

    # Fallback: must not accept as claimable GOD ticket
    if content is not None:
        assert content.verdict != "accept", f"{name}: unexpectedly accepted\n{text!r}"
    else:
        assert not text.strip() or not is_god_wat_route(text)


@pytest.mark.offline
def test_vision_engine_extract_uses_booking_pdf_text_layer(tmp_path):
    """PDFs skip VL; booking confirmation text layer supplies fare + route."""
    from trainline.adapters.ollama_vision import OllamaVisionOcrEngine
    from trainline.adapters.ticket_intake import parse_ticket_price

    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "tickets"
        / "booking"
        / "B-SWR-TDV0MXMTS.pdf"
    )
    if not fixture.is_file():
        pytest.skip("booking PDF fixture not present")
    path = tmp_path / "booking.pdf"
    path.write_bytes(fixture.read_bytes())
    engine = OllamaVisionOcrEngine(model="unused-for-pdf")
    result = engine.extract(path)
    assert result.confidence >= 90.0
    assert is_god_wat_route(result.text)
    assert parse_ticket_price(result.text) == "38.80"
