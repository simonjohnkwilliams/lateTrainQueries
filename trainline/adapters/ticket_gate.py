"""Ticket gate adapter — scan, parse, claim-to-ticket match (AD-14, FR23–FR25).

Owns filesystem ticket naming and matching only. No Playwright, no SMTP, no
other adapters (AD-2). May import ``engine.models`` only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from trainline.engine.models import Band, Claim, Direction

EXPECTED_FORMAT = "<MM-DD-TICKET_NUMBER>.{jpg|jpeg|png|pdf}"

_TICKET_NAME = re.compile(
    r"^(?P<month>\d{2})-(?P<day>\d{2})-(?P<ticket>[A-Za-z0-9_-]+)"
    r"\.(?P<ext>jpg|jpeg|png|pdf)$",
    re.IGNORECASE,
)


def ticket_meta_path(ticket_path: Path) -> Path:
    """Sidecar JSON next to a ready/claimed ticket photo."""
    path = Path(ticket_path)
    return path.with_name(f"{path.stem}.meta.json")


def load_ticket_meta(ticket_path: Path) -> dict[str, str]:
    """Load OCR-extracted ticket_price / ticket_reference from sidecar."""
    path = ticket_meta_path(Path(ticket_path))
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    price = data.get("ticket_price")
    ref = data.get("ticket_reference")
    if price:
        out["ticket_price"] = str(price).strip()
    if ref:
        out["ticket_reference"] = str(ref).strip()
    return out


def write_ticket_meta(
    ticket_path: Path,
    *,
    ticket_price: str | None = None,
    ticket_reference: str | None = None,
) -> Path | None:
    """Write sidecar JSON for OCR fare/ref; skip if both empty."""
    meta: dict[str, str] = {}
    if ticket_price:
        meta["ticket_price"] = str(ticket_price).strip()
    if ticket_reference:
        meta["ticket_reference"] = str(ticket_reference).strip()
    if not meta:
        return None
    path = ticket_meta_path(Path(ticket_path))
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path



@dataclass(frozen=True)
class TicketFile:
    path: Path
    month: str
    day: str
    ticket_number: str
    mm_dd: str


@dataclass(frozen=True)
class ScanResult:
    valid: tuple[TicketFile, ...] = ()
    invalid: tuple[tuple[Path, str], ...] = ()  # (path, reason)
    missing_directory: bool = False


@dataclass(frozen=True)
class MatchResult:
    ok: bool
    missing_dates: tuple[str, ...] = ()
    mapping: dict[str, Path] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    invalid_files: tuple[tuple[Path, str], ...] = ()


def parse_ticket_filename(name: str) -> TicketFile | None:
    """Parse a basename; return ``None`` if it violates the naming contract."""
    match = _TICKET_NAME.match(name)
    if not match:
        return None
    month = match.group("month")
    day = match.group("day")
    return TicketFile(
        path=Path(name),
        month=month,
        day=day,
        ticket_number=match.group("ticket"),
        mm_dd=f"{month}-{day}",
    )


def scan_ticket_dir(path) -> ScanResult:
    """Scan ``path`` for ticket files (non-recursive).

    Valid names match ``EXPECTED_FORMAT``. Misnamed files are listed with a
    reason that includes the expected format. Missing directory → empty scan
    with ``missing_directory=True``.
    """
    root = Path(path)
    if not root.is_dir():
        return ScanResult(missing_directory=True)

    valid: list[TicketFile] = []
    invalid: list[tuple[Path, str]] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_file():
            continue
        parsed = parse_ticket_filename(entry.name)
        if parsed is None:
            invalid.append((
                entry,
                f"misnamed ticket file {entry.name!r}; expected {EXPECTED_FORMAT}",
            ))
            continue
        valid.append(TicketFile(
            path=entry,
            month=parsed.month,
            day=parsed.day,
            ticket_number=parsed.ticket_number,
            mm_dd=parsed.mm_dd,
        ))
    return ScanResult(valid=tuple(valid), invalid=tuple(invalid))


def claim_date_to_mm_dd(iso_date: str) -> str:
    """Convert ``YYYY-MM-DD`` → ``MM-DD`` for ticket filename matching."""
    _year, month, day = iso_date.split("-", 2)
    return f"{month}-{day}"


def match_tickets_to_claims(claims, scan: ScanResult) -> MatchResult:
    """Ensure every distinct claim date has ≥1 valid ticket (FR25).

    Multiple tickets for the same ``MM-DD``: any one satisfies the date.
    Returns a mapping of ISO claim date → chosen ``Path``.
    """
    claim_list = list(claims)
    if not claim_list:
        return MatchResult(ok=True, missing_dates=(), mapping={}, errors=())

    by_mm_dd: dict[str, list[TicketFile]] = {}
    for ticket in scan.valid:
        by_mm_dd.setdefault(ticket.mm_dd, []).append(ticket)

    claim_dates = sorted({c.date for c in claim_list})
    mapping: dict[str, Path] = {}
    missing: list[str] = []
    for iso in claim_dates:
        mm_dd = claim_date_to_mm_dd(iso)
        tickets = by_mm_dd.get(mm_dd) or []
        if not tickets:
            missing.append(iso)
        else:
            mapping[iso] = tickets[0].path

    errors: list[str] = []
    if scan.missing_directory:
        errors.append("ticket directory not found")
    for _path, reason in scan.invalid:
        errors.append(reason)
    if missing:
        errors.append(
            "missing ticket(s) for claim date(s): " + ", ".join(missing)
        )

    ok = not missing and not scan.invalid and not scan.missing_directory
    return MatchResult(
        ok=ok,
        missing_dates=tuple(missing),
        mapping=mapping,
        errors=tuple(errors),
        invalid_files=scan.invalid,
    )


def gate_blocks_filing(result: MatchResult) -> bool:
    """True when Epic 6 ``--file`` must skip browser submission (AD-17)."""
    return not result.ok


def format_match_errors(result: MatchResult) -> str:
    """Human-readable multi-line error report for CLI stderr."""
    if result.ok:
        return "All claim dates have matching ticket files."
    lines = ["Ticket gate failed:"]
    for err in result.errors:
        lines.append(f"  - {err}")
    return "\n".join(lines)


def load_claim_dates_from_json(json_path) -> list[Claim]:
    """Minimal claim stubs from ``claims.json`` rows (date required for gating)."""
    path = Path(json_path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    claims = []
    for row in rows:
        direction = (
            Direction.INBOUND
            if str(row.get("direction", "")).lower() == "inbound"
            else Direction.OUTBOUND
        )
        claims.append(Claim(
            date=row["date"],
            direction=direction,
            origin=row.get("origin", ""),
            destination=row.get("destination", ""),
            scheduled_departure=0,
            scheduled_arrival=0,
            actual_arrival=0,
            delay=int(row.get("delay_min") or 0),
            band=Band.B15_29,
            reason=row.get("reason") or None,
        ))
    return claims


def resolve_ticket_scan_dir(
    ticket_dir: str | Path | None = None,
    tickets_root: str | Path | None = None,
) -> Path:
    """Prefer OCR ready_to_claim, then explicit ticket_dir, then legacy ``ticket/``."""
    if ticket_dir is not None:
        return Path(ticket_dir)
    root = Path(tickets_root or "tickets")
    ready = root / "processed" / "ready_to_claim"
    if ready.is_dir():
        return ready
    legacy = Path("ticket")
    if legacy.is_dir():
        return legacy
    return ready


def claimed_mm_dds(claimed_dir: str | Path) -> set[str]:
    """``MM-DD`` values already present under ``claimed/`` (Epic 6 dedup)."""
    root = Path(claimed_dir)
    if not root.is_dir():
        return set()
    found: set[str] = set()
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        parsed = parse_ticket_filename(entry.name)
        if parsed is not None:
            found.add(parsed.mm_dd)
    return found


def filter_claims_not_already_claimed(claims, claimed_dir: str | Path):
    """Drop claims whose ``MM-DD`` already appears in ``claimed/`` (Epic 6)."""
    done = claimed_mm_dds(claimed_dir)
    return [c for c in claims if claim_date_to_mm_dd(c.date) not in done]


def filter_claims_to_ticketed_dates(claims, scan: ScanResult):
    """Keep claims whose dates have ≥1 ticket; drop the rest (partial file).

    Strict FR25 still applies via ``match_tickets_to_claims`` on the full set.
    Call this first when ``--allow-partial-tickets`` is set so weekly ops can
    file matched days without inventing tickets for every delay day.
    """
    by_mm_dd = {t.mm_dd for t in scan.valid}
    kept = []
    dropped: list[str] = []
    for claim in claims:
        if claim_date_to_mm_dd(claim.date) in by_mm_dd:
            kept.append(claim)
        else:
            dropped.append(claim.date)
    return kept, tuple(sorted(set(dropped)))


def move_to_claimed(ticket_path: Path, claimed_dir: str | Path) -> Path:
    """Move a ready ticket into ``claimed/`` after successful Epic 6 submit."""
    import shutil

    dest_dir = Path(claimed_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ticket_path.name
    if dest.exists():
        stem, ext = ticket_path.stem, ticket_path.suffix
        dest = dest_dir / f"{stem}-dup{ext}"
    shutil.move(str(ticket_path), str(dest))
    meta = ticket_meta_path(ticket_path)
    if meta.is_file():
        meta_dest = dest_dir / meta.name
        if meta_dest.exists():
            meta_dest = dest_dir / f"{meta.stem}-dup.json"
        shutil.move(str(meta), str(meta_dest))
    return dest
