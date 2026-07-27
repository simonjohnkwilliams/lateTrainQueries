"""Rule registry and packs."""
from __future__ import annotations

from typing import Callable, Iterable

from psa.core.config import ConfigView
from psa.findings import Finding
from psa.model.types import PromptModel
from psa.rules import activation, duplication, ordering, style

RuleFn = Callable[[PromptModel, ConfigView], Iterable[Finding]]

_REGISTRY: list[tuple[str, str, RuleFn]] = [
    ("ORDERING", "ORDER001", ordering.check_order001),
    ("ACTIVATION", "ACT001", activation.check_act001),
    ("ACTIVATION", "ACT002", activation.check_act002),
    ("STYLE", "STYLE001", style.check_style001),
    ("DUPLICATION", "DUP001", duplication.check_dup001),
]


def run_rules(model: PromptModel, config: ConfigView) -> list[Finding]:
    out: list[Finding] = []
    enabled = set(config.enabled_packs)
    for pack, _rule_id, fn in _REGISTRY:
        if pack not in enabled:
            continue
        out.extend(fn(model, config))
    return out
