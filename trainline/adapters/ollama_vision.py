"""Ollama vision OCR for UK rail tickets (AD-14 style injectable engine).

Default model: ``trainline-ticket`` (Modelfile over ``qwen2.5vl:7b``),
tuned for RTX 3070 Ti 8 GB (Q4 + num_ctx 4096 + image downscale).
"""
from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "trainline-ticket"
FALLBACK_MODEL = "qwen2.5vl:7b"
# Longest edge — enough for ticket text, keeps VRAM/token cost down on 8 GB cards
_MAX_IMAGE_EDGE = 1600

_EXTRACT_PROMPT = (
    "Extract UK rail ticket fields from this photo. "
    "Decide document_type first (sales_voucher / receipt / journey_ticket). "
    "If it is a 7-day Travelcard, set ticket_kind=travelcard_7day with start_date AND "
    "valid_until; leave date_of_travel null. "
    "If two tickets are in frame, multiple_tickets=true. "
    "Return ONLY the JSON object."
)

_WEEKLY_RETRY_PROMPT = (
    "This photo is a 7-day / weekly Travelcard (TRVLCD / Zones). "
    "Read the Start date and Valid until lines carefully (APTIS months allowed). "
    "Return JSON with document_type=journey_ticket, ticket_kind=travelcard_7day, "
    "start_date and valid_until as YYYY-MM-DD, date_of_travel null, "
    "start_print and until_print as printed. origin and destination required."
)


_APTIS_MON = {
    "jan": 1, "jnr": 1,
    "feb": 2, "fby": 2,
    "mar": 3, "mch": 3,
    "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "jly": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11,
    "dec": 12, "dmr": 12,
}
_APTIS_DATE_RE = re.compile(
    r"^\s*(?P<d>\d{1,2})[-–=. ]+(?P<mon>[A-Za-z]{3,4})[-–=. ]+(?P<y>\d{2,4})\s*$",
    re.IGNORECASE,
)


def _clean_date_text(val: Any) -> str | None:
    if val is None:
        return None
    text = str(val).strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return None
    # Model sometimes emits middle-dots or pipes in dates / enums
    text = text.replace("·", "-").replace("•", "-").replace("|", " ").strip()
    return text or None


