"""Epic 8 — content-hash dedup + safe naming (Story 8.2). Offline."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.ticket_drop import (
    DropHashStore,
    content_hash,
    sanitize_filename,
    unique_drop_path,
)


@pytest.mark.offline
def test_content_hash_stable():
    assert content_hash(b"abc") == content_hash(b"abc")
    assert content_hash(b"abc") != content_hash(b"abd")


@pytest.mark.offline
def test_sanitize_filename_strips_path_and_unsafe():
    assert sanitize_filename(r"..\foo\bar!.JPG") == "bar_.JPG"
    assert sanitize_filename("ok-ticket_01.jpg") == "ok-ticket_01.jpg"


@pytest.mark.offline
def test_unique_drop_path_dedups_identical_bytes(tmp_path: Path):
    store = DropHashStore(tmp_path / "hashes.json")
    data = b"\xff\xd8\xff\xd9fakejpeg"
    first = unique_drop_path(tmp_path, data, "a.jpg", store=store)
    assert first is not None
    first.write_bytes(data)
    second = unique_drop_path(tmp_path, data, "b.jpg", store=store)
    assert second is None
    assert len(list(tmp_path.glob("*.jpg"))) == 1


@pytest.mark.offline
def test_unique_drop_path_allows_different_bytes(tmp_path: Path):
    store = DropHashStore(tmp_path / "hashes.json")
    a = unique_drop_path(tmp_path, b"one", "a.jpg", store=store)
    b = unique_drop_path(tmp_path, b"two", "b.jpg", store=store)
    assert a is not None and b is not None
    assert a != b
