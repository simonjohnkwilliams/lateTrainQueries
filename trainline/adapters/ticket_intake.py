"""Ticket intake — OCR classify unclassified → ready_to_claim / rejected (AD-14 ext).

Injectable ``OcrEngine`` (Ollama vision in production; Fake for offline tests).
AWS Textract can replace the engine later without changing classify logic.

May import ``engine.models`` only (AD-2) — currently none required.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

# --- Paths ------------------------------------------------------------------

DEFAULT_TICKETS_ROOT = "tickets"


@dataclass(frozen=True)
class TicketsLayout:
    """Folder contract under a tickets root."""

    root: Path

    @property
    def unclassified(self) -> Path:
        return self.root / "unclassified"

    @property
    def ready_to_claim(self) -> Path:
        return self.root / "processed" / "ready_to_claim"

    @property
    def rejected(self) -> Path:
        return self.root / "processed" / "rejected"

    @property
    def claimed(self) -> Path:
        return self.root / "claimed"

    @property
    def inbox(self) -> Path:
        """Optional Syncthing/OneDrive drop zone (Epic 8.3) before unclassified."""
        return self.root / "inbox"

    @property
    def inbox_processed(self) -> Path:
        return self.root / "inbox" / "processed"

    def ensure(self) -> None:
        for d in (
            self.unclassified,
            self.ready_to_claim,
            self.rejected,
            self.claimed,
            self.inbox,
            self.inbox_processed,
        ):
            d.mkdir(parents=True, exist_ok=True)


def tickets_layout(root: str | Path | None = None) -> TicketsLayout:
    return TicketsLayout(Path(root or DEFAULT_TICKETS_ROOT))


# --- OCR port ---------------------------------------------------------------

MIN_OCR_CONFIDENCE = 35.0  # below → unreadable


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float  # 0..100 mean word confidence when available


class OcrEngine(Protocol):
    def extract(self, path: Path) -> OcrResult: ...


class FakeOcrEngine:
    """Map basename → ``OcrResult`` for offline tests (no vision model)."""

    def __init__(self, by_name: dict[str, OcrResult] | None = None,
                 default: OcrResult | None = None):
        self._by_name = by_name or {}
        self._default = default or OcrResult(text="", confidence=0.0)

    def extract(self, path: Path) -> OcrResult:
        return self._by_name.get(path.name, self._default)


# --- Pure classification helpers --------------------------------------------

_UNREADABLE_REPORT = "unreadable_report.txt"
# Below this pixel count OCR on phone tickets is often unreliable
_MIN_PIXELS = 400_000

# Valid London-end destinations (OCR-tolerant, including common misreads)
_LONDON_DEST_RE = re.compile(
    r"(?:"
    r"waterloo"
    r"|\blon\s*wat\b"
    r"|\bwat\b"
    r"|london\s+terminals?"
    r"|london\s+zones?\s*1"
    r"|london\s+2\s*ones?\s*1"  # ZONES → 20nes
    r"|zones?\s*1\s*[-–]?\s*6"
    r"|20nes\s*1\s*[-–]?\s*6?"
    r"|zonecs?\s*>?\s*(?:serp|1)?"  # zonecs garbles
    r"|cones?\s*1\s*[-–]?\s*6?"  # ZONES → CONES
    r"|comes?\s*1\s*[-–]?\s*[6€]?"  # ZONES → COMES / 1-€
    r")",
    re.IGNORECASE,
)
# Godalming: OCR often drops/garble the leading "Go"
_GODALMING_RE = re.compile(
    r"(?:"
    r"godalming|godaling|godalm"
    r"|sooalming|soodalming|sdalh?ing"
    r"|[gs]odalming"
    r"|dalming|dalhing"
    r"|\balm\s*ing\b"
    r"|\bgod\b"
    r")",
    re.IGNORECASE,
)

# Journey / valid-for style dates (UK-first).
# APTIS ticket months (anti-fraud): JNR FBY MCH APR MAY JUN JLY AUG SEP OCT NOV DMR
_APTIS_MONTH = (
    r"JNR|FBY|MCH|APR|MAY|JUN|JLY|AUG|SEP|SEPT|OCT|NOV|DMR|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)

_DATE_PATTERNS = [
    re.compile(
        r"\b(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2})[/\-.](?P<y>\d{4})\b"),
    re.compile(
        r"\b(?P<d>\d{1,2})[/\-.](?P<m>\d{1,2})[/\-.](?P<y>\d{2})\b"),
    re.compile(
        rf"\b(?P<d>\d{{1,2}})\s+"
        rf"(?P<mon>{_APTIS_MONTH})[a-z]*\s+"
        rf"(?P<y>\d{{4}})\b",
        re.IGNORECASE,
    ),
    # Space-separated 2-digit year: 29 SEP 19
    re.compile(
        rf"\b(?P<d>\d{{1,2}})\s+"
        rf"(?P<mon>{_APTIS_MONTH})[a-z]*\s+"
        rf"(?P<y>\d{{2}})\b",
        re.IGNORECASE,
    ),
    # Ticket-style 07-JNR-25 / 02-FBY-20 / 26-MCH-24 / 16-may=-19
    re.compile(
        rf"\b(?P<d>[0o@]?\d{{1,2}})[-–=.]+"
        rf"(?P<mon>{_APTIS_MONTH})[a-z]*[-–=.]+"
        rf"(?P<y>\d{{2,4}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})\b"),
]

# Standard English + APTIS anti-fraud month codes used on UK rail tickets
_MON = {
    "jan": 1, "jnr": 1,
    "feb": 2, "fby": 2,
    "mar": 3, "mch": 3,
    "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "jly": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
    "dec": 12, "dmr": 12,
}

# Phone / scanner capture stamps — these are NOT journey dates
# e.g. 20250131_125945, 20170116-085304, 2019_11_21 15_49 Office Lens
_CAMERA_CAPTURE_RE = re.compile(
    r"(20\d{2})[_\-. ](\d{2})[_\-. ](\d{2})(?:[_\-. ]\d{2}){1,3}"
)

_TICKET_ID_RE = re.compile(
    r"\b([A-Z0-9]{5,12})\b",
    re.IGNORECASE,
)

_TICKET_ID_STOPWORDS = frozenset({
    "journey", "ticket", "valid", "until", "travel", "class", "adult",
    "child", "railcard", "london", "waterloo", "godalming", "station",
    "useful", "only", "from", "single", "return", "offpeak", "anytime",
})


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip()


def _ocr_haystacks(text: str) -> tuple[str, str]:
    """Forward + reversed normalised text (handles upside-down OCR)."""
    n = normalize_ocr_text(text)
    return n, n[::-1]


def _compact_ocr(text: str) -> str:
    """Letters/digits only — collapses OCR splits like ``goda | mins``."""
    return re.sub(r"[^a-z0-9]+", "", normalize_ocr_text(text))


def _has_godalming(haystack: str) -> bool:
    if _GODALMING_RE.search(haystack) is not None:
        return True
    c = _compact_ocr(haystack)
    god_tokens = (
        "godalming", "godaling", "godaiming", "godaining", "godalmin",
        "sodalming", "sooalming", "sdalhing", "sdalming",
        "dalming", "dalhing",
        "bodaiming", "bodaming", "bodamina", "bodaming",
        "godamins", "gadamins", "godamins", "godalming",
        "godaining", "godaining",
    )
    if any(t in c for t in god_tokens):
        return True
    # Split OCR: ``ming`` immediately before London destination markers
    for marker in ("london", "waterloo", "zones", "terminals", "cones", "20nes"):
        i = c.find(marker)
        if i > 0 and c[max(0, i - 12):i].endswith("ming"):
            return True
    return False


def _has_london_destination(haystack: str) -> bool:
    if _LONDON_DEST_RE.search(haystack) is not None:
        return True
    c = _compact_ocr(haystack)
    lon_tokens = (
        "waterloo", "londonterminals", "londonterminal", "londonferm",
        "londonzones", "londonzones1", "londonzones16", "zones16",
        "cones16", "comes16", "london20nes", "london20nes16",
        "londonlones", "ondonlones", "londonzon",
    )
    if any(t in c for t in lon_tokens):
        return True
    if "london" in c and any(
        z in c for z in ("zones", "cones", "comes", "20nes", "lones", "terminal", "ferm")
    ):
        return True
    return False


def is_readable(result: OcrResult, min_confidence: float = MIN_OCR_CONFIDENCE) -> bool:
    if not (result.text or "").strip():
        return False
    return result.confidence >= min_confidence


def is_god_wat_route(text: str) -> bool:
    """True if OCR looks like Godalming ↔ valid London end.

    Valid London ends: Waterloo, London Terminals, London Zones 1-6
    (and common OCR misreads). Also checks reversed text for rotated photos.
    """
    if not (text or "").strip():
        return False
    for hay in _ocr_haystacks(text):
        if _has_godalming(hay) and _has_london_destination(hay):
            return True
    return False


# Destinations that prove a different journey (Not_valid_Route), not mere OCR gaps.
_WRONG_ROUTE_MARKERS = (
    "burgesshill", "burgess hill", "guildford", "christchurch",
    "chesterfield", "haslemere", "portsmouth", "brighton", "gatwick",
    "horsham", "crawley", "eastbourne", "worthing", "southampton",
    "marylebone",  # issuing-office only is handled as wrong_document; station as end
)


def is_clearly_wrong_route(text: str) -> bool:
    """True only when OCR positively shows a non-claim route.

    Missing Godalming/London ends alone is *not* a wrong route — that is an
    unreadable / incomplete OCR problem.
    """
    if not (text or "").strip() or is_god_wat_route(text):
        return False
    n = normalize_ocr_text(text)
    c = _compact_ocr(text)
    for marker in _WRONG_ROUTE_MARKERS:
        key = marker.replace(" ", "")
        if key in c or marker in n:
            return True
    return False


# --- Content rules (readable text we may still reject) ----------------------


@dataclass(frozen=True)
class ContentAssessment:
    """Result of content rules after OCR/vision text is available."""

    verdict: str
    # accept | wrong_route | wrong_document | route_unclear
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "accept"


def is_wrong_document(text: str) -> bool:
    """True for receipts / sales vouchers — not a journey ticket for Delay Repay."""
    n = normalize_ocr_text(text)
    if not n:
        return False
    if "multiple tickets in frame" in n:
        return True
    markers = (
        "not valid for travel",
        "debit/credit card sales voucher",
        "debit credit card sales voucher",
        "sales voucher",
        "cardholder's copy",
        "cardholders copy",
        "vat reg",
        "issuing office",
    )
    if "receipt" in n and (
        "not valid for travel" in n
        or "issuing office" in n
        or "vat reg" in n
        or "rail tickets" in n
    ):
        return True
    return any(m in n for m in markers)


def wrong_document_reason(text: str) -> str:
    n = normalize_ocr_text(text)
    if "multiple tickets" in n:
        return "multiple_tickets"
    if "sales voucher" in n or ("debit" in n and "voucher" in n):
        return "wrong_document_voucher"
    if "receipt" in n or "not valid for travel" in n:
        return "wrong_document_receipt"
    return "wrong_document"


def assess_ticket_content(text: str) -> ContentAssessment:
    """Classify OCR text: accept GOD↔London, or reject for content reasons."""
    if not (text or "").strip():
        return ContentAssessment("route_unclear", ["OCR text empty"])

    if is_wrong_document(text):
        code = wrong_document_reason(text)
        return ContentAssessment(
            "wrong_document",
            [code, "document is a receipt/voucher, not a journey ticket"],
        )

    if is_god_wat_route(text):
        return ContentAssessment("accept", [])

    if is_clearly_wrong_route(text):
        return ContentAssessment(
            "wrong_route",
            [
                "wrong_route",
                "readable route is not Godalming<->London "
                "(Waterloo/Terminals/Zones 1-6)",
            ],
        )

    return ContentAssessment(
        "route_unclear",
        [
            "route_unclear",
            "could not identify both journey ends from OCR",
        ],
    )


def diagnose_route_unreadable(path: Path, result: OcrResult,
                              min_confidence: float = MIN_OCR_CONFIDENCE) -> str:
    """Explain rejection when both journey ends could not be identified."""
    parts = [
        "could not identify both journey ends "
        "(Godalming and London Waterloo/Terminals/Zones 1-6) from OCR — "
        "likely partial shot, glare, or phone UI overlay; retake the full ticket",
    ]
    fwd, _ = _ocr_haystacks(result.text)
    saw_god = _has_godalming(fwd)
    saw_lon = _has_london_destination(fwd)
    if saw_god and not saw_lon:
        parts.append("saw Godalming-like text but not a London destination")
    elif saw_lon and not saw_god:
        parts.append("saw a London destination but not Godalming")
    elif not saw_god and not saw_lon:
        parts.append("neither end recognised")
    parts.append(diagnose_unreadable(path, result, min_confidence))
    return "; ".join(parts)


def diagnose_image_quality(path: Path) -> list[str]:
    """Heuristic reasons an image may OCR poorly (no OCR required)."""
    reasons: list[str] = []
    suffix = path.suffix.casefold()
    if suffix == ".pdf":
        reasons.append(
            "PDF is not rasterised for OCR — export/convert to JPG or PNG")
        return reasons
    if suffix not in {".jpg", ".jpeg", ".png"}:
        reasons.append(f"unsupported image type ({suffix or 'unknown'})")
        return reasons
    try:
        from PIL import Image, ImageStat
    except ImportError:
        reasons.append("Pillow not installed — cannot measure image quality")
        return reasons
    try:
        with Image.open(path) as img:
            w, h = img.size
            pixels = w * h
            if pixels < _MIN_PIXELS:
                reasons.append(
                    f"resolution low ({w}×{h} = {pixels:,} px; "
                    f"aim for ≥{_MIN_PIXELS:,})")
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            mean = float(stat.mean[0])
            extrema = gray.getextrema()
            spread = float(extrema[1] - extrema[0]) if extrema else 0.0
            if mean < 55:
                reasons.append(
                    f"image too dark (avg brightness {mean:.0f}/255)")
            elif mean > 225:
                reasons.append(
                    f"image too bright/washed out (avg brightness {mean:.0f}/255)")
            if spread < 40:
                reasons.append(
                    f"low contrast (tone range {spread:.0f}/255)")
            small = gray.resize((max(1, w // 4), max(1, h // 4)))
            if hasattr(small, "get_flattened_data"):
                sample = list(small.get_flattened_data())
            else:
                sample = list(small.getdata())
            if len(sample) > 10:
                try:
                    sd = statistics.pstdev(sample)
                    if sd < 12:
                        reasons.append(
                            f"appears blurry/flat (pixel stddev {sd:.1f})")
                except statistics.StatisticsError:
                    pass
    except OSError as exc:
        reasons.append(f"could not open image ({exc})")
    return reasons


def diagnose_unreadable(
    path: Path,
    result: OcrResult,
    min_confidence: float = MIN_OCR_CONFIDENCE,
) -> str:
    """Human-readable explanation for an unreadable rejection."""
    parts: list[str] = []
    parts.extend(diagnose_image_quality(path))

    text = (result.text or "").strip()
    if not text:
        parts.append("OCR extracted no usable text")
    elif result.confidence < min_confidence:
        parts.append(
            f"OCR confidence too low "
            f"({result.confidence:.0f}% < {min_confidence:.0f}% threshold)")

    fwd, rev = _ocr_haystacks(text)
    fwd_hits = int(_has_godalming(fwd)) + int(_has_london_destination(fwd))
    rev_hits = int(_has_godalming(rev)) + int(_has_london_destination(rev))
    if rev_hits > fwd_hits and rev_hits > 0:
        parts.append(
            "text looks upside-down or rotated — try rotating the photo 180°")

    if not parts:
        parts.append(
            "OCR could not read ticket clearly (unknown cause — "
            "try a sharper, better-lit photo of the full ticket)")
    return "; ".join(parts)


def strip_reject_prefix(name: str) -> str:
    """Recover original basename from Not_valid_*/unreadable- rename."""
    m = re.match(
        r"^(?:Not_valid_Route|Not_valid_Document|unreadable)-\d{8}-\d{6}-(.+)$",
        name,
        re.IGNORECASE,
    )
    return m.group(1) if m else name


def restore_rejected_to_unclassified(
    rejected_dir: Path,
    unclassified: Path,
    *,
    pattern: str = "*",
) -> list[Path]:
    """Move rejected files back to unclassified with original names restored."""
    unclassified.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for src in sorted(rejected_dir.glob(pattern)):
        if not src.is_file():
            continue
        dest = unclassified / strip_reject_prefix(src.name)
        if dest.exists():
            dest = unclassified / f"{dest.stem}-restored{dest.suffix}"
        shutil.move(str(src), str(dest))
        moved.append(dest)
    return moved


def _month_from_token(mon_raw: str) -> int | None:
    raw = (mon_raw or "").casefold()
    if raw.startswith("sept"):
        return 9
    key = raw[:3]
    return _MON.get(key)


def _parse_date_match(m: re.Match[str]) -> datetime | None:
    gd = m.groupdict()
    try:
        if gd.get("mon"):
            month = _month_from_token(gd["mon"])
            if month is None:
                return None
            day_raw = gd["d"]
            day_raw = day_raw.lstrip("@").replace("o", "0").replace("O", "0")
            day = int(day_raw)
            year = int(gd["y"])
            if year < 100:
                year += 2000
        elif len(gd.get("y", "")) == 4 and gd.get("m") and m.group(0).count("-") == 2:
            year, month, day = int(gd["y"]), int(gd["m"]), int(gd["d"])
        else:
            day, month = int(gd["d"]), int(gd["m"])
            year = int(gd["y"])
            if year < 100:
                year += 2000
        return datetime(year, month, day)
    except (ValueError, KeyError, TypeError):
        return None


def parse_journey_date(text: str) -> datetime | None:
    """Best-effort journey/valid-for date from OCR text (UK day-first / APTIS)."""
    if not text:
        return None
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parsed = _parse_date_match(m)
        if parsed is not None:
            return parsed
    return None


@dataclass(frozen=True)
class TicketDates:
    """Dates extracted from ticket OCR (APTIS-aware)."""

    date_of_travel: datetime | None = None
    start_date: datetime | None = None
    valid_until: datetime | None = None

    @property
    def primary(self) -> datetime | None:
        """Day returns → date of travel; Travelcards → start date; else valid-until."""
        return self.date_of_travel or self.start_date or self.valid_until


# Captures ISO (2020-01-27) or ticket print (27-JNR-20 / 29 SEP 19) after a label
_LABELED_DATE_VALUE = (
    rf"(?:"
    rf"(?P<iso_y>\d{{4}})-(?P<iso_m>\d{{2}})-(?P<iso_d>\d{{2}})"
    rf"|"
    rf"(?P<d>[0o@]?\d{{1,2}})[-–=. ]+(?P<mon>{_APTIS_MONTH})[a-z]*[-–=. ]+(?P<y>\d{{2,4}})"
    rf")"
)


def _parse_labeled_date_match(m: re.Match[str]) -> datetime | None:
    gd = m.groupdict()
    if gd.get("iso_y"):
        try:
            return datetime(int(gd["iso_y"]), int(gd["iso_m"]), int(gd["iso_d"]))
        except (ValueError, TypeError):
            return None
    return _parse_date_match(m)


_LABELED_DATE_PATTERNS = [
    (
        "date_of_travel",
        re.compile(
            rf"(?:date\s+of\s+travel|travel\s+date)\s*[:=]?\s*{_LABELED_DATE_VALUE}",
            re.IGNORECASE,
        ),
    ),
    (
        "start_date",
        re.compile(
            rf"start\s+date\s*[:=]?\s*{_LABELED_DATE_VALUE}",
            re.IGNORECASE,
        ),
    ),
    (
        "valid_until",
        re.compile(
            rf"valid\s+until\s*[:=]?\s*{_LABELED_DATE_VALUE}",
            re.IGNORECASE,
        ),
    ),
]


def parse_ticket_dates(text: str) -> TicketDates:
    """Prefer labeled APTIS dates (Date of travel / Start date / Valid until)."""
    if not text:
        return TicketDates()
    found: dict[str, datetime] = {}
    for key, pat in _LABELED_DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parsed = _parse_labeled_date_match(m)
        if parsed is not None:
            found[key] = parsed
    return TicketDates(
        date_of_travel=found.get("date_of_travel"),
        start_date=found.get("start_date"),
        valid_until=found.get("valid_until"),
    )


def parse_journey_date_from_filename(name: str) -> datetime | None:
    """Fallback date from human ticket filenames — never from camera capture stamps."""
    stem = Path(name).stem
    # Galaxy / Office Lens capture timestamps are when the photo was taken
    if _CAMERA_CAPTURE_RE.search(stem):
        return None
    # Bare YYYYMMDD without a time suffix (rare intentional names)
    m = re.search(r"(?<!\d)(20\d{2})[_\-.]?(\d{2})[_\-.]?(\d{2})(?!\d)", stem)
    if m and not re.search(r"\d{3,6}\s*$", stem[m.end():m.end() + 8]):
        # Still skip if the rest of the stem looks like HHMMSS glued on
        rest = stem[m.end():]
        if re.match(r"[_\-.\s]?\d{4,6}\b", rest):
            return None
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # train06112019 / 06112019 (DDMMYYYY) — human naming, not camera
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", stem)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(year, month, day)
        except ValueError:
            pass
    # 16thjuly2019 / 18thjuly2019 — require an explicit year in the name
    m = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|jnr|fby|mch|jly|dmr)[a-z]*"
        r"(\d{2,4})",
        stem,
        re.IGNORECASE,
    )
    if m:
        try:
            day = int(m.group(1))
            month = _month_from_token(m.group(2))
            if month is None:
                return None
            year = int(m.group(3))
            if year < 100:
                year += 2000
            return datetime(year, month, day)
        except (ValueError, KeyError):
            pass
    return None


def resolve_journey_date(text: str, filename: str) -> datetime | None:
    """Labeled OCR dates first; never prefer camera capture filenames."""
    labeled = parse_ticket_dates(text)
    if labeled.primary is not None:
        return labeled.primary
    found = parse_journey_date(text)
    if found is not None:
        return found
    found = parse_journey_date_from_filename(filename)
    if found is not None:
        return found
    stem = Path(filename).stem
    m = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|jnr|fby|mch|jly|dmr)[a-z]*",
        stem,
        re.IGNORECASE,
    )
    day: int | None = None
    month: int | None = None
    if m:
        try:
            day = int(m.group(1))
            month = _month_from_token(m.group(2))
        except (ValueError, KeyError):
            day, month = None, None
    if day is None:
        m = re.search(
            r"(jan|feb|mar|apr|may|jun|july|jul|aug|sep|sept|oct|nov|dec|jnr|fby|mch|jly|dmr)[a-z]*"
            r"(\d{1,2})(?:st|nd|rd|th)?",
            stem,
            re.IGNORECASE,
        )
        if m:
            try:
                month = _month_from_token(m.group(1))
                day = int(m.group(2))
            except (ValueError, KeyError):
                return None
    if day is None or month is None:
        return None
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text or "")]
    if not years:
        years = [
            2000 + int(y)
            for y in re.findall(r"[-–=](\d{2})\b", text or "")
            if 10 <= int(y) <= 35
        ]
    uniq = sorted(set(years))
    if len(uniq) == 1:
        try:
            return datetime(uniq[0], month, day)
        except ValueError:
            return None
    return None


def ticket_id_from_text_or_hash(text: str, path: Path) -> str:
    """Prefer an OCR'd ticket-like token; else short file content hash."""
    for match in _TICKET_ID_RE.finditer(text or ""):
        token = match.group(1)
        if token.casefold() in _TICKET_ID_STOPWORDS:
            continue
        # Skip pure years / times
        if token.isdigit() and len(token) <= 4:
            continue
        if re.fullmatch(r"\d{6,8}", token):  # likely date stamp
            continue
        return re.sub(r"[^A-Za-z0-9_-]", "", token)[:24] or _file_hash(path)
    return _file_hash(path)


