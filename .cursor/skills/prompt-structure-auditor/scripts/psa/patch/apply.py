"""Patch apply — only after validation; branch + one commit + rollback text."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from psa.core.pipeline import Audit
from psa.patch.generate import Patch
from psa.patch.validate import ValidationResult


@dataclass(frozen=True)
class ApplyResult:
    branch: str
    commit: str
    path: str
    rollback_instructions: str
    message: str

    def to_dict(self) -> dict:
        return {
            "branch": self.branch,
            "commit": self.commit,
            "path": self.path,
            "rollback_instructions": self.rollback_instructions,
            "message": self.message,
        }


def apply_patch(
    repo_root: str | Path,
    audit: Audit,
    patch: Patch,
    *,
    validated: bool,
    validation: ValidationResult | None = None,
    branch: str | None = None,
) -> ApplyResult:
    if not validated:
        raise ValueError("refuse to apply: validation was not run (validated=False)")
    if validation is None or not validation.ok:
        raise ValueError("refuse to apply: validation did not pass")

    root = Path(repo_root).resolve()
    if not (root / ".git").exists():
        raise ValueError(f"not a git repository: {root}")

    short = patch.finding_id.replace("f_", "")[:8]
    branch_name = branch or f"psa/fix-{patch.rule_id.lower()}-{short}"
    msg = f"psa: apply {patch.rule_id} ({patch.finding_id})"

    _run(root, ["git", "checkout", "-b", branch_name])
    target = root / patch.path.replace("\\", "/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patch.new_text, encoding="utf-8")
    _run(root, ["git", "add", "--", patch.path.replace("\\", "/")])
    _run(
        root,
        ["git", "-c", "user.email=psa@local", "-c", "user.name=psa", "commit", "-m", msg],
    )
    commit = _run(root, ["git", "rev-parse", "HEAD"]).stdout.strip()
    rollback = (
        f"Rollback: git checkout - && git branch -D {branch_name}\n"
        f"Or revert commit: git revert {commit}"
    )
    return ApplyResult(
        branch=branch_name,
        commit=commit,
        path=patch.path,
        rollback_instructions=rollback,
        message=msg,
    )


def _run(cwd: Path, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
