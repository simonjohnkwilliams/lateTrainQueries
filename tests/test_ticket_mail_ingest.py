"""Epic 8.1 — Gmail ticket mail ingest (mocked). Offline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from trainline.adapters.gmail.ticket_mail import (
    IMAGE_EXTENSIONS,
    build_ticket_mail_query,
    extract_image_attachments,
)
from trainline.adapters.ticket_drop import DropHashStore, unique_drop_path


@pytest.mark.offline
def test_build_ticket_mail_query_excludes_ingested():
    q = build_ticket_mail_query(
        subject_prefix="TICKET",
        label=None,
        ingested_label="trainline-ticket-ingested",
    )
    assert "subject:TICKET" in q
    assert "has:attachment" in q
    assert "-label:trainline-ticket-ingested" in q


@pytest.mark.offline
def test_extract_image_attachments_skips_non_image():
    msg = {
        "id": "m1",
        "payload": {
            "parts": [
                {
                    "filename": "notes.txt",
                    "mimeType": "text/plain",
                    "body": {"attachmentId": "A0", "size": 3},
                },
                {
                    "filename": "ticket.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "A1", "size": 10},
                },
            ]
        },
    }
    parts = extract_image_attachments(msg)
    assert len(parts) == 1
    assert parts[0].filename == "ticket.jpg"
    assert parts[0].attachment_id == "A1"


@pytest.mark.offline
def test_extract_nested_multipart_image():
    msg = {
        "id": "m2",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/related",
                    "parts": [
                        {
                            "filename": "nested.png",
                            "mimeType": "image/png",
                            "body": {"attachmentId": "N1", "size": 4},
                        }
                    ],
                }
            ],
        },
    }
    parts = extract_image_attachments(msg)
    assert len(parts) == 1
    assert parts[0].filename == "nested.png"
    assert parts[0].attachment_id == "N1"


@pytest.mark.offline
def test_ingest_pipeline_writes_jpeg_and_marks(tmp_path: Path):
    """Simulate CLI orchestration: extract → download → unique_drop_path → modify."""
    dest = tmp_path / "unclassified"
    dest.mkdir()
    jpeg = b"\xff\xd8\xff\xd9" + b"x" * 20
    client = MagicMock()
    client.search_messages.return_value = [{"id": "msg1"}]
    client.get_message.return_value = {
        "id": "msg1",
        "payload": {
            "parts": [
                {
                    "filename": "shot.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "ATT1", "size": len(jpeg)},
                }
            ]
        },
    }
    client.get_attachment.return_value = jpeg
    client.ensure_label_id.return_value = "Label_99"

    from trainline import cli

    rc = cli._ingest_from_gmail_client(
        client,
        dest_dir=dest,
        hash_store_path=tmp_path / "hashes.json",
        subject_prefix="TICKET",
        label=None,
        ingested_label="trainline-ticket-ingested",
    )
    assert rc == 0
    files = list(dest.glob("*.jpg"))
    assert len(files) == 1
    assert files[0].read_bytes() == jpeg
    client.modify_message.assert_called()
    kwargs = client.modify_message.call_args.kwargs
    assert "Label_99" in kwargs.get("add_label_ids", [])


@pytest.mark.offline
def test_second_save_dedups_by_hash(tmp_path: Path):
    store = DropHashStore(tmp_path / "hashes.json")
    data = b"\xff\xd8\xff\xd9same"
    p1 = unique_drop_path(tmp_path, data, "a.jpg", store=store)
    assert p1 is not None
    p1.write_bytes(data)
    assert unique_drop_path(tmp_path, data, "b.jpg", store=store) is None


@pytest.mark.offline
def test_image_extensions_include_jpeg_png():
    assert ".jpg" in IMAGE_EXTENSIONS
    assert ".png" in IMAGE_EXTENSIONS
