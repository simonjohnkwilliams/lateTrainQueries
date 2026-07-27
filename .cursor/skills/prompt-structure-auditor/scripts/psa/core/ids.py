"""Stable content-addressed IDs (ADR D8)."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Sequence


def _blake(payload: str) -> str:
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()


def content_id(text: str) -> str:
    return _blake(text)


def _canonical(parts: Sequence[object]) -> str:
    return json.dumps(list(parts), sort_keys=False, ensure_ascii=False, separators=(",", ":"))


def segment_id(*, path: str, anchor: tuple[str, ...], order: int, kind: str) -> str:
    path_n = path.replace("\\", "/")
    return "s_" + _blake(_canonical([path_n, list(anchor), order, kind]))


def finding_id(*, rule_id: str, path: str, anchor: tuple[str, ...], excerpt: str) -> str:
    path_n = path.replace("\\", "/")
    excerpt_n = re.sub(r"\s+", " ", excerpt.strip())
    return "f_" + _blake(_canonical([rule_id, path_n, list(anchor), excerpt_n]))
