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
def test_build_ticket_mail_query_primary_inbox_only():
    q = build_ticket_mail_query(
        subject_prefix="TICKET",
        label=None,
        ingested_label="trainline-ticket-ingested",
    )
    assert "in:inbox" in q
    assert "category:primary" in q
    assert "subject:TICKET" in q
    assert "has:attachment" in q
    # Must still pick up mails moved back into Primary even if labeled before
    assert "-label:trainline-ticket-ingested" not in q


@pytest.mark.offline
def test_extract_image_attachments_allows_pdf_and_skips_txt():
    msg = {
        "id": "m3",
        "payload": {
            "parts": [
                {
                    "filename": "notes.txt",
                    "mimeType": "text/plain",
                    "body": {"attachmentId": "T1", "size": 3},
                },
                {
                    "filename": "eticket.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": "P1", "size": 9},
                },
                {
                    "filename": "shot.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "J1", "size": 4},
                },
            ]
        },
    }
    parts = extract_image_attachments(msg)
    assert [p.filename for p in parts] == ["eticket.pdf", "shot.jpg"]


@pytest.mark.offline
def test_subject_matches_ticket_prefix_only_at_start():
    from trainline.adapters.gmail.ticket_mail import subject_matches_ticket_prefix

    assert subject_matches_ticket_prefix("TICKET GOD return")
    assert subject_matches_ticket_prefix("ticket photo")
    assert not subject_matches_ticket_prefix("Your England tickets")
    assert not subject_matches_ticket_prefix("Re: Delay Repay ticket")


@pytest.mark.offline
def test_ingest_skips_non_prefix_subject(tmp_path: Path):
    dest = tmp_path / "unclassified"
    dest.mkdir()
    jpeg = b"\xff\xd8\xff\xd9" + b"skipme"
    client = MagicMock()
    client.search_messages.return_value = [{"id": "msgX"}]
    client.get_message.return_value = {
        "id": "msgX",
        "payload": {
            "headers": [{"name": "Subject", "value": "Your match tickets"}],
            "parts": [
                {
                    "filename": "t.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "A9", "size": len(jpeg)},
                }
            ],
        },
    }
    client.ensure_label_id.return_value = "Label_1"

    from trainline import cli

    rc = cli._ingest_from_gmail_client(
        client,
        dest_dir=dest,
        hash_store_path=tmp_path / "hashes.json",
    )
    assert rc == 0
    assert list(dest.glob("*")) == []
    client.get_attachment.assert_not_called()



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
            "headers": [{"name": "Subject", "value": "TICKET GOD return"}],
            "parts": [
                {
                    "filename": "shot.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "ATT1", "size": len(jpeg)},
                }
            ],
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
    assert "INBOX" in kwargs.get("remove_label_ids", [])
    assert "UNREAD" in kwargs.get("remove_label_ids", [])


@pytest.mark.offline
def test_second_save_dedups_by_hash(tmp_path: Path):
    store = DropHashStore(tmp_path / "hashes.json")
    data = b"\xff\xd8\xff\xd9same"
    p1 = unique_drop_path(tmp_path, data, "a.jpg", store=store)
    assert p1 is not None
    p1.write_bytes(data)
    assert unique_drop_path(tmp_path, data, "b.jpg", store=store) is None


@pytest.mark.offline
def test_ingest_saves_when_label_scope_missing(tmp_path: Path):
    """Readonly token: download must succeed; label/modify soft-fails (hash dedup)."""
    from trainline.adapters.gmail.errors import GmailError

    dest = tmp_path / "unclassified"
    dest.mkdir()
    jpeg = b"\xff\xd8\xff\xd9" + b"scope" * 8
    client = MagicMock()
    client.search_messages.return_value = [{"id": "msg1"}]
    client.get_message.return_value = {
        "id": "msg1",
        "payload": {
            "headers": [{"name": "Subject", "value": "TICKET phone"}],
            "parts": [
                {
                    "filename": "phone.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "ATT1", "size": len(jpeg)},
                }
            ],
        },
    }
    client.get_attachment.return_value = jpeg
    client.ensure_label_id.side_effect = GmailError(
        "HttpError 403 insufficientPermissions Request had insufficient "
        "authentication scopes."
    )

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
    client.modify_message.assert_not_called()
    client.get_attachment.assert_called_once()


@pytest.mark.offline
def test_ingest_soft_fails_modify_after_save(tmp_path: Path):
    from trainline.adapters.gmail.errors import GmailError

    dest = tmp_path / "unclassified"
    dest.mkdir()
    jpeg = b"\xff\xd8\xff\xd9" + b"mod" * 10
    client = MagicMock()
    client.search_messages.return_value = [{"id": "msg2"}]
    client.get_message.return_value = {
        "id": "msg2",
        "payload": {
            "headers": [{"name": "Subject", "value": "TICKET t"}],
            "parts": [
                {
                    "filename": "t.jpg",
                    "mimeType": "image/jpeg",
                    "body": {"attachmentId": "A2", "size": len(jpeg)},
                }
            ],
        },
    }
    client.get_attachment.return_value = jpeg
    client.ensure_label_id.return_value = "Label_1"
    client.modify_message.side_effect = GmailError(
        "403 Forbidden insufficientPermissions"
    )

    from trainline import cli

    rc = cli._ingest_from_gmail_client(
        client,
        dest_dir=dest,
        hash_store_path=tmp_path / "hashes.json",
    )
    assert rc == 0
    assert list(dest.glob("*.jpg"))
    client.get_attachment.assert_called()


@pytest.mark.offline
def test_token_missing_modify_scope_is_detected():
    from trainline.adapters.gmail.auth import (
        GMAIL_SCOPES,
        token_missing_required_scopes,
    )

    assert token_missing_required_scopes(
        ["https://www.googleapis.com/auth/gmail.readonly"]
    )
    assert not token_missing_required_scopes(list(GMAIL_SCOPES))


@pytest.mark.offline
def test_image_extensions_include_jpeg_png_pdf():
    assert ".jpg" in IMAGE_EXTENSIONS
    assert ".png" in IMAGE_EXTENSIONS
    assert ".pdf" in IMAGE_EXTENSIONS
