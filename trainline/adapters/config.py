"""Config adapter — route/window/dates + credential loading (FR16, FR17).

``RunConfig`` is the immutable, explicitly-passed run configuration (no global
state, AD-3). Defaults are GOD <-> WAT with **full-day** windows both directions
(capture every service; the engine slims down afterward) and a ``batch_size`` so
a run fetches the lookback in chunks without over-pulling the HSP API.

Credentials are read only from the file at ``HSP_CREDENTIALS_FILE`` (FR17) and
never live in the repo. Config carries no secrets, so it is safe to log.

The credentials file may contain several Open Rail Data products (DTD, KB,
Darwin, HSP). Each product has its own auth model — see ``CREDENTIAL_MAP`` and
``load_hsp_credentials``. May import ``engine.models`` only (AD-2).
"""
from __future__ import annotations

import dataclasses
import os
import re
from dataclasses import dataclass

FULL_DAY = ("0000", "2359")

# Which file section supplies auth for which product (Open Rail Data wiki).
# HSP: portal email/password via HTTP Basic Auth (wiki.openraildata.com/HSP).
# DTD/KB staticfeeds: same portal login, then X-Auth-Token from /authenticate.
# Darwin Push Port / KB realtime: product-specific Username/Password in-section.
CREDENTIAL_MAP = {
    "nrdp_portal": "[configuration] username/password — National Rail Data Portal",
    "dtd": "NRDP portal (+ X-Auth-Token); DTD section is feed URLs only",
    "kb_api": "NRDP portal (+ X-Auth-Token); KB API section is feed URLs only",
    "kb_realtime": "## Knowledgebase (KB) Real Time Incidents ## Username/Password",
    "darwin_s3": "## Darwin File Information ## Access Key / Secret Key",
    "darwin_ftp": "## Darwin FTP Information ## Username/Password",
    "darwin_sftp": "## Darwin SFTP Information ## Username/Password",
    "darwin_topic": "## Darwin Topic Information ## Username/Password",
    "hsp": (
        "## Historical Service Performance (HSP) ## Username/Password if present, "
        "else [configuration] portal username/password (HTTP Basic Auth)"
    ),
}

_SECTION_HEADER = re.compile(r"^##\s*(.+?)\s*##\s*$")
_DEFAULT_METRICS_URL = "https://hsp-prod.rockshore.net/api/v1/serviceMetrics"
_DEFAULT_DETAILS_URL = "https://hsp-prod.rockshore.net/api/v1/serviceDetails"


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
    # AD-6 gate. OQ1 is now resolved (real cancelled-train fixtures exist under
    # tests/fixtures/recorded_details_cancelled_*.json), so production runs
    # include next-catchable cancellation claims by default. The pure optimiser
    # keeps its own default OFF (see engine.optimiser) so a bare optimise(days)
    # call is unchanged; only a real RunConfig turns it on.
    enable_cancellation_fallback: bool = True


@dataclass(frozen=True)
class HspCredentials:
    """Auth + endpoint URLs for the HSP API only (never Darwin/KB secrets)."""

    username: str
    password: str
    service_metrics_url: str = _DEFAULT_METRICS_URL
    service_details_url: str = _DEFAULT_DETAILS_URL
    source: str = "configuration"  # which section supplied username/password


def default_config() -> RunConfig:
    """The GOD <-> WAT full-day default run configuration (FR16)."""
    return RunConfig()


def make_config(**overrides) -> RunConfig:
    """A ``RunConfig`` with ``overrides`` applied over the defaults (FR16)."""
    valid = {f.name for f in dataclasses.fields(RunConfig)}
    unknown = set(overrides) - valid
    if unknown:
        raise TypeError(f"unknown config field(s): {sorted(unknown)}")
    return dataclasses.replace(RunConfig(), **overrides)


class CredentialsError(Exception):
    """Raised when HSP credentials cannot be loaded (missing/malformed file)."""


def _credentials_path(path: str | None) -> str:
    path = path or os.environ.get("HSP_CREDENTIALS_FILE")
    if not path:
        raise CredentialsError(
            "HSP_CREDENTIALS_FILE is not set — point it at your HSP credentials file")
    if not os.path.isfile(path):
        raise CredentialsError(f"HSP credentials file not found: {path}")
    return path


def parse_credentials_file(path: str | None = None) -> dict[str, dict[str, str]]:
    """Parse the multi-section credentials file into ``{section: {key: value}}``.

    Recognises ``[ini_sections]`` and ``## Markdown-style headers ##``. Keys are
    lowercased; values keep their original spelling. Lines without ``=`` are
    ignored (so free-form notes do not break parsing).
    """
    path = _credentials_path(path)
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith(";") or line.startswith("#") and not line.startswith("##"):
                    continue
                header = _SECTION_HEADER.match(line)
                if header:
                    current = header.group(1).strip()
                    sections.setdefault(current, {})
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current = line[1:-1].strip()
                    sections.setdefault(current, {})
                    continue
                if current is None or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                sections[current][key.strip().lower()] = value.strip()
    except OSError as exc:
        raise CredentialsError(f"cannot read HSP credentials file: {path}") from exc
    return sections


def _find_section(sections: dict[str, dict[str, str]], *needles: str) -> tuple[str, dict[str, str]] | None:
    """Return ``(section_name, values)`` whose title contains all needles (casefold)."""
    wanted = [n.casefold() for n in needles]
    for name, values in sections.items():
        hay = name.casefold()
        if all(n in hay for n in wanted):
            return name, values
    return None


def _user_pass(values: dict[str, str]) -> tuple[str, str] | None:
    user = values.get("username")
    password = values.get("password")
    if user and password:
        return user, password
    return None


def load_hsp_credentials(path: str | None = None) -> HspCredentials:
    """Load HSP-only credentials and endpoint URLs (FR17).

    Preference order for username/password:
      1. The ``## Historical Service Performance (HSP) ... ##`` section, if it
         defines Username/Password.
      2. The ``[configuration]`` National Rail Data Portal username/password.

    Never uses Darwin FTP/SFTP/Topic or KB realtime usernames for HSP — those
    products have separate credentials per the Open Rail Data wiki.
    """
    sections = parse_credentials_file(path)
    hsp = _find_section(sections, "historical service performance") or _find_section(
        sections, "hsp")
    metrics_url = _DEFAULT_METRICS_URL
    details_url = _DEFAULT_DETAILS_URL
    source = "configuration"
    pair: tuple[str, str] | None = None

    if hsp is not None:
        name, values = hsp
        metrics_url = values.get("service metrics url", metrics_url)
        details_url = values.get("service details url", details_url)
        pair = _user_pass(values)
        if pair:
            source = name

    if pair is None:
        config_values = sections.get("configuration") or {}
        pair = _user_pass(config_values)
        source = "configuration"

    if pair is None:
        raise CredentialsError(
            "HSP credentials not found: set username=/password= under "
            "[configuration] (National Rail Data Portal login) or under the "
            "## Historical Service Performance (HSP) ## section. "
            "Do not use Darwin/KB usernames for HSP."
        )
    username, password = pair
    return HspCredentials(
        username=username,
        password=password,
        service_metrics_url=metrics_url,
        service_details_url=details_url,
        source=source,
    )


def load_credentials(path: str | None = None) -> tuple[str, str]:
    """Load ``(username, password)`` for HSP HTTP Basic Auth (FR17).

    Compatibility wrapper around ``load_hsp_credentials``.
    """
    creds = load_hsp_credentials(path)
    return creds.username, creds.password
