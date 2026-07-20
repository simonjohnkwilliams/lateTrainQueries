"""Friday completion marker for weekly ops idempotency (Epic 7 / FR32, FR39).

Marker files live under a state directory (typically ``Results/weekly/``) and are
keyed by anchor Friday ISO date. Pure local filesystem — no HSP/Gmail I/O.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path


def marker_path(state_dir: Path, anchor_friday: date) -> Path:
    """Return the marker file path for ``anchor_friday`` under ``state_dir``."""
    state_dir = Path(state_dir)
    return state_dir / f"weekly-complete-{anchor_friday.isoformat()}.marker"


def is_complete(state_dir: Path, anchor_friday: date) -> bool:
    """True when the anchor Friday has a completion marker on disk."""
    return marker_path(state_dir, anchor_friday).is_file()


def mark_complete(state_dir: Path, anchor_friday: date) -> Path:
    """Create (or refresh) the completion marker. Idempotent."""
    path = marker_path(state_dir, anchor_friday)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"completed_anchor_friday={anchor_friday.isoformat()}\n",
        encoding="utf-8",
    )
    return path
