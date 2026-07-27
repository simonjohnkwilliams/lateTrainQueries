"""Epic 9 / Story 9.1 — claim lifecycle store (AD-18, AD-19, FR37–FR39).

AD-12: tests written against the spine API first (``record_submitted`` /
``apply_stage``). Fail loud if the adapter is missing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from trainline.adapters import claim_lifecycle


def _store(tmp_path: Path):
    return claim_lifecycle.LifecycleStore(tmp_path / "claim-lifecycle.json")


@pytest.mark.offline
def test_default_lifecycle_path_uses_hyphenated_filename():
    assert claim_lifecycle.DEFAULT_LIFECYCLE_PATH == Path("Results") / "claim-lifecycle.json"


@pytest.mark.offline
def test_record_submitted_on_successful_file(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0218-108-579",
        date="2026-07-16",
        direction="outbound",
        when=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
    )
    row = store.get("SWR-0218-108-579")
    assert row is not None
    assert row.status == "submitted"
    assert row.date == "2026-07-16"
    assert row.direction == "outbound"
    assert row.reported_paid_at is None
    assert row.updated_at


@pytest.mark.offline
def test_apply_stage_promotes_received_approved_paid(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0218-108-579",
        date="2026-07-16",
        direction="outbound",
        when=datetime(2026, 7, 17, tzinfo=UTC),
    )
    store.apply_stage(
        "SWR-0218-108-579", "received", datetime(2026, 7, 17, 13, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "received"
    store.apply_stage(
        "SWR-0218-108-579", "approved", datetime(2026, 7, 18, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "approved"
    store.apply_stage(
        "SWR-0218-108-579", "paid", datetime(2026, 7, 19, tzinfo=UTC)
    )
    assert store.get("SWR-0218-108-579").status == "paid"


@pytest.mark.offline
def test_apply_stage_does_not_downgrade_paid_to_received(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0001-000-001",
        date="2026-07-01",
        direction="inbound",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_stage(
        "SWR-0001-000-001", "paid", datetime(2026, 7, 10, tzinfo=UTC)
    )
    store.apply_stage(
        "SWR-0001-000-001", "received", datetime(2026, 7, 11, tzinfo=UTC)
    )
    assert store.get("SWR-0001-000-001").status == "paid"


@pytest.mark.offline
def test_failed_is_terminal(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0003-000-003",
        date="2026-07-01",
        direction="outbound",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_stage(
        "SWR-0003-000-003", "failed", datetime(2026, 7, 3, tzinfo=UTC)
    )
    store.apply_stage(
        "SWR-0003-000-003", "received", datetime(2026, 7, 4, tzinfo=UTC)
    )
    assert store.get("SWR-0003-000-003").status == "failed"


@pytest.mark.offline
def test_open_for_table2_omits_reported_paid(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0001-000-001",
        date="2026-07-01",
        direction="outbound",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_stage(
        "SWR-0001-000-001", "paid", datetime(2026, 7, 5, tzinfo=UTC)
    )
    store.mark_reported_paid(
        ["SWR-0001-000-001"], datetime(2026, 7, 11, tzinfo=UTC)
    )

    store.record_submitted(
        claim_id="SWR-0002-000-002",
        date="2026-07-08",
        direction="inbound",
        when=datetime(2026, 7, 10, tzinfo=UTC),
    )
    ids = {r.claim_id for r in store.open_for_table2()}
    assert "SWR-0001-000-001" not in ids
    assert "SWR-0002-000-002" in ids


@pytest.mark.offline
def test_open_for_table2_includes_paid_until_reported(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0004-000-004",
        date="2026-07-01",
        direction="outbound",
        when=datetime(2026, 7, 2, tzinfo=UTC),
    )
    store.apply_stage(
        "SWR-0004-000-004", "paid", datetime(2026, 7, 5, tzinfo=UTC)
    )
    ids = {r.claim_id for r in store.open_for_table2()}
    assert "SWR-0004-000-004" in ids


@pytest.mark.offline
def test_idempotent_record_submitted_same_claim_id(tmp_path: Path):
    store = _store(tmp_path)
    store.record_submitted(
        claim_id="SWR-0218-108-579",
        date="2026-07-16",
        direction="outbound",
        when=datetime(2026, 7, 17, tzinfo=UTC),
    )
    store.record_submitted(
        claim_id="SWR-0218-108-579",
        date="2026-07-16",
        direction="outbound",
        when=datetime(2026, 7, 17, 1, tzinfo=UTC),
    )
    assert len(list(store.all())) == 1


@pytest.mark.offline
def test_store_persists_across_reload(tmp_path: Path):
    path = tmp_path / "claim-lifecycle.json"
    store = claim_lifecycle.LifecycleStore(path)
    store.record_submitted(
        claim_id="SWR-0218-108-579",
        date="2026-07-16",
        direction="outbound",
        when=datetime(2026, 7, 17, tzinfo=UTC),
    )
    reloaded = claim_lifecycle.LifecycleStore(path)
    row = reloaded.get("SWR-0218-108-579")
    assert row is not None
    assert row.status == "submitted"


@pytest.mark.offline
def test_store_module_does_not_import_gmail():
    src = Path(claim_lifecycle.__file__).read_text(encoding="utf-8")
    assert "gmail" not in src.casefold()
    assert "playwright" not in src.casefold()
