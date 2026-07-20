"""Offline characterisation of SWR Delay Repay claim-status emails (FR37/FR38)."""
from __future__ import annotations

import pytest

from tests.fixtures.swr_claim_mail.samples import (
    APPROVED,
    CLAIM_ID,
    PAYMENT_SENT,
    RECEIVED,
)
from trainline.adapters.gmail.claim_mail import (
    ClaimMailStage,
    looks_like_swr_sender,
    parse_swr_claim_mail,
    swr_claim_search_query,
)


@pytest.mark.offline
@pytest.mark.parametrize(
    "sample,expected_stage",
    [
        (RECEIVED, ClaimMailStage.RECEIVED),
        (APPROVED, ClaimMailStage.APPROVED),
        (PAYMENT_SENT, ClaimMailStage.PAYMENT_SENT),
    ],
)
def test_parse_swr_claim_mail_stages(sample, expected_stage):
    parsed = parse_swr_claim_mail(
        subject=sample["subject"],
        from_addr=sample["from_addr"],
        body=sample["body"],
    )
    assert parsed is not None
    assert parsed.claim_id == CLAIM_ID
    assert parsed.stage is expected_stage
    assert looks_like_swr_sender(parsed.from_addr)
    assert parsed.amount_gbp == "1.57"


@pytest.mark.offline
def test_received_carries_journey_summary():
    parsed = parse_swr_claim_mail(**{k: RECEIVED[k] for k in ("subject", "from_addr", "body")})
    assert parsed is not None
    assert parsed.travel_date_raw == "Thu, 16 Jul 2026"
    assert "GODALMING" in (parsed.departing_raw or "")
    assert "15 - 29" in (parsed.delay_raw or "")


@pytest.mark.offline
def test_approved_carries_decision():
    parsed = parse_swr_claim_mail(**{k: APPROVED[k] for k in ("subject", "from_addr", "body")})
    assert parsed is not None
    assert parsed.decision_raw == "Approved"


@pytest.mark.offline
def test_non_swr_subject_returns_none_without_claim_id():
    assert parse_swr_claim_mail(subject="Weekly digest", body="") is None


@pytest.mark.offline
def test_search_query_includes_claim_and_sender():
    q = swr_claim_search_query(CLAIM_ID)
    assert CLAIM_ID in q
    assert "firstcustomercontact.com" in q
    assert "Delay Repay" in q