_PRICE_RE = re.compile(
    r"(?:Price|Fare|Amount)\s*[:\s]*£?\s*(\d+[.,]\d{2})",
    re.IGNORECASE,
)
_PRICE_RE_BARE = re.compile(r"£\s*(\d+[.,]\d{2})")
_TICKET_REF_RE = re.compile(
    r"(?:Ticket\s*(?:number|no\.?|#)|booking\s*reference|"
    r"collection\s*(?:ref(?:erence)?|number)?)\s*[:\s]*([A-Za-z0-9-]{5,})",
    re.IGNORECASE,
)


def parse_ticket_price(text: str) -> str | None:
    """Extract fare from OCR transcript (e.g. ``Price 12.50`` or ``£12.50``)."""
    for pat in (_PRICE_RE, _PRICE_RE_BARE):
        match = pat.search(text or "")
        if match:
            return match.group(1).replace(",", ".")
    return None


def parse_ticket_reference(text: str) -> str | None:
    """Extract ticket number / booking reference from OCR transcript."""
    match = _TICKET_REF_RE.search(text or "")
    if not match:
        return None
    token = match.group(1).strip()
    digits = re.search(r"(\d{5,})", token)
    if digits:
        return digits.group(1)
    cleaned = re.sub(r"[^A-Za-z0-9-]", "", token)
    return cleaned[:24] or None


