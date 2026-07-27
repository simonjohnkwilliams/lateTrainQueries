"""Patch validation — re-audit scratch copy; must not worsen (RFC §12.3)."""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from psa.core.pipeline import Audit, analyze
from psa.core.ports import LocalRepoFS, RepoFS
from psa.patch.generate import Patch


_PRIORITY_RANK = {
    "High value": 0,
    "Medium value": 1,
    "Low value": 2,
    "Informational": 3,
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    resolved: tuple[str, ...]
    introduced: tuple[str, ...]
    worsened: tuple[tuple[str, str, str], ...]  # id, from, to
    failures: tuple[str, ...]
    after: Audit | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "resolved": list(self.resolved),
            "introduced": list(self.introduced),
            "worsened": [list(w) for w in self.worsened],
            "failures": list(self.failures),
        }


def validate_patch(
    repo: RepoFS,
    before: Audit,
    patch: Patch,
    *,
    tool_version: str = "0.1.0",
) -> ValidationResult:
    """Apply patch to a scratch tree and re-run analyze. Never writes to `repo`."""
    root = Path(repo.root())
    with tempfile.TemporaryDirectory(prefix="psa-validate-") as tmp:
        scratch = Path(tmp) / "scratch"
        _copy_tree(root, scratch)
        target = scratch / patch.path.replace("\\", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch.new_text, encoding="utf-8")
        after = analyze(LocalRepoFS(scratch), tool_version=tool_version)
        return _compare(before, after, patch.finding_id)


def _copy_tree(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "target",
        "out",
    )
    shutil.copytree(src, dst, ignore=ignore)


def _compare(before: Audit, after: Audit, target_id: str) -> ValidationResult:
    before_ids = {f.id: f for f in before.findings}
    after_ids = {f.id: f for f in after.findings}
    resolved = tuple(sorted(i for i in before_ids if i not in after_ids))
    introduced = tuple(sorted(i for i in after_ids if i not in before_ids))
    worsened: list[tuple[str, str, str]] = []
    for fid, bf in before_ids.items():
        af = after_ids.get(fid)
        if af is None:
            continue
        if _PRIORITY_RANK.get(af.priority, 9) < _PRIORITY_RANK.get(bf.priority, 9):
            # lower rank number = higher value = worse left unfixed / escalated
            worsened.append((fid, bf.priority, af.priority))

    failures: list[str] = []
    if target_id not in resolved and target_id in after_ids:
        failures.append(f"target finding {target_id} was not resolved")
    if target_id not in before_ids:
        failures.append(f"target finding {target_id} was not in the before audit")
    if introduced:
        failures.append(f"introduced {len(introduced)} new finding(s)")
    if worsened:
        failures.append(f"worsened priority on {len(worsened)} finding(s)")

    ok = (
        target_id in before_ids
        and target_id in resolved
        and not introduced
        and not worsened
    )
    return ValidationResult(
        ok=ok,
        resolved=resolved,
        introduced=introduced,
        worsened=tuple(worsened),
        failures=tuple(failures),
        after=after,
    )
