"""Audit diff — resolved / introduced / unchanged (RFC §14.3)."""
from __future__ import annotations

from dataclasses import dataclass

from psa.core.pipeline import Audit


@dataclass(frozen=True)
class AuditDiff:
    resolved: tuple[str, ...]
    introduced: tuple[str, ...]
    unchanged: tuple[str, ...]
    reprioritised: tuple[tuple[str, str, str], ...]

    def to_dict(self) -> dict:
        return {
            "resolved": list(self.resolved),
            "introduced": list(self.introduced),
            "unchanged": list(self.unchanged),
            "reprioritised": [list(x) for x in self.reprioritised],
        }


def diff_audits(*, current: Audit, baseline: Audit) -> AuditDiff:
    cur = {f.id: f for f in current.findings}
    base = {f.id: f for f in baseline.findings}
    resolved = tuple(sorted(i for i in base if i not in cur))
    introduced = tuple(sorted(i for i in cur if i not in base))
    unchanged = tuple(sorted(i for i in cur if i in base))
    reprioritised = tuple(
        sorted(
            (i, base[i].priority, cur[i].priority)
            for i in unchanged
            if base[i].priority != cur[i].priority
        )
    )
    return AuditDiff(
        resolved=resolved,
        introduced=introduced,
        unchanged=unchanged,
        reprioritised=reprioritised,
    )
