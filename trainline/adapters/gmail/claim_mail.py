"""Parse SWR Delay Repay claim-status emails (FR37 / FR38).

Characterised from live inbox mail for claim ``SWR-0218-108-579``
(2026-07-17…18): RECEIVED → Approved → PAYMENT SENT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

CLAIM_ID_RE = re.compile(r"\b(SWR-\d{4}-\d{3}-\d{3})\b", re.IGNORECASE)

# Subject: South Western Railway Delay Repay - Claim SWR-… - <STAGE>
SUBJECT_RE = re.compile(
    r"^South Western Railway Delay Repay\s*-\s*Claim\s+"
    r"(?P<claim_id>SWR-\d{4}-\d{3}-\d{3})\s*-\s*(?P<stage>.+?)\s*$",
    re.IGNORECASE,
)

SWR_FROM_HINT = "firstcustomercontact.com"
SWR_FROM_LOCAL = "no-replyswrdr"

_POUND_AMOUNT_RE = re.compile(r"£\s*(\d+(?:\.\d{1,2})?)")


class ClaimMailStage(str, Enum):
    """Lifecycle stages observed in SWR Delay Repay emails."""

    RECEIVED = "received"
    APPROVED = "approved"
    PAYMENT_SENT = "paid"
    UNKNOWN = "unknown"


# Subject stage token → ClaimMailStage (case-insensitive exact match after strip)
_STAGE_ALIASES: dict[str, ClaimMailStage] = {
    "received": ClaimMailStage.RECEIVED,
    "approved": ClaimMailStage.APPROVED,
    "payment sent": ClaimMailStage.PAYMENT_SENT,
    "payment_sent": ClaimMailStage.PAYMENT_SENT,
}


@dataclass(frozen=True)
class SwrClaimMail:
    """Parsed SWR claim-status message fields used for Table 2 / lifecycle."""

    claim_id: str
    stage: ClaimMailStage
    subject: str
    from_addr: str
    amount_gbp: str | None = None
    travel_date_raw: str | None = None
    departing_raw: str | None = None
    delay_raw: str | None = None
    decision_raw: str | None = None
    body: str = ""


def normalize_claim_id(text: str) -> str | None:
    m = CLAIM_ID_RE.search(text or "")
    return m.group(1).upper() if m else None


def parse_subject_stage(subject: str) -> tuple[str | None, ClaimMailStage]:
    """Return ``(claim_id, stage)`` from the SWR subject line."""
    subject = (subject or "").strip()
    m = SUBJECT_RE.match(subject)
    if not m:
        claim = normalize_claim_id(subject)
        return claim, ClaimMailStage.UNKNOWN
    claim_id = m.group("claim_id").upper()
    token = m.group("stage").strip().casefold()
    stage = _STAGE_ALIASES.get(token, ClaimMailStage.UNKNOWN)
    return claim_id, stage


def looks_like_swr_sender(from_addr: str) -> bool:
    addr = (from_addr or "").casefold()
    return SWR_FROM_HINT in addr and SWR_FROM_LOCAL in addr


def _first_match(pattern: str, text: str, flags: int = re.I) -> str | None:
    m = re.search(pattern, text or "", flags)
    return m.group(1).strip() if m else None


def parse_body_fields(body: str) -> dict[str, str | None]:
    """Extract common structured lines from SWR claim email bodies."""
    text = body or ""
    amount = None
    am = _POUND_AMOUNT_RE.search(text)
    if am:
        amount = am.group(1)
    return {
        "amount_gbp": amount,
        "travel_date_raw": _first_match(
            r"Travel Date:\s*(.+?)(?:\n|$)", text
        ),
        "departing_raw": _first_match(
            r"Departing:\s*(.+?)(?:\n|$)", text
        ),
        "delay_raw": _first_match(
            r"^Delay:\s*(.+?)\s*$",
            text,
            flags=re.I | re.M,
        ),
        "decision_raw": _first_match(r"Decision:\s*(.+?)(?:\n|$)", text),
        "claim_id": normalize_claim_id(text),
    }


def parse_swr_claim_mail(
    *,
    subject: str,
    from_addr: str = "",
    body: str = "",
) -> SwrClaimMail | None:
    """Parse a message into ``SwrClaimMail``, or ``None`` if not an SWR claim mail."""
    claim_id, stage = parse_subject_stage(subject)
    if claim_id is None:
        return None
    # Prefer subject stage; body can still fill fields when stage unknown
    fields = parse_body_fields(body)
    if stage is ClaimMailStage.UNKNOWN and fields.get("decision_raw"):
        if fields["decision_raw"].casefold().startswith("approved"):
            stage = ClaimMailStage.APPROVED
    body_claim = fields.get("claim_id")
    if body_claim and body_claim != claim_id:
        # Subject wins for id; body mismatch → still return subject id
        pass
    return SwrClaimMail(
        claim_id=claim_id,
        stage=stage,
        subject=subject.strip(),
        from_addr=from_addr.strip(),
        amount_gbp=fields.get("amount_gbp"),
        travel_date_raw=fields.get("travel_date_raw"),
        departing_raw=fields.get("departing_raw"),
        delay_raw=fields.get("delay_raw"),
        decision_raw=fields.get("decision_raw"),
        body=body,
    )


def gmail_header_map(message: dict[str, Any]) -> dict[str, str]:
    """Flatten Gmail API ``payload.headers`` to a case-insensitive name map."""
    headers = (message.get("payload") or {}).get("headers") or []
    out: dict[str, str] = {}
    for h in headers:
        name = (h.get("name") or "").strip()
        if name:
            out[name.casefold()] = h.get("value") or ""
    return out


def extract_gmail_body_text(message: dict[str, Any]) -> str:
    """Best-effort plain-text body from a Gmail ``format=full`` message."""
    import base64

    payload = message.get("payload") or {}

    def _decode(data: str) -> str:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
            "utf-8", errors="replace"
        )

    def _walk(part: dict[str, Any]) -> str | None:
        mime = (part.get("mimeType") or "").casefold()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime in ("text/plain", "text/html"):
            return _decode(data)
        for child in part.get("parts") or []:
            found = _walk(child)
            if found:
                return found
        return None

    text = _walk(payload)
    if text:
        return text
    snippet = message.get("snippet") or ""
    return snippet


def parse_gmail_message(message: dict[str, Any]) -> SwrClaimMail | None:
    """Parse a Gmail API message dict into ``SwrClaimMail`` when applicable."""
    headers = gmail_header_map(message)
    subject = headers.get("subject", "")
    from_addr = headers.get("from", "")
    body = extract_gmail_body_text(message)
    return parse_swr_claim_mail(subject=subject, from_addr=from_addr, body=body)


def swr_claim_search_query(claim_id: str) -> str:
    """Gmail search query for a known claim id (and SWR sender domain)."""
    cid = normalize_claim_id(claim_id) or claim_id.strip()
    return f'from:firstcustomercontact.com subject:"Delay Repay" subject:{cid}'
