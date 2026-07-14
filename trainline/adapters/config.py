"""Config adapter — route/window/dates + credential loading (FR16, FR17).

``RunConfig`` is the immutable, explicitly-passed run configuration (no global
state, AD-3). Defaults are GOD <-> WAT with **full-day** windows both directions
(capture every service; the engine slims down afterward) and a ``batch_size`` so
a run fetches the lookback in chunks without over-pulling the HSP API.

Credentials are read only from the file at ``HSP_CREDENTIALS_FILE`` (FR17) and
never live in the repo. Config carries no secrets, so it is safe to log.

May import ``engine.models`` only within the package (AD-2); it imports no other
adapter.
"""
from __future__ import annotations

import configparser
import dataclasses
import os
from dataclasses import dataclass

FULL_DAY = ("0000", "2359")


@dataclass(frozen=True)
class RunConfig:
    origin: str = "GOD"
    destination: str = "WAT"
    outbound_window: tuple[str, str] = FULL_DAY  # origin -> destination
    inbound_window: tuple[str, str] = FULL_DAY  # destination -> origin
    lookback_days: int = 9  # one week + buffer; bounded by SWR's 28-day filing window
    to_date: str | None = None  # ISO end date; None => resolved at run time
    batch_size: int = 3  # days fetched per run chunk (HSP politeness)
    per_day_cap: float | None = None  # OQ2 stacking cap; None = uncapped
    enable_cancellation_fallback: bool = False  # AD-6 gate; off until OQ1


def default_config() -> RunConfig:
    """The GOD <-> WAT full-day default run configuration (FR16)."""
    return RunConfig()


def make_config(**overrides) -> RunConfig:
    """A ``RunConfig`` with ``overrides`` applied over the defaults (FR16).

    Changing route/window/date needs no code edit — everything flows through
    here. Unknown field names raise, surfacing typos rather than silently
    ignoring them (unlike the old getJson positional-arg gap).
    """
    valid = {f.name for f in dataclasses.fields(RunConfig)}
    unknown = set(overrides) - valid
    if unknown:
        raise TypeError(f"unknown config field(s): {sorted(unknown)}")
    return dataclasses.replace(RunConfig(), **overrides)


class CredentialsError(Exception):
    """Raised when HSP credentials cannot be loaded (missing/malformed file)."""


def load_credentials(path: str | None = None) -> tuple[str, str]:
    """Load ``(username, password)`` from the HSP credentials file (FR17).

    Path comes from the ``path`` argument or ``HSP_CREDENTIALS_FILE``. A missing
    env var, missing file, or malformed contents raise ``CredentialsError`` with
    a clear message. The file itself never lives in the repo.
    """
    path = path or os.environ.get("HSP_CREDENTIALS_FILE")
    if not path:
        raise CredentialsError(
            "HSP_CREDENTIALS_FILE is not set — point it at your HSP credentials file")
    if not os.path.isfile(path):
        raise CredentialsError(f"HSP credentials file not found: {path}")

    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except configparser.Error as exc:
        raise CredentialsError(
            f"{path} is malformed — expected a [configuration] section: {exc}"
        ) from exc
    if not parser.has_section("configuration"):
        raise CredentialsError(f"{path} is missing a [configuration] section")
    try:
        username = parser.get("configuration", "username")
        password = parser.get("configuration", "password")
    except configparser.NoOptionError as exc:
        raise CredentialsError(
            f"{path} must contain username= and password= keys") from exc
    if not username or not password:
        raise CredentialsError(f"{path} has an empty username or password")
    return username, password
