"""Behaviour: VOL002 / classifier — references are not embeds."""
from __future__ import annotations

from psa.model.classify import classify_section


def test_reference_to_bmad_output_is_stable_not_volatile():
    text = (
        "Before changing code always:\n"
        "1. Read _bmad-output/planning-artifacts/briefs\n"
        "2. Read the implementation artefact for the current story\n"
    )
    result = classify_section("Instructions", text)
    assert result.stability == "stable"
    assert result.is_prefix_poison is False


def test_current_focus_heading_is_volatile():
    text = "Primary flow is now CSV upload for bank transactions.\n"
    result = classify_section("Current Focus: CSV Import", text)
    assert result.stability == "volatile"
    assert result.is_prefix_poison is True
    assert result.volatility_signals


def test_on_hold_is_worklog_not_prefix_poison():
    result = classify_section("TrueLayer (On Hold – Can Return)", "Revisit later.\n")
    assert result.is_worklog is True
    assert result.is_prefix_poison is False


def test_debugging_is_worklog_not_prefix_poison():
    result = classify_section("Debugging invalid client_id", "Notes...\n")
    assert result.is_worklog is True
    assert result.is_prefix_poison is False


def test_mixed_stable_heading_with_embedded_poison():
    result = classify_section(
        "CSV Format",
        "Headers: Date\nCurrent sprint: 47\n",
    )
    assert result.stability == "mixed"
    assert result.is_prefix_poison is True
