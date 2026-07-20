"""Epic 7 / Story 7.2 — completion marker for Friday idempotency (FR32, FR39)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from trainline.adapters import weekly_marker


@pytest.mark.offline
def test_marker_path_keyed_by_anchor_friday(tmp_path: Path):
    anchor = date(2026, 7, 17)
    path = weekly_marker.marker_path(tmp_path, anchor)
    assert "2026-07-17" in path.name
    assert path.parent == tmp_path or tmp_path in path.parents


@pytest.mark.offline
def test_write_and_is_complete_round_trip(tmp_path: Path):
    anchor = date(2026, 7, 17)
    assert weekly_marker.is_complete(tmp_path, anchor) is False
    weekly_marker.mark_complete(tmp_path, anchor)
    assert weekly_marker.is_complete(tmp_path, anchor) is True


@pytest.mark.offline
def test_second_mark_is_idempotent(tmp_path: Path):
    anchor = date(2026, 7, 17)
    weekly_marker.mark_complete(tmp_path, anchor)
    weekly_marker.mark_complete(tmp_path, anchor)
    assert weekly_marker.is_complete(tmp_path, anchor) is True


@pytest.mark.offline
def test_different_anchor_fridays_are_independent(tmp_path: Path):
    a = date(2026, 7, 17)
    b = date(2026, 7, 24)
    weekly_marker.mark_complete(tmp_path, a)
    assert weekly_marker.is_complete(tmp_path, a) is True
    assert weekly_marker.is_complete(tmp_path, b) is False
