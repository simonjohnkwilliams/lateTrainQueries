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
    # Story 4.3 / FR22 — weekly digest after assess (CLI --digest overrides).
    send_digest: bool = False
    # Story 5.x / FR23 — ticket artifact directory (CLI --ticket-dir overrides).
    # Prefer tickets/processed/ready_to_claim when using OCR intake (Epic 5b).
    ticket_dir: str = "tickets/processed/ready_to_claim"
    # Epic 5b — root of unclassified / processed / claimed tree.
    tickets_root: str = "tickets"


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


# --- Email / digest SMTP (AD-13, FR22, NFR9) ---------------------------------

_EMAIL_REQUIRED = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "DIGEST_TO",
)


@dataclass(frozen=True)
class EmailConfig:
    """SMTP settings for the weekly digest (never logged with password)."""

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    digest_to: str
    digest_from: str | None = None  # None => sender uses smtp_user at send time


class EmailConfigError(Exception):
    """Raised when digest SMTP settings cannot be loaded (missing/invalid env)."""


def load_email_config(
    environ: dict[str, str] | None = None,
    credentials_path: str | None = None,
) -> EmailConfig:
    """Load SMTP digest settings from env and/or the credentials file (NFR9).

    Preference: environment variables override file values. File keys may live
    in any section (e.g. a dedicated ``## Email Digest ##`` block, or alongside
    other products in ``creds/trainConfig.txt``). Required names:
    ``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``, ``SMTP_PASSWORD``, ``DIGEST_TO``.
    Optional: ``DIGEST_FROM``.
    """
    env = dict(os.environ if environ is None else environ)
    file_vals = _email_vals_from_credentials_file(credentials_path)
    merged: dict[str, str] = {}
    for key in _EMAIL_REQUIRED + ("DIGEST_FROM",):
        if key == "SMTP_PASSWORD":
            from_env = env.get(key) or ""
        else:
            from_env = (env.get(key) or "").strip()
        if from_env:
            merged[key] = from_env
        elif key in file_vals and file_vals[key]:
            merged[key] = file_vals[key]

    missing = [key for key in _EMAIL_REQUIRED if not (merged.get(key) or "").strip()]
    if missing:
        raise EmailConfigError(
            "email config incomplete — missing or blank: " + ", ".join(missing)
            + " (set env vars or SMTP_* keys in the credentials file)"
        )
    port_raw = merged["SMTP_PORT"].strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise EmailConfigError(
            f"SMTP_PORT must be an integer, got {port_raw!r}"
        ) from exc
    if not 1 <= port <= 65535:
        raise EmailConfigError(
            f"SMTP_PORT must be in 1..65535, got {port}"
        )
    digest_from = (merged.get("DIGEST_FROM") or "").strip() or None
    # Gmail app passwords are often shown with spaces; SMTP accepts either form.
    password = merged["SMTP_PASSWORD"].replace(" ", "")
    return EmailConfig(
        smtp_host=merged["SMTP_HOST"].strip(),
        smtp_port=port,
        smtp_user=merged["SMTP_USER"].strip(),
        smtp_password=password,
        digest_to=merged["DIGEST_TO"].strip(),
        digest_from=digest_from,
    )


def _email_vals_from_credentials_file(path: str | None) -> dict[str, str]:
    """Collect SMTP_* / DIGEST_* keys from any section of the credentials file.

    Uses ``path`` if given, else ``HSP_CREDENTIALS_FILE``. Does **not** silently
    scan ``cwd/creds/`` — the composition root passes the same path it uses for HSP.
    """
    path = path or os.environ.get("HSP_CREDENTIALS_FILE")
    if not path or not os.path.isfile(path):
        return {}
    try:
        sections = parse_credentials_file(path)
    except CredentialsError:
        return {}
    # Prefer an email/digest-named section; otherwise first section that has smtp_host.
    preferred = None
    fallback = None
    for name, values in sections.items():
        hay = name.casefold()
        got = {
            "SMTP_HOST": values.get("smtp_host", ""),
            "SMTP_PORT": values.get("smtp_port", ""),
            "SMTP_USER": values.get("smtp_user", ""),
            "SMTP_PASSWORD": values.get("smtp_password", ""),
            "DIGEST_TO": values.get("digest_to", ""),
            "DIGEST_FROM": values.get("digest_from", ""),
        }
        if not (got["SMTP_HOST"] or "").strip():
            continue
        if "email" in hay or "digest" in hay or "smtp" in hay:
            preferred = got
            break
        if fallback is None:
            fallback = got
    return preferred or fallback or {}


