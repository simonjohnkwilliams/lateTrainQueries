"""Findings model (RFC §8)."""
from __future__ import annotations

from dataclasses import dataclass

from psa.model.types import Evidence


@dataclass(frozen=True)
class Finding:
    id: str
    rule_id: str
    title: str
    category: str
    priority: str
    verification: str
    observability: str
    confidence: str
    ownership: str
    evidence: tuple[Evidence, ...]
    explanation: str
    recommendation: str
    related: tuple[str, ...] = ()
    patchable: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "verification": self.verification,
            "observability": self.observability,
            "confidence": self.confidence,
            "ownership": self.ownership,
            "evidence": [e.to_dict() for e in self.evidence],
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "related": list(self.related),
            "patchable": self.patchable,
        }


def normalize_findings(raw: list[Finding]) -> tuple[Finding, ...]:
    # Deduplicate by id; deterministic order
    by_id: dict[str, Finding] = {}
    for f in raw:
        by_id[f.id] = f
    priority_rank = {"High value": 0, "Medium value": 1, "Low value": 2, "Informational": 3}
    items = list(by_id.values())
    items.sort(
        key=lambda f: (
            priority_rank.get(f.priority, 9),
            f.rule_id,
            f.evidence[0].path if f.evidence else "",
            f.id,
        )
    )
    return tuple(items)
