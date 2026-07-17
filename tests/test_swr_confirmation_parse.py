"""Unit tests for SWR confirmation parsing (no live portal)."""
from __future__ import annotations

import pytest

from trainline.adapters.claim_submission import parse_swr_confirmation


def test_rejects_nav_automated_claims_false_positive():
    body = (
        "Make a claim\nAutomated claims\nReview claim details\n"
        "Submit claim\nreCAPTCHA\n"
    )
    with pytest.raises(RuntimeError, match="still visible"):
        parse_swr_confirmation(
            body,
            "https://delayrepay.southwesternrailway.com/en/make-claim",
            "2026-07-16",
            submit_still_visible=True,
        )


def test_does_not_treat_automated_as_reference():
    body = (
        "Make a claim\nAutomated claims\nThank you\n"
        "Your claim has been submitted\n"
    )
    ref = parse_swr_confirmation(
        body,
        "https://delayrepay.southwesternrailway.com/en/account",
        "2026-07-16",
        submit_still_visible=False,
    )
    assert ref == "SUBMITTED-2026-07-16"


def test_extracts_claim_reference_token():
    body = "Claim reference: ABC12345\nThank you for your claim."
    ref = parse_swr_confirmation(
        body,
        "https://delayrepay.southwesternrailway.com/en/confirmation",
        "2026-07-16",
        submit_still_visible=False,
    )
    assert ref == "ABC12345"


def test_extracts_swr_claim_id():
    body = "Claim SWR-0218-108-579\nStatus In Progress\nTravel date 16/07/2026"
    ref = parse_swr_confirmation(
        body,
        "https://delayrepay.southwesternrailway.com/en/account",
        "2026-07-16",
        submit_still_visible=False,
    )
    assert ref == "SWR-0218-108-579"
