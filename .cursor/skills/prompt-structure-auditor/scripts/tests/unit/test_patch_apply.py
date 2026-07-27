"""Tests for patch apply (branch + commit)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from tests.conftest import FIXTURES

from psa.core.pipeline import analyze
from psa.core.ports import LocalRepoFS
from psa.patch.apply import apply_patch
from psa.patch.generate import preview_patch
from psa.patch.validate import validate_patch


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def test_apply_requires_validation(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text(
        (FIXTURES / "vr3_demo" / "AGENTS.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git_init(repo)
    fs = LocalRepoFS(repo)
    audit = analyze(fs, tool_version="0.1.0")
    patch = preview_patch(fs, audit, "ORDER001")
    try:
        apply_patch(repo, audit, patch, validated=False)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_apply_creates_branch_and_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text(
        (FIXTURES / "vr3_demo" / "AGENTS.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git_init(repo)
    fs = LocalRepoFS(repo)
    audit = analyze(fs, tool_version="0.1.0")
    patch = preview_patch(fs, audit, "ORDER001")
    v = validate_patch(fs, audit, patch, tool_version="0.1.0")
    assert v.ok
    result = apply_patch(repo, audit, patch, validated=True, validation=v)
    assert result.branch.startswith("psa/fix-")
    assert result.commit
    assert "rollback" in result.rollback_instructions.lower() or "git" in result.rollback_instructions.lower()
    # file changed on disk
    new = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert new.index("## CSV Format") < new.index("## Current Focus")
