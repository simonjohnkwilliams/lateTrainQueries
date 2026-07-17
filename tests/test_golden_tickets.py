"""Golden ticket fixtures — parser contract + upload quality gates (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trainline.adapters.ticket_intake import (
    FakeOcrEngine,
    OcrResult,
    classify_unclassified,
    is_god_wat_route,
    parse_ticket_dates,
    ready_filename,
    resolve_journey_date,
    tickets_layout,
)
from trainline.adapters.ticket_quality import assess_image_quality, is_documented_reject

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "tickets" / "golden"
EXPECTED_PATH = GOLDEN / "expected.json"


def _expected() -> dict:
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.mark.offline
def test_golden_expected_files_exist():
    data = _expected()
    assert data["accept"], "golden accept set must not be empty"
    for name in data["accept"]:
        assert (GOLDEN / name).is_file(), name
    for name in data["reject"]:
        assert (GOLDEN / "reject" / name).is_file(), name
    # Documented drops stay out of the accept set
    dropped = set(data["_meta"]["dropped"])
    sources = {
        v.get("source_ready_name") or v.get("source_rejected_name")
        for v in data["accept"].values()
    }
    assert dropped.isdisjoint(sources)


@pytest.mark.offline
def test_golden_no_duplicate_journey_keys_within_kind():
    """Cherry-pick should not keep two accepts for the same week/day identity."""
    data = _expected()
    # Dropped sources must not appear
    for drop in data["_meta"]["dropped"]:
        assert drop not in {
            v.get("source_ready_name")
            for v in data["accept"].values()
            if v.get("source_ready_name")
        }
    # 10-22 week kept; 10-28 dropped
    sources = {
        v.get("source_ready_name")
        for v in data["accept"].values()
        if v.get("source_ready_name")
    }
    assert "10-22-Start.jpg" in sources
    assert "10-28-Start.jpg" not in sources
    assert "09-17-TRVLCD.jpg" in sources
    assert "09-17-Travelcard.jpg" not in sources
    assert "04-11-terminals.jpg" in sources
    assert "03-26-bodalming.jpg" not in sources


@pytest.mark.offline
@pytest.mark.parametrize("name", sorted(
    json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["accept"].keys()
))
def test_golden_transcript_parses_to_expected_date(name):
    data = _expected()
    rec = data["accept"][name]
    text = rec["transcript"]
    assert is_god_wat_route(text), name
    got = resolve_journey_date(text, name)
    assert got is not None, name
    assert got.date().isoformat() == rec["journey_date"], name
    if rec.get("kind") == "travelcard_7day":
        td = parse_ticket_dates(text)
        assert td.start_date.date().isoformat() == rec["start_date"]
        assert td.valid_until.date().isoformat() == rec["valid_until"]
        assert td.primary.date().isoformat() == rec["start_date"]


@pytest.mark.offline
def test_golden_spot_checks_user_confirmed():
    data = _expected()
    assert data["accept"]["day_return_2024-03-26_god_terminals.jpg"]["journey_date"] == (
        "2024-03-26"
    )
    assert data["accept"]["day_return_2018-09-03_terminals_god.jpg"]["journey_date"] == (
        "2018-09-03"
    )
    assert data["accept"]["weekly_2020-01-27_to_2020-02-02_god_zones.jpg"][
        "journey_date"
    ] == "2020-01-27"
    assert data["accept"]["day_return_2025-01-07_god_terminals.jpg"]["journey_date"] == (
        "2025-01-07"
    )


@pytest.mark.offline
def test_golden_classify_with_fake_ocr_uses_correct_ready_names(tmp_path):
    """End-to-end classify: FakeOcr transcripts → ready MM-DD matches journey_date."""
    data = _expected()
    # Sample a mix: day return, day TC, weekly, APTIS months
    sample_names = [
        "day_return_2025-01-07_god_terminals.jpg",
        "day_return_2024-03-26_god_terminals.jpg",
        "day_tc_2019-07-03_god_zones.jpg",
        "weekly_2020-01-27_to_2020-02-02_god_zones.jpg",
        "day_return_2018-09-03_terminals_god.jpg",
    ]
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    by_name = {}
    for name in sample_names:
        rec = data["accept"][name]
        dest = layout.unclassified / name
        # Tiny placeholder bytes — FakeOcr does not open the image
        dest.write_bytes(b"FAKE")
        by_name[name] = OcrResult(rec["transcript"], 85.0)

    summary = classify_unclassified(layout, FakeOcrEngine(by_name))
    assert summary.ready == len(sample_names)
    assert summary.rejected == 0
    ready = {p.name for p in layout.ready_to_claim.iterdir() if p.is_file()}
    for name in sample_names:
        rec = data["accept"][name]
        journey = resolve_journey_date(rec["transcript"], name)
        assert journey is not None
        prefix = f"{journey.month:02d}-{journey.day:02d}-"
        assert any(r.startswith(prefix) for r in ready), (name, prefix, ready)


@pytest.mark.offline
def test_reject_fixtures_document_fail_reasons():
    data = _expected()
    assert len(data["reject"]) >= 4
    multi = data["reject"]["reject_multi_ticket_cropped.jpg"]
    assert "multiple_tickets" in multi["fail_reasons"]
    receipt = data["reject"]["reject_receipt_not_ticket.jpg"]
    assert "wrong_document_receipt" in receipt["fail_reasons"]
    voucher = data["reject"]["reject_sales_voucher.jpg"]
    assert "wrong_document_voucher" in voucher["fail_reasons"]
    wrong = data["reject"]["reject_wrong_route_chesterfield.jpg"]
    assert "wrong_route" in wrong["fail_reasons"]
    for name in data["reject"]:
        assert (GOLDEN / "reject" / name).is_file(), name
        reasons = is_documented_reject(GOLDEN / "reject" / name, data["reject"])
        assert reasons


@pytest.mark.offline
def test_rescued_unreadable_present_in_accept():
    data = _expected()
    rescued = [
        v for v in data["accept"].values() if v.get("rescued_from") == "unreadable"
    ]
    assert len(rescued) >= 10
    # Spot-check previously "unreadable" day TC / JNR day returns
    assert "day_tc_2019-05-21_god_zones.jpg" in data["accept"]
    assert "day_return_2025-01-08_god_terminals.jpg" in data["accept"]
    assert data["accept"]["day_return_2025-01-08_god_terminals.jpg"][
        "journey_date"
    ] == "2025-01-08"


@pytest.mark.offline
def test_assess_image_quality_runs_on_golden_gold_sample():
    """Smoke: quality gate opens a real gold photo without crashing."""
    path = GOLDEN / "day_return_2025-01-06_god_terminals.jpg"
    result = assess_image_quality(path)
    # May warn on glare for some shots; must return a structured result
    assert isinstance(result.ok, bool)
    assert isinstance(result.reasons, list)


@pytest.mark.offline
def test_ready_filename_matches_golden_journey_dates():
    from datetime import datetime

    data = _expected()
    rec = data["accept"]["weekly_2020-01-27_to_2020-02-02_god_zones.jpg"]
    d = datetime.fromisoformat(rec["journey_date"])
    assert ready_filename(d, "TICKET", ".jpg").startswith("01-27-")
    rec2 = data["accept"]["day_return_2025-01-07_god_terminals.jpg"]
    d2 = datetime.fromisoformat(rec2["journey_date"])
    assert ready_filename(d2, "TICKET", ".jpg").startswith("01-07-")
