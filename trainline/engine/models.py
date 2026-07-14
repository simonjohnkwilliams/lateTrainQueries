"""Domain data shapes — the single source of truth (AD-3).

``Service``, ``Claim``, ``DayResult`` (plus the ``Band``, ``FetchStatus`` and
``Direction`` enums) are defined here and **only** here. Raw HSP JSON is mapped
to ``Service`` inside ``adapters.hsp_client`` (Epic 2); ``Claim`` is serialised
to CSV/JSON inside ``adapters.storage`` (Story 3.2). The engine never sees an
HSP dict.

Conventions (architecture spine):
- Times are integer minutes relative to the service's **origin day** (AD-4); a
  calling point past midnight carries +1440. Actual-time fields are ``int | None``
  where ``None`` means *no actual recorded* (unarrived/cancelled), never ``0`` (AD-3).
- Dataclasses are frozen for purity/determinism (AD-1, AD-10).
- This module imports nothing I/O (AD-1) — enforced by the import-boundary test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Direction(Enum):
    """Which leg of the day a service belongs to."""

    OUTBOUND = "outbound"  # origin -> destination (default GOD -> WAT)
    INBOUND = "inbound"  # destination -> origin (default WAT -> GOD)


class Band(IntEnum):
    """SWR Delay Repay band from destination arrival delay.

    ``IntEnum`` so "higher band wins" is a direct comparison; the numeric
    ``payout`` per band lives in ``engine.delay`` (AD-11), not here — the enum
    carries no percentage so the return/single/season tracks stay a function
    concern (FR18).
    """

    NONE = 0  # sub-15-min: not claimable
    B15_29 = 1  # 15-29 min
    B30_59 = 2  # 30-59 min
    B60_119 = 3  # 60-119 min
    B120_PLUS = 4  # 120+ min


class FetchStatus(Enum):
    """Per-day fetch outcome (AD-5). A day is trustworthy only when ``OK``."""

    OK = "ok"  # every required leg fetched; claim/no-claim is trustworthy
    FETCH_FAILED = "fetch_failed"  # a required fetch failed → "not analysed"


@dataclass(frozen=True)
class Service:
    """One train on one leg of one day, in domain terms (no HSP field names).

    ``actual_departure``/``actual_arrival`` are ``None`` when no actual was
    recorded (AD-3) — distinct from an on-time ``0``. ``cancelled`` carries the
    raw HSP signal only (empty actuals + ``late_canc_reason``); the engine owns
    any cancellation-derived delay (AD-6).
    """

    rid: str
    direction: Direction
    origin: str  # CRS code of this leg's origin
    destination: str  # CRS code of this leg's destination
    date: str  # ISO YYYY-MM-DD (HSP date_of_service / origin day)
    scheduled_departure: int  # origin-day-relative minutes (AD-4)
    scheduled_arrival: int  # origin-day-relative minutes (AD-4)
    actual_departure: int | None = None
    actual_arrival: int | None = None
    cancelled: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class Claim:
    """A single claimable leg, carrying the SWR-form fields (FR13).

    Serialised to CSV/JSON only by ``adapters.storage`` (AD-3). MVP surfaces the
    ``band``/percentage, not a £ figure (AD-11).
    """

    date: str
    direction: Direction
    origin: str
    destination: str
    scheduled_departure: int  # origin-day-relative minutes
    scheduled_arrival: int
    actual_arrival: int
    delay: int  # minutes late at destination (>= 15 for a real claim)
    band: Band
    reason: str | None = None


@dataclass(frozen=True)
class DayResult:
    """The engine's per-day output — the only legal engine return unit (AD-1).

    Expresses a no-claim day (``OK`` + empty ``claims``), a claimable day
    (``OK`` + 1-2 claims), and a failed day (``FETCH_FAILED``) distinctly — a
    bare ``list[Claim]`` cannot (AD-5). ``status`` is set by ``hsp_client`` and
    passed through the engine unchanged.
    """

    date: str
    status: FetchStatus
    claims: tuple[Claim, ...] = field(default_factory=tuple)