@dataclass(frozen=True)
class GmailFileConfig:
    """Gmail API OAuth settings (Epic 7 / FR40) — duck-typed into ``GmailConfig``."""

    client_id: str
    client_secret: str
    token_path: Path
    digest_to: str


class GmailConfigError(Exception):
    """Raised when Gmail API settings cannot be loaded."""


def load_gmail_config(
    environ: dict[str, str] | None = None,
    credentials_path: str | None = None,
) -> GmailFileConfig:
    """Load Gmail API client id/secret + token path from env and/or credentials file.

    Required (env or ``## Gmail API ##`` section): ``GOOGLE_CLIENT_ID``,
    ``GOOGLE_CLIENT_SECRET``, ``GMAIL_TOKEN_PATH``, ``DIGEST_TO`` (may reuse
    Email Digest ``DIGEST_TO``).
    """
    from pathlib import Path

    env = dict(os.environ if environ is None else environ)
    file_vals = _gmail_vals_from_credentials_file(credentials_path)
    # Allow DIGEST_TO from Email Digest section as fallback
    if not file_vals.get("DIGEST_TO"):
        email_vals = _email_vals_from_credentials_file(credentials_path)
        if email_vals.get("DIGEST_TO"):
            file_vals["DIGEST_TO"] = email_vals["DIGEST_TO"]

    keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GMAIL_TOKEN_PATH", "DIGEST_TO")
    merged: dict[str, str] = {}
    for key in keys:
        from_env = (env.get(key) or "").strip()
        if from_env:
            merged[key] = from_env
        elif file_vals.get(key):
            merged[key] = file_vals[key]

    missing = [k for k in keys if not (merged.get(k) or "").strip()]
    if missing:
        raise GmailConfigError(
            "Gmail config incomplete — missing: " + ", ".join(missing)
            + " (set env or ## Gmail API ## keys in the credentials file)"
        )
    token_path = Path(merged["GMAIL_TOKEN_PATH"]).expanduser()
    if not token_path.is_absolute():
        # Resolve relative to credentials file directory when possible
        cred_path = credentials_path or env.get("HSP_CREDENTIALS_FILE")
        if cred_path:
            token_path = (Path(cred_path).resolve().parent / token_path).resolve()
        else:
            token_path = token_path.resolve()
    return GmailFileConfig(
        client_id=merged["GOOGLE_CLIENT_ID"],
        client_secret=merged["GOOGLE_CLIENT_SECRET"],
        token_path=token_path,
        digest_to=merged["DIGEST_TO"],
    )


def _gmail_vals_from_credentials_file(path: str | None) -> dict[str, str]:
    path = path or os.environ.get("HSP_CREDENTIALS_FILE")
    if not path or not os.path.isfile(path):
        return {}
    try:
        sections = parse_credentials_file(path)
    except CredentialsError:
        return {}
    out: dict[str, str] = {}
    for name, values in sections.items():
        hay = name.casefold()
        if "gmail" not in hay and "google" not in hay:
            continue
        out = {
            "GOOGLE_CLIENT_ID": values.get("google_client_id", "")
            or values.get("client_id", ""),
            "GOOGLE_CLIENT_SECRET": values.get("google_client_secret", "")
            or values.get("client_secret", ""),
            "GMAIL_TOKEN_PATH": values.get("gmail_token_path", "")
            or values.get("token_path", ""),
            "DIGEST_TO": values.get("digest_to", ""),
        }
        break
    return out

