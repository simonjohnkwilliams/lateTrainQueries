"""Epic 7 / Story 7.5 — claim lifecycle store (FR37–FR39).

Each test importorskips until ``trainline.adapters.claim_lifecycle`` lands.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest


def _mod():
    return pytest.importorskip(
        "trainline.adapters.claim_lifecycle",
        reason="Story 7.5 claim_lifecycle not implemented yet",
    )


def _store(tmp_path: Path):
    claim_lifecycle = _mod()
    return claim_lifecycle.LifecycleStore(tmp_path / "claim_lifecycle.json")


@pytest.mark.offline
def test_upsert_submitted_on_successful_file(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_submitted(
        claim_id="SWR-0218-108-579",
        journey_date="2026-07-16",
        summary="GOD->WAT outbound",
        when=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        audit_ref="audit-line-1",
    )
    row = store.get("SWR-0218-108-579")
    assert row is not None
    assert row.status == "submitted"
    assert row.journey_date == "2026-07-16"


@pytest.mark.offline
def test_inbox_stages_promote_received_approved_paid(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_submitted(
        claim_id="SWR-0218-108-579",
        journey_date="2026-07-16",
        summary="x",
        when=datetime(2026, 7, 17, tzinfo=UTC),
    )
    store.apply_inbox_stage(
        "SWR-0218-108-579", "received", datetime(2026, 7, 17, 13, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "received"
    store.apply_inbox_stage(
        "SWR-0218-108-579", "approved", datetime(2026, 7, 18, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "approved"
    store.apply_inbox_stage(
        "SWR-0218-108-579", "paid", datetime(2026, 7, 19, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "paid"


@pytest.mark.offline
def test_inbox_does_not_downgrade_paid_to_received(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_submitted(
        claim_id="SWR-0001-000-001",
        journey_date="2026-07-01",
        summary="x",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_inbox_stage(
        "SWR-0001-000-001", "paid", datetime(2026, 7, 10, tzinfo=UTC)
    )
    store.apply_inbox_stage(
        "SWR-0001-000-001", "received", datetime(2026, 7, 11, tzinfo=UTC)
    )
    assert store.get("SWR-0001-000-001").status == "paid"


@pytest.mark.offline
def test_open_for_table2_omits_reported_paid(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_submitted(
        claim_id="SWR-0001-000-001",
        journey_date="2026-07-01",
        summary="a",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_inbox_stage(
        "SWR-0001-000-001", "paid", datetime(2026, 7, 5, tzinfo=UTC)
    )
    store.mark_reported_paid(
        ["SWR-0001-000-001"], datetime(2026, 7, 11, tzinfo=UTC)
    )

    store.upsert_submitted(
        claim_id="SWR-0002-000-002",
        journey_date="2026-07-08",
        summary="b",
        when=datetime(2026, 7, 10, tzinfo=UTC),
    )
    ids = {r.claim_id for r in store.open_for_table2()}
    assert "SWR-0001-000-001" not in ids
    assert "SWR-0002-000-002" in ids


@pytest.mark.offline
def test_idempotent_upsert_same_claim_id(tmp_path: Path):
    store = _store(tmp_path)
    store.upsert_submitted(
        claim_id="SWR-0218-108-579",
        journey_date="2026-07-16",
        summary="first",
        when=datetime(2026, 7, 17, tzinfo=UTC),
    )
    store.upsert_submitted(
        claim_id="SWR-0218-108-579",
        journey_date="2026-07-16",
        summary="second",
        when=datetime(2026, 7, 17, 1, tzinfo=UTC),
    )
    assert len(list(store.all())) == 1


@pytest.mark.offline
def test_store_module_does_not_import_gmail():
    claim_lifecycle = _mod()
    src = Path(claim_lifecycle.__file__).read_text(encoding="utf-8")
    assert "gmail" not in src.casefold()
    assert "playwright" not in src.casefold()
