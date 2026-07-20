"""Epic 7 / Story 7.4 — ops email Tables 1 and 2 (FR36–FR38).

Each test importorskips until ``trainline.adapters.ops_email`` lands.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _mod():
    return pytest.importorskip(
        "trainline.adapters.ops_email",
        reason="Story 7.4 ops_email renderer not implemented yet",
    )


def _table1_fixture():
    return {
        "claimable": [
            {
                "date": "2026-07-08",
                "direction": "outbound",
                "band": "15-29",
                "route": "GOD->WAT",
                "delay": 18,
            }
        ],
        "matched_tickets": [
            {
                "path": "tickets/processed/ready_to_claim/07-08-god.jpg",
                "date": "2026-07-08",
            }
        ],
        "rejections": [
            {
                "reason": "ocr_low_confidence",
                "path": "tickets/processed/rejected/blurry.jpg",
            }
        ],
        "newly_filed": [{"claim_id": "SWR-0218-108-579", "date": "2026-07-08"}],
        "still_open": [],
    }


def _table2_fixture():
    return [
        {
            "claim_id": "SWR-0001-000-001",
            "status": "received",
            "journey_date": "2026-07-01",
        },
        {
            "claim_id": "SWR-0002-000-002",
            "status": "approved",
            "journey_date": "2026-07-02",
        },
        {
            "claim_id": "SWR-0003-000-003",
            "status": "in_flight",
            "journey_date": "2026-07-03",
        },
    ]


@pytest.mark.offline
def test_render_ops_email_table1_contains_late_trains_rejects_and_filed():
    ops_email = _mod()
    html, text = ops_email.render_ops_email(
        table1=_table1_fixture(),
        table2=_table2_fixture(),
        anchor_friday="2026-07-17",
    )
    blob = (html + text).casefold()
    assert "2026-07-08" in blob
    assert "god" in blob and "wat" in blob
    assert "ocr_low_confidence" in blob or "rejected" in blob
    assert "blurry.jpg" in blob or "rejected" in blob
    assert "swr-0218-108-579" in blob


@pytest.mark.offline
def test_render_ops_email_table2_statuses():
    ops_email = _mod()
    html, text = ops_email.render_ops_email(
        table1=_table1_fixture(),
        table2=_table2_fixture(),
        anchor_friday="2026-07-17",
    )
    blob = (html + text).casefold()
    assert "received" in blob
    assert "approved" in blob
    assert "in_flight" in blob or "in flight" in blob
    assert "swr-0001-000-001" in blob


@pytest.mark.offline
def test_render_ops_email_omits_reported_paid_rows():
    ops_email = _mod()
    table2 = [
        {
            "claim_id": "SWR-PAID-000-001",
            "status": "paid",
            "journey_date": "2026-06-01",
            "reported_paid": True,
        },
        {
            "claim_id": "SWR-OPEN-000-002",
            "status": "paid",
            "journey_date": "2026-06-08",
            "reported_paid": False,
        },
    ]
    html, text = ops_email.render_ops_email(
        table1=_table1_fixture(),
        table2=[r for r in table2 if not r.get("reported_paid")],
        anchor_friday="2026-07-17",
    )
    blob = (html + text).casefold()
    assert "swr-paid-000-001" not in blob
    assert "swr-open-000-002" in blob


@pytest.mark.offline
def test_ops_email_subject_mentions_weekly_ops_and_anchor():
    ops_email = _mod()
    subject = ops_email.ops_email_subject(anchor_friday="2026-07-17")
    assert "2026-07-17" in subject
    assert "ops" in subject.casefold() or "weekly" in subject.casefold()


@pytest.mark.offline
def test_ops_email_module_does_not_import_gmail():
    ops_email = _mod()
    src = Path(ops_email.__file__).read_text(encoding="utf-8")
    assert "gmail" not in src.casefold()
    assert "from trainline.adapters.config" not in src