def _ticket_meta_path(ticket_path: Path) -> Path:
    path = Path(ticket_path)
    return path.with_name(f"{path.stem}.meta.json")


def _write_ready_ticket_meta(ticket_path: Path, text: str) -> None:
    """Persist OCR fare/ref beside a ready ticket (sidecar ``*.meta.json``)."""
    price = parse_ticket_price(text)
    reference = parse_ticket_reference(text)
    meta: dict[str, str] = {}
    if price:
        meta["ticket_price"] = price
    if reference:
        meta["ticket_reference"] = reference
    if not meta:
        return
    _ticket_meta_path(ticket_path).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8].upper()


def ready_filename(journey: datetime, ticket_id: str, ext: str) -> str:
    ext = ext if ext.startswith(".") else f".{ext}"
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "", ticket_id) or "TICKET"
    return f"{journey.month:02d}-{journey.day:02d}-{safe_id}{ext.casefold()}"


def reject_filename(kind: str, original: Path, when: datetime) -> str:
    """kind is ``unreadable``, ``Not_valid_Route``, or ``Not_valid_Document``."""
    stamp = when.strftime("%Y%m%d-%H%M%S")
    stem = original.stem
    ext = original.suffix.casefold() or ".jpg"
    return f"{kind}-{stamp}-{stem}{ext}"


