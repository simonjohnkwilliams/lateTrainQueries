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
def test_render_ops_email_table1_surplus_and_filed():
    from trainline.adapters.ops_email import render_ops_email

    table1 = {
        "claimable": [
            {
                "date": "2026-07-24",
                "direction": "outbound",
                "band": "15-29",
                "route": "GOD->WAT",
                "delay": 18,
            },
            {
                "date": "2026-07-24",
                "direction": "inbound",
                "band": "15-29",
                "route": "WAT->GOD",
                "delay": 27,
            },
        ],
        "newly_filed": [
            {
                "date": "2026-07-24",
                "direction": "outbound",
                "outcome": "filed",
                "reference": "FAKE-SWR-0001",
            },
            {
                "date": "2026-07-24",
                "direction": "inbound",
                "outcome": "filed",
                "reference": "FAKE-SWR-0002",
            },
        ],
        "skipped_no_ticket": ["2026-07-20", "2026-07-21", "2026-07-22"],
        "surplus_tickets": [
            {
                "date": "2026-07-23",
                "path": "tickets/processed/ready_to_claim/07-23-Terminals.jpg",
            }
        ],
        "rejections": [],
    }
    html, text = render_ops_email(
        table1=table1, table2=None, anchor_friday="2026-07-31"
    )
    blob = (html + text).casefold()
    assert "2026-07-24" in blob
    assert "newly filed" in blob
    assert "fake-swr-0001" in blob
    assert "2026-07-20" in blob
    assert "no matching late trains" in blob or "no claimable delay" in blob
    assert "07-23" in blob
    assert "table 2" not in blob


@pytest.mark.offline
def test_render_ops_email_table2_statuses():
    pytest.skip("Table 2 deferred to next epic")


@pytest.mark.offline
def test_render_ops_email_omits_reported_paid_rows():
    pytest.skip("Table 2 deferred to next epic")


@pytest.mark.offline
def test_ops_email_subject_mentions_weekly_ops_and_anchor():
    from trainline.adapters.ops_email import ops_email_subject

    subject = ops_email_subject(
        anchor_friday="2026-07-17", filed=2, claimable=7
    )
    assert "2026-07-17" in subject
    assert "ops" in subject.casefold() or "weekly" in subject.casefold()


@pytest.mark.offline
def test_ops_email_module_does_not_import_gmail():
    import trainline.adapters.ops_email as ops_email

    src = Path(ops_email.__file__).read_text(encoding="utf-8")
    assert "import gmail" not in src.casefold()
    assert "from trainline.adapters.gmail" not in src
    assert "from trainline.adapters.config" not in src