def _parse_loose_date(text: str | None):
    """Best-effort date for ordering / swap checks (no peer-adapter import)."""
    if not text:
        return None
    from datetime import datetime

    cleaned = (_clean_date_text(text) or "").upper().replace("SEPT", "SEP")
    for fmt in ("%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%d %b %y", "%d %b %Y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    m = _APTIS_DATE_RE.match(cleaned)
    if not m:
        return None
    mon = _APTIS_MON.get(m.group("mon").casefold()[:4]) or _APTIS_MON.get(
        m.group("mon").casefold()[:3]
    )
    if mon is None:
        return None
    year = int(m.group("y"))
    if year < 100:
        year += 2000
    try:
        return datetime(year, mon, int(m.group("d")))
    except ValueError:
        return None


def normalise_vision_fields(fields: TicketVisionFields) -> TicketVisionFields:
    """Repair common model slips before building the parser transcript."""
    data = dict(fields.raw)
    kind_raw = _clean_date_text(fields.ticket_kind) or ""
    # Model sometimes returns enum list as one string
    kind = kind_raw.casefold().split()[0] if kind_raw else ""
    if "|" in kind_raw:
        kind = kind_raw.casefold().split("|")[0].strip()
    data["ticket_kind"] = kind or fields.ticket_kind

    start = fields.start_date or _clean_date_text(fields.raw.get("start_print"))
    until = fields.valid_until or _clean_date_text(fields.raw.get("until_print"))
    travel = fields.date_of_travel or _clean_date_text(
        fields.raw.get("date_of_travel_print")
    )

    # Prefer printed forms when ISO missing (more faithful for APTIS)
    if start:
        data["start_date"] = start
    if until:
        data["valid_until"] = until
    if travel and not fields.date_of_travel:
        data["date_of_travel"] = travel

    start_dt = _parse_loose_date(data.get("start_date") if isinstance(data.get("start_date"), str) else start)
    until_dt = _parse_loose_date(data.get("valid_until") if isinstance(data.get("valid_until"), str) else until)
    # Swap inverted weekly range (model often swaps Start / Valid until)
    if start_dt and until_dt and start_dt > until_dt:
        data["start_date"], data["valid_until"] = data.get("valid_until"), data.get("start_date")
        if data.get("start_print") and data.get("until_print"):
            data["start_print"], data["until_print"] = data["until_print"], data["start_print"]

    start = data.get("start_date")
    until = data.get("valid_until")
    # Drop unparseable garbage dates (e.g. OCR noise "2521313521")
    if start and _parse_loose_date(str(start)) is None:
        data["start_date"] = None
        start = None
    if until and _parse_loose_date(str(until)) is None:
        data["valid_until"] = None
        until = None
    kind = (data.get("ticket_kind") or "").casefold()

    if (
        start
        and until
        and str(start) != str(until)
    ):
        data["ticket_kind"] = "travelcard_7day"
        data["date_of_travel"] = None
    elif any(k in kind for k in ("7day", "7_day", "trvlcd", "travelcard_7")):
        data["ticket_kind"] = "travelcard_7day"
        data["date_of_travel"] = None
    elif "day" in kind and "travelcard" in kind:
        data["ticket_kind"] = "anytime_day_travelcard"

    # Prefer printed day-of-travel when ISO and print disagree (NOV vs APR mixups)
    travel_iso = _clean_date_text(data.get("date_of_travel"))
    travel_print = _clean_date_text(data.get("date_of_travel_print"))
    if travel_iso and travel_print:
        iso_dt = _parse_loose_date(travel_iso)
        print_dt = _parse_loose_date(travel_print)
        if iso_dt and print_dt and iso_dt.date() != print_dt.date():
            data["date_of_travel"] = travel_print

    return TicketVisionFields.from_dict(data)


@dataclass(frozen=True)
class _OcrLike:
    """Duck-typed to ``ticket_intake.OcrResult`` (no peer-adapter import)."""

    text: str
    confidence: float


@dataclass(frozen=True)
class TicketVisionFields:
    """Structured fields from the vision model (before parser transcript)."""

    raw: dict[str, Any]
    document_type: str
    origin: str | None
    destination: str | None
    date_of_travel: str | None
    start_date: str | None
    valid_until: str | None
    ticket_kind: str | None
    multiple_tickets: bool
    readable: bool
    quality_issues: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TicketVisionFields:
        def _s(key: str) -> str | None:
            return _clean_date_text(data.get(key))

        issues = data.get("quality_issues") or []
        if not isinstance(issues, list):
            issues = [str(issues)]
        kind = _s("ticket_kind")
        if kind and "|" in kind:
            kind = kind.split("|")[0].strip()
        return cls(
            raw=data,
            document_type=(_s("document_type") or "unknown").casefold(),
            origin=_s("origin"),
            destination=_s("destination"),
            date_of_travel=_s("date_of_travel"),
            start_date=_s("start_date"),
            valid_until=_s("valid_until"),
            ticket_kind=kind,
            multiple_tickets=bool(data.get("multiple_tickets")),
            readable=bool(data.get("readable", True)),
            quality_issues=tuple(str(x) for x in issues),
        )


def vision_fields_to_transcript(fields: TicketVisionFields) -> str:
    """Build parser-friendly OCR text from structured vision output."""
    doc = fields.document_type
    if doc in {"receipt"} or "receipt" in doc:
        return (
            "RECEIPT NOT VALID FOR TRAVEL Issuing office unknown "
            f"Date {fields.date_of_travel or fields.start_date or 'unknown'}"
        )
    if doc in {"sales_voucher", "voucher"} or "voucher" in doc:
        return (
            "DEBIT/CREDIT CARD SALES VOUCHER CARDHOLDER'S COPY "
            f"Issuing Office {fields.origin or 'unknown'}"
        )

    origin = fields.origin or "UNKNOWN"
    dest = fields.destination or "UNKNOWN"
    kind = (fields.ticket_kind or "").casefold()

    if "travelcard_7day" in kind or "7day" in kind or "7_day" in kind:
        start = fields.start_date or fields.date_of_travel or "unknown"
        until = fields.valid_until or start
        return (
            f"Travelcard STD TRVLCD-00M07D Start date {start} "
            f"Valid until {until} {origin.upper()} * & {dest.upper()} ANY PERMITTED"
        )

    if "travelcard" in kind or "day_tc" in kind:
        day = fields.date_of_travel or fields.start_date or fields.valid_until or "unknown"
        return (
            f"Day Travelcard STD ANYTIME DAY TC Start date {day} "
            f"Valid until {day} {origin.upper()} * & {dest.upper()} ANY PERMITTED"
        )

    day = fields.date_of_travel or fields.start_date or "unknown"
    return (
        f"Valid for one journey from {origin} to {dest} "
        f"Date of travel {day} Adult Standard Class"
    )


def parse_vision_json(content: str) -> dict[str, Any]:
    """Extract a JSON object from model output (tolerates markdown fences)."""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty vision model response")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"no JSON object in vision response: {text[:200]!r}")


def encode_ticket_image_b64(path: Path, max_edge: int = _MAX_IMAGE_EDGE) -> str:
    """JPEG base64, downscaled for VRAM/token budget on 8 GB GPUs."""
    from PIL import Image

    path = Path(path)
    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        scale = min(1.0, max_edge / float(max(w, h)))
        if scale < 1.0:
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")


class OllamaVisionOcrEngine:
    """Local Qwen2.5-VL via Ollama HTTP API → OcrResult-shaped value for classify."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        timeout_s: float = 180.0,
        max_image_edge: int = _MAX_IMAGE_EDGE,
        fallback_model: str | None = FALLBACK_MODEL,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.max_image_edge = max_image_edge
        self.fallback_model = fallback_model

    def extract(self, path: Path) -> _OcrLike:
        path = Path(path)
        if path.suffix.casefold() == ".pdf":
            return _OcrLike(text="", confidence=0.0)
        try:
            fields = self.extract_fields(path)
        except Exception:
            return _OcrLike(text="", confidence=0.0)
        if fields.multiple_tickets:
            return _OcrLike(text="MULTIPLE TICKETS IN FRAME", confidence=55.0)
        if not fields.readable:
            return _OcrLike(text="", confidence=15.0)
        transcript = vision_fields_to_transcript(fields)
        conf = 92.0 if fields.date_of_travel or fields.start_date else 70.0
        if fields.quality_issues:
            conf = min(conf, 75.0)
        return _OcrLike(text=transcript, confidence=conf)

    def extract_fields(self, path: Path) -> TicketVisionFields:
        b64 = encode_ticket_image_b64(path, self.max_image_edge)
        try:
            content = self._chat(self.model, b64, prompt=_EXTRACT_PROMPT)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and self.fallback_model and self.fallback_model != self.model:
                content = self._chat(self.fallback_model, b64, prompt=_EXTRACT_PROMPT)
            else:
                raise
        fields = normalise_vision_fields(TicketVisionFields.from_dict(parse_vision_json(content)))
        if self._needs_weekly_retry(fields):
            try:
                retry = self._chat(self.model, b64, prompt=_WEEKLY_RETRY_PROMPT)
                retried = normalise_vision_fields(
                    TicketVisionFields.from_dict(parse_vision_json(retry))
                )
                merged = self._merge_weekly_retry(fields, retried)
                if merged is not None:
                    fields = merged
            except Exception:
                pass
        return fields

    @staticmethod
    def _merge_weekly_retry(
        first: TicketVisionFields,
        retried: TicketVisionFields,
    ) -> TicketVisionFields | None:
        """Keep a weekly retry only when the date span looks like a 7-day card.

        Also merges retry start_date with first-pass date_of_travel when the model
        returns start==until on retry but the first pass held the Valid-until day.
        """
        start = retried.start_date
        until = retried.valid_until
        start_dt = _parse_loose_date(start)
        until_dt = _parse_loose_date(until)
        if start_dt and until_dt and start_dt != until_dt:
            days = (until_dt - start_dt).days
            if 4 <= days <= 10:
                return retried
            # Implausible span (e.g. months) — try merging with first-pass until below

        # Retry found start but bad/duplicate until — borrow until from first pass
        first_until = _parse_loose_date(first.date_of_travel) or _parse_loose_date(
            first.valid_until
        )
        if start_dt and first_until and start_dt < first_until:
            days = (first_until - start_dt).days
            if 4 <= days <= 10:
                data = dict(retried.raw)
                data["ticket_kind"] = "travelcard_7day"
                data["start_date"] = start
                data["valid_until"] = first.date_of_travel or first.valid_until
                data["date_of_travel"] = None
                return TicketVisionFields.from_dict(data)
        return None

    @staticmethod
    def _needs_weekly_retry(fields: TicketVisionFields) -> bool:
        """Retry Zones tickets that lack a usable start/until pair."""
        dest = (fields.destination or "").casefold()
        if "zone" not in dest and "zones" not in dest:
            return False
        if (
            fields.start_date
            and fields.valid_until
            and fields.start_date != fields.valid_until
            and _parse_loose_date(fields.start_date)
            and _parse_loose_date(fields.valid_until)
        ):
            start_dt = _parse_loose_date(fields.start_date)
            until_dt = _parse_loose_date(fields.valid_until)
            if start_dt and until_dt and 4 <= (until_dt - start_dt).days <= 10:
                return False
        return True

    def _chat(self, model: str, image_b64: str, prompt: str = _EXTRACT_PROMPT) -> str:
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
                "num_ctx": 4096,
                "num_predict": 768,
                "top_p": 0.1,
                "top_k": 20,
            },
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body.get("message") or {}
        content = message.get("content") or ""
        if not content:
            raise RuntimeError(f"Ollama returned empty content: {body!r}")
        return content


def ensure_ollama_reachable(host: str = DEFAULT_OLLAMA_HOST, timeout_s: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=timeout_s) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_ollama_models(host: str = DEFAULT_OLLAMA_HOST) -> list[str]:
    with urllib.request.urlopen(f"{host.rstrip('/')}/api/tags", timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m.get("name", "") for m in data.get("models") or []]
