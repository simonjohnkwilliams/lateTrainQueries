"""Tests for patch validate invariant."""
from __future__ import annotations

from pathlib import Path

from tests.conftest import FIXTURES

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.patch.generate import preview_patch
from psa.patch.validate import validate_patch


def test_validate_order001_passes():
    fs = LocalRepoFS(FIXTURES / "vr3_demo")
    audit = analyze(fs, tool_version="0.1.0")
    patch = preview_patch(fs, audit, "ORDER001")
    result = validate_patch(fs, audit, patch, tool_version="0.1.0")
    assert result.ok is True
    assert patch.finding_id in result.resolved
    assert result.introduced == ()


def test_validate_bad_patch_fails(tmp_path: Path):
    # Copy fixture and craft a worsening patch: prepend more Current Focus noise
    src = FIXTURES / "vr3_demo" / "AGENTS.md"
    repo = tmp_path / "repo"
    repo.mkdir()
    text = src.read_text(encoding="utf-8")
    (repo / "AGENTS.md").write_text(text, encoding="utf-8")
    fs = LocalRepoFS(repo)
    audit = analyze(fs, tool_version="0.1.0")
    patch = preview_patch(fs, audit, "ORDER001")
    # Corrupt new_text to introduce another early Current Focus
    bad_text = "## Current Focus: EXTRA\nBad.\n\n" + patch.new_text
    from psa.patch.generate import Patch

    bad = Patch(
        finding_id=patch.finding_id,
        rule_id=patch.rule_id,
        path=patch.path,
        diff=patch.diff,
        new_text=bad_text,
    )
    result = validate_patch(fs, audit, bad, tool_version="0.1.0")
    assert result.ok is False
    assert result.introduced or not result.resolved or result.failures