# --- Classify pipeline ------------------------------------------------------

@dataclass(frozen=True)
class ClassifyItem:
    source: Path
    destination: Path
    outcome: str
    # ready | rejected_unreadable | rejected_route | rejected_document | rejected_no_date
    detail: str = ""


@dataclass
class ClassifySummary:
    items: list[ClassifyItem] = field(default_factory=list)

    @property
    def ready(self) -> int:
        return sum(1 for i in self.items if i.outcome == "ready")

    @property
    def rejected(self) -> int:
        return sum(1 for i in self.items if i.outcome.startswith("rejected"))


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".pdf"}


def classify_unclassified(
    layout: TicketsLayout,
    ocr: OcrEngine,
    *,
    now: datetime | None = None,
    min_confidence: float = MIN_OCR_CONFIDENCE,
    on_progress=None,
) -> ClassifySummary:
    """Process every file in ``unclassified/`` into ready_to_claim or rejected.

    ``on_progress(index, total, path, phase, item_or_none)`` is optional:
    phase is ``\"start\"`` before OCR and ``\"done\"`` after classify (item set).
    """
    layout.ensure()
    when = now or datetime.now()
    summary = ClassifySummary()
    files = sorted(
        p for p in layout.unclassified.iterdir()
        if p.is_file() and p.suffix.casefold() in _IMAGE_EXTS
    )
    total = len(files)
    for index, path in enumerate(files, start=1):
        if on_progress is not None:
            on_progress(index, total, path, "start", None)
        item = _classify_one(path, layout, ocr, when, min_confidence)
        summary.items.append(item)
        if on_progress is not None:
            on_progress(index, total, path, "done", item)
    return summary


