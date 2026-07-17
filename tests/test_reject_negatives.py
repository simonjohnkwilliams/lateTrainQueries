"""Negative tests: image-quality gates vs content reject rules."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from trainline.adapters.ticket_intake import (
    FakeOcrEngine,
    OcrResult,
    assess_ticket_content,
    classify_unclassified,
    is_clearly_wrong_route,
    is_god_wat_route,
    is_wrong_document,
    tickets_layout,
)
from trainline.adapters.ticket_quality import (
    REASON_LOW_RESOLUTION,
    REASON_PDF,
    REASON_TOO_DARK,
    assess_image_quality,
    is_documented_reject,
)

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "tickets" / "golden"


def _expected() -> dict:
    return json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))


# --- Content rules (readable but unwanted) ---------------------------------

BURGESS_TRANSCRIPT = (
    "Anytime Day Return from Guildford to Burgess Hill "
    "Date of travel 16-JUL-2024 Adult Standard Class"
)
CHRISTCHURCH_TRANSCRIPT = (
    "from Burgess Hill to Christchurch Date of travel 10-MAY-19 "
    "Adult Standard Class ANY PERMITTED"
)
CHESTERFIELD_TRANSCRIPT = (
    "Off-Peak Return from Chesterfield to London Terminals "
    "Valid 03-JNR-17 until 02-FBY-17 Adult Standard Class"
)
RECEIPT_TRANSCRIPT = (
    "RECEIPT NOT VALID FOR TRAVEL 2 RAIL TICKETS Date 13-MCH-17 "
    "Amount £17-00 Issuing office LONDON M'BONE Vat Reg no. 667-3877-77"
)
VOUCHER_TRANSCRIPT = (
    "DEBIT/CREDIT CARD SALES VOUCHER Qty 001 Description TICKET "
    "Total £31.00 Date 29-SEP-17 Issuing Office GUILDFORD "
    "CARDHOLDER'S COPY Authorised Sale Confirmed"
)


@pytest.mark.offline
def test_content_wrong_route_burgess_is_readable_but_rejected():
    """We can read Burgess Hill — we just do not want it."""
    assert is_god_wat_route(BURGESS_TRANSCRIPT) is False
    assert is_clearly_wrong_route(BURGESS_TRANSCRIPT) is True
    c = assess_ticket_content(BURGESS_TRANSCRIPT)
    assert c.verdict == "wrong_route"
    assert "wrong_route" in c.reasons


@pytest.mark.offline
def test_content_wrong_route_christchurch_and_chesterfield():
    assert assess_ticket_content(CHRISTCHURCH_TRANSCRIPT).verdict == "wrong_route"
    assert assess_ticket_content(CHESTERFIELD_TRANSCRIPT).verdict == "wrong_route"
    assert is_god_wat_route(CHESTERFIELD_TRANSCRIPT) is False


@pytest.mark.offline
def test_content_receipt_and_voucher_are_wrong_documents():
    assert is_wrong_document(RECEIPT_TRANSCRIPT) is True
    assert is_wrong_document(VOUCHER_TRANSCRIPT) is True
    assert assess_ticket_content(RECEIPT_TRANSCRIPT).verdict == "wrong_document"
    assert assess_ticket_content(VOUCHER_TRANSCRIPT).verdict == "wrong_document"
    # Must not be mistaken for a claimable GOD route
    assert is_god_wat_route(RECEIPT_TRANSCRIPT) is False


@pytest.mark.offline
def test_content_god_ticket_still_accepts():
    text = (
        "Valid for one journey from Godalming to London Terminals "
        "Date of travel 07-JNR-25 Adult Standard Class"
    )
    assert assess_ticket_content(text).verdict == "accept"
    assert assess_ticket_content(text).ok is True


@pytest.mark.offline
def test_classify_wrong_route_goes_to_not_valid_route_not_unreadable(tmp_path):
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    (layout.unclassified / "burgess.jpg").write_bytes(b"X")
    (layout.unclassified / "chesterfield.jpg").write_bytes(b"Y")
    ocr = FakeOcrEngine({
        "burgess.jpg": OcrResult(BURGESS_TRANSCRIPT, 80.0),
        "chesterfield.jpg": OcrResult(CHESTERFIELD_TRANSCRIPT, 75.0),
    })
    summary = classify_unclassified(
        layout, ocr, now=datetime(2026, 7, 16, 16, 0, 0))
    assert summary.ready == 0
    assert summary.rejected == 2
    assert all(i.outcome == "rejected_route" for i in summary.items)
    names = {p.name for p in layout.rejected.iterdir() if p.is_file()}
    assert any(n.startswith("Not_valid_Route-") for n in names)
    assert not any(n.startswith("unreadable-") for n in names)


@pytest.mark.offline
def test_classify_receipt_goes_to_not_valid_document(tmp_path):
    layout = tickets_layout(tmp_path / "tickets")
    layout.ensure()
    (layout.unclassified / "receipt.jpg").write_bytes(b"R")
    (layout.unclassified / "voucher.jpg").write_bytes(b"V")
    ocr = FakeOcrEngine({
        "receipt.jpg": OcrResult(RECEIPT_TRANSCRIPT, 70.0),
        "voucher.jpg": OcrResult(VOUCHER_TRANSCRIPT, 70.0),
    })
    summary = classify_unclassified(
        layout, ocr, now=datetime(2026, 7, 16, 16, 0, 0))
    assert summary.ready == 0
    assert all(i.outcome == "rejected_document" for i in summary.items)
    names = {p.name for p in layout.rejected.iterdir() if p.is_file()}
    assert any(n.startswith("Not_valid_Document-") for n in names)


@pytest.mark.offline
def test_golden_reject_transcripts_match_content_rules():
    """Golden reject fixtures carry transcripts that encode the content rule."""
    data = _expected()
    cases = {
        "reject_wrong_route_burgess_christchurch.jpg": "wrong_route",
        "reject_wrong_route_chesterfield.jpg": "wrong_route",
        "reject_receipt_not_ticket.jpg": "wrong_document",
        "reject_sales_voucher.jpg": "wrong_document",
    }
    for name, verdict in cases.items():
        rec = data["reject"][name]
        text = rec.get("transcript")
        assert text, f"{name} needs a transcript for content tests"
        assert assess_ticket_content(text).verdict == verdict, name
        # Image exists (for future vision OCR negatives)
        assert (GOLDEN / "reject" / name).is_file()


# --- Image quality gates ---------------------------------------------------

@pytest.mark.offline
def test_quality_rejects_pdf_and_tiny_and_dark(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    q = assess_image_quality(pdf)
    assert q.ok is False
    assert REASON_PDF in q.codes

    tiny = tmp_path / "tiny.jpg"
    Image.new("RGB", (50, 50), (128, 128, 128)).save(tiny)
    q2 = assess_image_quality(tiny)
    assert q2.ok is False
    assert REASON_LOW_RESOLUTION in q2.codes

    dark = tmp_path / "dark.jpg"
    Image.new("RGB", (800, 600), (5, 5, 5)).save(dark)
    q3 = assess_image_quality(dark)
    assert q3.ok is False
    assert REASON_TOO_DARK in q3.codes


@pytest.mark.offline
def test_quality_documented_multi_ticket_reasons():
    data = _expected()
    for name in (
        "reject_multi_ticket_cropped.jpg",
        "reject_multi_ticket_day_tc.jpg",
    ):
        path = GOLDEN / "reject" / name
        reasons = is_documented_reject(path, data["reject"])
        assert "multiple_tickets" in reasons
        assert "cropped_incomplete" in reasons
        # Photo itself may or may not trip auto glare/resolution — content rule is documented
        assert path.is_file()


@pytest.mark.offline
def test_quality_gold_accept_sample_opens():
    path = GOLDEN / "day_return_2025-01-06_god_terminals.jpg"
    q = assess_image_quality(path)
    assert isinstance(q.ok, bool)
    # Gold samples should not fail basic open/type checks
    assert "unsupported" not in q.summary
