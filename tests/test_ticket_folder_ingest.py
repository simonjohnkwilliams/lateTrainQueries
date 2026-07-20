"""Epic 8.3 — folder inbox → unclassified drain. Offline."""
from __future__ import annotations

from pathlib import Path

import pytest

from trainline.adapters.ticket_drop import DropHashStore, ingest_folder_images


@pytest.mark.offline
def test_ingest_folder_moves_jpg_skips_txt(tmp_path: Path):
    inbox = tmp_path / "inbox"
    dest = tmp_path / "unclassified"
    processed = tmp_path / "inbox_processed"
    inbox.mkdir()
    dest.mkdir()
    (inbox / "t.jpg").write_bytes(b"\xff\xd8\xff\xd9jpg")
    (inbox / "notes.txt").write_text("nope", encoding="utf-8")

    summary = ingest_folder_images(
        inbox_dir=inbox,
        dest_dir=dest,
        processed_dir=processed,
        hash_store_path=tmp_path / "hashes.json",
    )
    assert summary.saved == 1
    assert summary.skipped >= 1
    assert (dest / "t.jpg").is_file() or list(dest.glob("*.jpg"))
    assert not (inbox / "t.jpg").exists()
    assert (processed / "notes.txt").is_file() or (inbox / "notes.txt").exists()


@pytest.mark.offline
def test_ingest_folder_second_run_no_duplicate(tmp_path: Path):
    inbox = tmp_path / "inbox"
    dest = tmp_path / "unclassified"
    processed = tmp_path / "inbox_processed"
    inbox.mkdir()
    dest.mkdir()
    data = b"\xff\xd8\xff\xd9dup"
    (inbox / "a.jpg").write_bytes(data)

    store = tmp_path / "hashes.json"
    ingest_folder_images(
        inbox_dir=inbox, dest_dir=dest, processed_dir=processed, hash_store_path=store
    )
    # Re-drop same bytes under a new name
    inbox.mkdir(exist_ok=True)
    (inbox / "b.jpg").write_bytes(data)
    s2 = ingest_folder_images(
        inbox_dir=inbox, dest_dir=dest, processed_dir=processed, hash_store_path=store
    )
    assert s2.duplicates == 1
    assert len(list(dest.glob("*.jpg"))) == 1