def _append_unreadable_report(layout: TicketsLayout, item: ClassifyItem) -> None:
    report = layout.rejected / _UNREADABLE_REPORT
    line = (
        f"{datetime.now().isoformat(timespec='seconds')}\t"
        f"{item.destination.name}\t"
        f"{item.detail}\n"
    )
    with report.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _classify_one(
    path: Path,
    layout: TicketsLayout,
    ocr: OcrEngine,
    when: datetime,
    min_confidence: float,
) -> ClassifyItem:
    result = ocr.extract(path)
    readable = is_readable(result, min_confidence)
    # Soft-accept: clear Godalming↔London keywords despite low OCR confidence
    if not readable and (result.text or "").strip() and is_god_wat_route(result.text):
        readable = True
    if not readable:
        detail = diagnose_unreadable(path, result, min_confidence)
        dest_name = reject_filename("unreadable", path, when)
        dest = layout.rejected / dest_name
        shutil.move(str(path), str(dest))
        item = ClassifyItem(path, dest, "rejected_unreadable", detail)
        _append_unreadable_report(layout, item)
        return item

    # Content rules: readable text we may still reject (wrong doc / wrong route)
    content = assess_ticket_content(result.text)
    if content.verdict == "wrong_document":
        dest_name = reject_filename("Not_valid_Document", path, when)
        dest = layout.rejected / dest_name
        shutil.move(str(path), str(dest))
        return ClassifyItem(
            path,
            dest,
            "rejected_document",
            "; ".join(content.reasons),
        )
    if content.verdict == "wrong_route":
        dest_name = reject_filename("Not_valid_Route", path, when)
        dest = layout.rejected / dest_name
        shutil.move(str(path), str(dest))
        return ClassifyItem(
            path,
            dest,
            "rejected_route",
            "; ".join(content.reasons),
        )
    if content.verdict == "route_unclear":
        detail = diagnose_route_unreadable(path, result, min_confidence)
        dest_name = reject_filename("unreadable", path, when)
        dest = layout.rejected / dest_name
        shutil.move(str(path), str(dest))
        item = ClassifyItem(path, dest, "rejected_unreadable", detail)
        _append_unreadable_report(layout, item)
        return item

    journey = resolve_journey_date(result.text, path.name)
    if journey is None:
        hint = ""
        stem = path.stem
        if re.search(
            r"\d{1,2}(?:st|nd|rd|th)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
            stem,
            re.I,
        ) or re.search(
            r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\d{1,2}",
            stem,
            re.I,
        ):
            hint = (
                " filename has day/month but no year — rename to include year "
                "(e.g. 21stmay2019.jpg) or retake a clearer photo;"
            )
        detail = (
            f"could not parse journey date from OCR text;{hint} "
            + diagnose_unreadable(path, result, min_confidence)
        )
        dest_name = reject_filename("unreadable", path, when)
        dest = layout.rejected / dest_name
        shutil.move(str(path), str(dest))
        item = ClassifyItem(path, dest, "rejected_no_date", detail)
        _append_unreadable_report(layout, item)
        return item

    ticket_id = ticket_id_from_text_or_hash(result.text, path)
    # Prefer a clear 5+ digit ticket number from OCR for the ready filename.
    ocr_ref = parse_ticket_reference(result.text)
    if ocr_ref and ocr_ref.isdigit() and len(ocr_ref) >= 5:
        ticket_id = ocr_ref
    dest_name = ready_filename(journey, ticket_id, path.suffix)
    dest = layout.ready_to_claim / dest_name
    # Avoid clobbering an existing ready file
    if dest.exists():
        dest = layout.ready_to_claim / ready_filename(
            journey, f"{ticket_id}-{_file_hash(path)[:4]}", path.suffix)
    shutil.move(str(path), str(dest))
    _write_ready_ticket_meta(dest, result.text)
    return ClassifyItem(path, dest, "ready", dest_name)
