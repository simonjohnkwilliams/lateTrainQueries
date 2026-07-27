"""Canonical JSON — byte-stable serialization (ADR D7)."""
from __future__ import annotations

import json
from typing import Any


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def loads(text: str) -> Any:
    return json.loads(text)
