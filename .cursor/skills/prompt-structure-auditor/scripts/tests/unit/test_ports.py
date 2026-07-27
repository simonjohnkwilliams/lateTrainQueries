"""Unit tests: RepoFS is read-only and path-normalized."""
from __future__ import annotations

from psa.core.ports import LocalRepoFS, MemoryRepoFS


def test_memory_repo_lists_and_reads():
    fs = MemoryRepoFS(
        {
            "AGENTS.md": "# hi\n",
            ".cursor/rules/a.mdc": "rule\n",
        }
    )
    paths = fs.list_files()
    assert "AGENTS.md" in paths
    assert fs.read_text("AGENTS.md") == "# hi\n"
    assert fs.exists("AGENTS.md")
    assert not fs.exists("missing.md")


def test_local_repo_reads_fixture(tmp_path):
    (tmp_path / "AGENTS.md").write_text("x\n", encoding="utf-8")
    fs = LocalRepoFS(tmp_path)
    assert fs.read_text("AGENTS.md") == "x\n"
    assert "AGENTS.md" in fs.list_files()
