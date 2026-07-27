"""Minimal config view — defaults only for v0.1."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

from psa.core.canon import dumps
from psa.core.ids import content_id
from psa.core.ignore_globs import DEFAULT_IGNORE_GLOBS


@dataclass(frozen=True)
class ConfigView:
    enabled_packs: tuple[str, ...] = (
        "ORDERING",
        "VOLATILITY",
        "DUPLICATION",
        "ACTIVATION",
        "STYLE",
        "OWNERSHIP",
        "CONTRADICTION",
    )
    apply_default_ignores: bool = True
    extra_ignore_globs: tuple[str, ...] = ()
    extra: Mapping[str, object] = field(default_factory=dict)

    def effective_ignore_globs(self) -> tuple[str, ...]:
        if not self.apply_default_ignores:
            return self.extra_ignore_globs
        return DEFAULT_IGNORE_GLOBS + self.extra_ignore_globs

    def with_no_default_ignores(self) -> ConfigView:
        return replace(self, apply_default_ignores=False)

    def hash(self) -> str:
        return content_id(
            dumps(
                {
                    "enabled_packs": list(self.enabled_packs),
                    "apply_default_ignores": self.apply_default_ignores,
                    "extra_ignore_globs": list(self.extra_ignore_globs),
                    "extra": dict(self.extra),
                }
            )
        )


DEFAULT_CONFIG = ConfigView()
