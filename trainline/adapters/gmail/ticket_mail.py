"""Gmail ticket-photo parsing helpers (Epic 8).

Pure extraction + query building. Does not import ticket_drop / ticket_intake (AD-2).
CLI downloads bytes and writes via ticket_drop.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    parts = ["has:attachment", f"-label:{ingested_label}"]
    if label:
        parts.append(f"label:{label}")
    else:
        parts.append(f"subject:{subject_prefix}")
    return " ".join(parts)


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
    refs: list[AttachmentRef] = []
    for part in _walk_parts(message.get("payload")):
        filename = (part.get("filename") or "").strip()
        body = part.get("body") or {}
        att_id = body.get("attachmentId")
        if not filename or not att_id:
            continue
        mime = (part.get("mimeType") or "").lower()
        ext = Path(filename).suffix.lower()
        if mime.startswith("image/") or ext in IMAGE_EXTENSIONS:
            refs.append(
                AttachmentRef(
                    filename=filename, attachment_id=att_id, mime_type=mime
                )
            )
    return refs
