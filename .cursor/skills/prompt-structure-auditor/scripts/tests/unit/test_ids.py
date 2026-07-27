"""Unit tests: stable IDs do not use clocks or randomness."""
from __future__ import annotations

from psa.core.ids import content_id, finding_id, segment_id


def test_segment_id_stable():
    a = segment_id(path="AGENTS.md", anchor=("Current Focus: CSV Import",), order=0, kind="instruction")
    b = segment_id(path="AGENTS.md", anchor=("Current Focus: CSV Import",), order=0, kind="instruction")
    assert a == b
    assert a.startswith("s_")


def test_finding_id_stable():
    a = finding_id(
        rule_id="ORDER001",
        path="AGENTS.md",
        anchor=("Current Focus: CSV Import",),
        excerpt="## Current Focus: CSV Import",
    )
    b = finding_id(
        rule_id="ORDER001",
        path="AGENTS.md",
        anchor=("Current Focus: CSV Import",),
        excerpt="## Current Focus: CSV Import",
    )
    assert a == b
    assert a.startswith("f_")


def test_content_id_changes_with_input():
    assert content_id("a") != content_id("b")
