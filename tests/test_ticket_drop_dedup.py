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
def test_unique_drop_path_rematerialises_when_file_missing(tmp_path: Path):
    """Hash recorded but file deleted (e.g. quarantine) must allow re-save."""
    dest = tmp_path / "unclassified"
    dest.mkdir()
    store = DropHashStore(tmp_path / "hashes.json")
    data = b"\xff\xd8\xff\xd9digital"
    first = unique_drop_path(dest, data, "shot.jpg", store=store)
    assert first is not None
    first.write_bytes(data)
    first.unlink()
    assert not first.exists()
    again = unique_drop_path(
        dest,
        data,
        "shot.jpg",
        store=store,
        presence_roots=[dest],
    )
    assert again is not None
    again.write_bytes(data)
    assert again.exists()


@pytest.mark.offline
def test_unique_drop_path_still_dedups_when_file_elsewhere(tmp_path: Path):
    dest = tmp_path / "unclassified"
    ready = tmp_path / "ready"
    dest.mkdir()
    ready.mkdir()
    store = DropHashStore(tmp_path / "hashes.json")
    data = b"\xff\xd8\xff\xd9moved"
    first = unique_drop_path(dest, data, "a.jpg", store=store)
    assert first is not None
    moved = ready / first.name
    first.write_bytes(data)
    first.rename(moved)
    again = unique_drop_path(
        dest,
        data,
        "b.jpg",
        store=store,
        presence_roots=[dest, ready],
    )
    assert again is None
