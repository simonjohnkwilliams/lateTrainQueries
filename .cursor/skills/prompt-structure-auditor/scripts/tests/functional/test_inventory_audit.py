"""Functional: inventory and empty audit for walking skeleton."""
from __future__ import annotations

from tests.conftest import VR1, VR2, VR3

from psa.core.canon import dumps
from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.report.inventory import render_inventory


def test_analyze_vr1_empty_findings_and_inventory():
    audit = analyze(LocalRepoFS(VR1), tool_version="0.1.0")
    assert audit.findings == ()
    inv_text = render_inventory(audit.inventory)
    assert "CLAUDE.md" in inv_text or "Claude" in inv_text
    assert "Not found" in inv_text or "[ ]" in inv_text
    assert "research" in inv_text.lower() or any(
        r.adapter == "research_data" or r.status == "out_of_scope"
        for r in audit.inventory.rows
    )


def test_analyze_deterministic_bytes():
    fs = LocalRepoFS(VR3)
    a = dumps(analyze(fs, tool_version="0.1.0").to_dict())
    b = dumps(analyze(fs, tool_version="0.1.0").to_dict())
    assert a == b


def test_vr2_inventory_shows_cursor_rules():
    audit = analyze(LocalRepoFS(VR2), tool_version="0.1.0")
    text = render_inventory(audit.inventory)
    assert "Cursor" in text or "cursor" in text.lower()
    assert "[x]" in text
