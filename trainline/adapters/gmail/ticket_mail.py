"""Gmail ticket-photo parsing helpers (Epic 8).

Pure extraction + query building. Does not import ticket_drop / ticket_intake (AD-2).
CLI downloads bytes and writes via ticket_drop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Phone-drop attachments: photos + PDF scans (Simon 2026-07-27).
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".pdf"})


@dataclass(frozen=True)
class AttachmentRef:
    filename: str
    attachment_id: str
    mime_type: str


def build_ticket_mail_query(
    *,
    subject_prefix: str = "TICKET",
    label: str | None = None,
    ingested_label: str = "trainline-ticket-ingested",
) -> str:
    """Primary-inbox search; callers also enforce subject prefix locally.

    Unprocessed = still in Primary inbox (needs action). We intentionally do
    **not** exclude ``ingested_label`` here: if Simon moves a mail back into
    Primary, re-ingest must rematerialise missing files. Dedup is content-hash
    + on-disk presence. After success we label + archive out of INBOX.
    """
    del ingested_label  # kept for API stability / callers
    parts = [
        "in:inbox",
        "category:primary",
        "has:attachment",
    ]
    if label:
        parts.append(f"label:{label}")
    else:
        parts.append(f"subject:{subject_prefix}")
    return " ".join(parts)


def message_subject(message: dict[str, Any]) -> str:
    headers = (message.get("payload") or {}).get("headers") or []
    for h in headers:
        if str(h.get("name") or "").casefold() == "subject":
            return str(h.get("value") or "")
    return ""


def subject_matches_ticket_prefix(
    subject: str, *, prefix: str = "TICKET"
) -> bool:
    """True when subject starts with ``prefix`` (case-insensitive; FR41)."""
    return (subject or "").lstrip().casefold().startswith(prefix.casefold())


def _walk_parts(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    parts = payload.get("parts")
    if not parts:
        return [payload]
    out: list[dict[str, Any]] = []
    for part in parts:
        out.extend(_walk_parts(part))
    return out


def extract_image_attachments(message: dict[str, Any]) -> list[AttachmentRef]:
    """Return jpg/jpeg/png/pdf attachment refs."""
    refs: list[AttachmentRef] = []
    for part in _walk_parts(message.get("payload")):
        filename = (part.get("filename") or "").strip()
        body = part.get("body") or {}
        att_id = body.get("attachmentId")
        if not filename or not att_id:
            continue
        mime = (part.get("mimeType") or "").lower()
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            refs.append(
                AttachmentRef(
                    filename=filename, attachment_id=att_id, mime_type=mime
                )
            )
            continue
        if not ext and mime in {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "application/pdf",
        }:
            refs.append(
                AttachmentRef(
                    filename=filename, attachment_id=att_id, mime_type=mime
                )
            )
    return refs
