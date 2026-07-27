"""Shared paths for fixture repos and optional live validation repos."""
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VR1 = FIXTURES / "vr1_empty"
VR2 = FIXTURES / "vr2_latetrain"
VR3 = FIXTURES / "vr3_demo"

# Live IdeaProjects validation repos (included in full suite when present).
LIVE_VR1 = Path(r"C:\Users\simon\IdeaProjects\ai-context-benchmark")
LIVE_VR2 = Path(r"C:\Users\simon\IdeaProjects\lateTrainQueries")
LIVE_VR3 = Path(r"C:\Users\simon\IdeaProjects\financeTracker_SW")

# (label, path, is_live)
FIXTURE_TARGETS: list[tuple[str, Path, bool]] = [
    ("VR1_fixture", VR1, False),
    ("VR2_fixture", VR2, False),
    ("VR3_fixture", VR3, False),
]

LIVE_TARGETS: list[tuple[str, Path, bool]] = [
    ("VR1_live", LIVE_VR1, True),
    ("VR2_live", LIVE_VR2, True),
    ("VR3_live", LIVE_VR3, True),
]

ALL_TARGETS: list[tuple[str, Path, bool]] = FIXTURE_TARGETS + LIVE_TARGETS


def present_targets(
    targets: list[tuple[str, Path, bool]] | None = None,
) -> list[tuple[str, Path, bool]]:
    """Targets whose paths exist (fixtures always; live when checked out)."""
    src = targets if targets is not None else ALL_TARGETS
    return [(n, p, live) for n, p, live in src if p.is_dir()]


def present_live_targets() -> list[tuple[str, Path, bool]]:
    return present_targets(LIVE_TARGETS)
