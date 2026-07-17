"""Representative offline tests for the live SWR Delay Repay portal contract.

Grounded in dry-run captures under ``live-capture/swr-journey/`` (2026-07-17).
These assert the real labels/ids/roles the Playwright wizard must use — not
placeholder ``input[name=journeyDate]`` toys.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures import swr_portal_contract as contract

CAPTURE = Path(__file__).resolve().parents[1] / "live-capture" / "swr-journey"


@pytest.mark.offline
def test_contract_stepper_and_login_selectors():
    assert contract.STEPPER_STEPS == (
        "Your details",
        "Journey",
        "Ticket",
        "Compensation",
        "Review",
    )
    assert contract.LOGIN["submit"] == "#submit-button"
    assert contract.JOURNEY["find_journey"] == "#find-journey"
    assert contract.JOURNEY["journey_card"] == "sr-journey-card"
    assert "Between 15 - 29 minutes" in contract.JOURNEY["delay_bands"]
    assert contract.TICKET["paper_aria"].startswith("Select Paper")
    assert "5-digit" in contract.TICKET["ticket_number_rule"]
    assert contract.REVIEW["submit_button"] == "Submit claim"


@pytest.mark.offline
@pytest.mark.parametrize(
    "name,needles",
    [
        ("01_login.html", ["Log in to claim Delay Repay", "Email Address", "submit-button"]),
        ("02_account.html", ["Account Summary", "Make a claim"]),
        (
            "05_journey_search_results.html",
            ["Travel date", "find-journey", "Leaving at", "sr-journey-card"],
        ),
        (
            "05b_service_selected.html",
            ["Your selected journey", "Length of delay", "Between 15 - 29 minutes"],
        ),
        (
            "07_ticket_step.html",
            ["Are you claiming for more than one ticket?", "Ticket details"],
        ),
        (
            "10_review_pre_submit.html",
            ["Review claim details", "Submit claim", "reCAPTCHA"],
        ),
    ],
)
def test_captured_html_contains_live_markers(name, needles):
    path = CAPTURE / name
    if not path.is_file():
        pytest.skip(f"capture missing: {path} (run scripts/probe_swr_claim_journey.py)")
    html = path.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in html, f"{name} missing {needle!r}"


@pytest.mark.offline
def test_delay_band_labels_cover_engine_bands():
    from trainline.adapters.swr_mapping import delay_band_label
    from trainline.engine.models import Band

    assert delay_band_label(Band.B15_29) == "Between 15 - 29 minutes"
    assert delay_band_label(Band.B30_59) == "Between 30 - 59 minutes"
    assert delay_band_label(Band.B60_119) == "Between 60 - 119 minutes"
    assert delay_band_label(Band.B120_PLUS) == "120 minutes or more"


@pytest.mark.offline
def test_leaving_at_rounds_to_quarter_hour():
    from trainline.adapters.swr_mapping import leaving_at_search_slot

    assert leaving_at_search_slot("09:41") == "09:30"
    assert leaving_at_search_slot("09:30") == "09:30"
    assert leaving_at_search_slot("09:44") == "09:30"
    assert leaving_at_search_slot("09:45") == "09:45"
