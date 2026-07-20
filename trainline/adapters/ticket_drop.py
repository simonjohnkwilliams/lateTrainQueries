"""Ticket drop helpers — content-hash dedup + safe naming (Epic 8 / FR42–FR44).

No Gmail or ticket_intake imports (AD-2). Callers pass destination Paths.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".pdf"})
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "ticket"
    return cleaned[:180]


class DropHashStore:
    """Persists seen content hashes under a JSON file (gitignored via Results/)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._hashes: set[str] = set()
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._hashes = set(raw.get("hashes", []))

    def has(self, digest: str) -> bool:
        return digest in self._hashes

    def add(self, digest: str) -> None:
        self._hashes.add(digest)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"hashes": sorted(self._hashes)}, indent=2) + "\n",
            encoding="utf-8",
        )


def unique_drop_path(
    dest_dir: Path,
    data: bytes,
    original_name: str,
    *,
    store: DropHashStore,
) -> Path | None:
    """Return a path under ``dest_dir`` for ``data``, or None if duplicate hash."""
    digest = content_hash(data)
    if store.has(digest):
        return None
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_filename(original_name)
    stem = Path(safe).stem
    suffix = Path(safe).suffix.lower() or ".jpg"
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"
    short = digest[:10]
    candidate = dest_dir / f"{stem}-{short}{suffix}"
    n = 2
    while candidate.exists():
        candidate = dest_dir / f"{stem}-{short}-{n}{suffix}"
        n += 1
    store.add(digest)
    return candidate


@dataclass
class DropSummary:
    saved: int = 0
    skipped: int = 0
    duplicates: int = 0
    paths: list[str] = field(default_factory=list)


def ingest_folder_images(
    *,
    inbox_dir: Path,
    dest_dir: Path,
    processed_dir: Path,
    hash_store_path: Path,
) -> DropSummary:
    """Move/copy images from inbox → unclassified with hash dedup (Story 8.3)."""
    summary = DropSummary()
    inbox_dir = Path(inbox_dir)
    dest_dir = Path(dest_dir)
    processed_dir = Path(processed_dir)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    store = DropHashStore(hash_store_path)

    for src in sorted(inbox_dir.iterdir()):
        if not src.is_file():
            continue
        ext = src.suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            summary.skipped += 1
            # Park non-images so they are not re-scanned forever
            dest = processed_dir / src.name
            if dest.exists():
                dest = processed_dir / f"{src.stem}-skip{src.suffix}"
            shutil.move(str(src), str(dest))
            continue
        data = src.read_bytes()
        if not data:
            summary.skipped += 1
            shutil.move(str(src), str(processed_dir / src.name))
            continue
        path = unique_drop_path(dest_dir, data, src.name, store=store)
        if path is None:
            summary.duplicates += 1
            shutil.move(str(src), str(processed_dir / src.name))
            continue
        path.write_bytes(data)
        src.unlink(missing_ok=True)
        summary.saved += 1
        summary.paths.append(str(path))
    return summary
