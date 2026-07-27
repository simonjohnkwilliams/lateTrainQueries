"""Stability / content classification (RFC §6.4).

ORDER001 uses only *prefix-poisoning* volatility (session-dynamic values).
STYLE001 uses broader *worklog* markers. These are intentionally distinct.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Session-dynamic values that poison a reusable stable prefix when placed early.
_PREFIX_POISON_HEADING = re.compile(
    r"(?i)\b(current\s+focus|current\s+sprint|current\s+task|current\s+date|"
    r"today'?s?\s+date|timestamp|session\s+counter)\b"
)
_PREFIX_POISON_BODY = re.compile(
    r"(?i)\b(current\s+sprint\s*[:=#]?\s*\d+|build\s+#?\d+|ticket\s+#?\d+|"
    r"session\s+counter|as\s+of\s+\d{4}-\d{2}-\d{2})\b"
)

# Narrative / worklog markers — STYLE001, not ORDER001.
_WORKLOG_HEADING = re.compile(
    r"(?i)\b(decision:|debugging|known\s+issue|on\s+hold|status|work\s*log|"
    r"session\s+notes|changelog)\b"
)

_REFERENCE_PATH = re.compile(
    r"(?i)_bmad-output/|planning-artifacts|implementation artefact|current story"
)

_STABLE_HEADING = re.compile(
    r"(?i)\b(format|standard|architecture|convention|csv|guardrail|"
    r"coding\s+standards|testing\s+strategy|role)\b"
)


@dataclass(frozen=True)
class ClassifyResult:
    stability: str  # stable | volatile | mixed | unknown
    content_kind: str
    volatility_signals: tuple[str, ...]
    confidence: str
    is_worklog: bool = False
    is_prefix_poison: bool = False


def classify_section(heading: str, body: str) -> ClassifyResult:
    signals: list[str] = []
    body_for_volatility = _REFERENCE_PATH.sub("", body)

    prefix_poison = False
    worklog = False

    if _PREFIX_POISON_HEADING.search(heading):
        prefix_poison = True
        signals.append(f"prefix_poison_heading:{heading.strip()}")
    for m in _PREFIX_POISON_BODY.finditer(body_for_volatility):
        prefix_poison = True
        signals.append(f"prefix_poison_body:{m.group(0)}")

    if _WORKLOG_HEADING.search(heading):
        worklog = True
        signals.append(f"worklog_heading:{heading.strip()}")

    # Embedded volatile span inside otherwise stable heading → mixed
    # (heading itself must not be a prefix-poison heading such as "Current Focus: CSV …")
    if (
        _STABLE_HEADING.search(heading)
        and prefix_poison
        and not _PREFIX_POISON_HEADING.search(heading)
    ):
        return ClassifyResult(
            stability="mixed",
            content_kind="standard",
            volatility_signals=tuple(signals),
            confidence="high",
            is_worklog=worklog,
            is_prefix_poison=True,
        )

    if prefix_poison:
        return ClassifyResult(
            stability="volatile",
            content_kind="state",
            volatility_signals=tuple(signals),
            confidence="high",
            is_worklog=worklog,
            is_prefix_poison=True,
        )

    if worklog:
        # Worklog narrative is volatile for STYLE purposes but not ORDER prefix poison.
        return ClassifyResult(
            stability="volatile",
            content_kind="state",
            volatility_signals=tuple(signals),
            confidence="medium",
            is_worklog=True,
            is_prefix_poison=False,
        )

    kind = "instruction"
    if _STABLE_HEADING.search(heading):
        kind = "standard"
    return ClassifyResult(
        stability="stable",
        content_kind=kind,
        volatility_signals=(),
        confidence="high",
        is_worklog=False,
        is_prefix_poison=False,
    )
