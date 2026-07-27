"""Claim lifecycle current-status store (AD-18, AD-19).

Owns mutable claim status keyed by SWR claim id. Filing audit JSONL remains
append-only history elsewhere — this module never rewrites it.

Hexagonal: no mail-client or browser-automation imports (AD-2 / AD-19).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

DEFAULT_LIFECYCLE_PATH = Path("Results") / "claim-lifecycle.json"

# Monotonic inbox/file rank. ``failed`` is terminal and handled separately.
_STAGE_RANK: dict[str, int] = {
    "submitted": 0,
    "received": 1,
    "approved": 2,
    "paid": 3,
}
_VALID_STATUSES = frozenset({*_STAGE_RANK, "failed"})


def _iso(when: datetime | None = None) -> str:
    ts = when if when is not None else datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class ClaimLifecycleRecord:
    claim_id: str
    status: str
    date: str
    direction: str
    updated_at: str
    amount_gbp: float | None = None
    reported_paid_at: str | None = None


class LifecycleStore:
    """JSON map of claim_id → current lifecycle record."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_LIFECYCLE_PATH
        self._rows: dict[str, ClaimLifecycleRecord] = {}
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError(f"claim lifecycle must be a JSON object: {self.path}")
            for claim_id, payload in raw.items():
                self._rows[claim_id] = _record_from_dict(claim_id, payload)

    def record_submitted(
        self,
        claim_id: str,
        *,
        date: str,
        direction: str,
        when: datetime | None = None,
        amount_gbp: float | None = None,
    ) -> ClaimLifecycleRecord:
        claim_id = _require_claim_id(claim_id)
        existing = self._rows.get(claim_id)
        # Do not regress or rewrite an advanced / failed claim.
        if existing is not None and existing.status != "submitted":
            return existing

        row = ClaimLifecycleRecord(
            claim_id=claim_id,
            status="submitted",
            date=date,
            direction=direction,
            updated_at=_iso(when),
            amount_gbp=amount_gbp if amount_gbp is not None else (
                existing.amount_gbp if existing else None
            ),
            reported_paid_at=existing.reported_paid_at if existing else None,
        )
        self._rows[claim_id] = row
        self._save()
        return row

    def apply_stage(
        self,
        claim_id: str,
        stage: str,
        when: datetime | None = None,
    ) -> ClaimLifecycleRecord | None:
        claim_id = claim_id.strip()
        stage_key = stage.strip().casefold().replace(" ", "_")
        # Accept ClaimMailStage-style "payment_sent" → paid
        if stage_key == "payment_sent":
            stage_key = "paid"
        if stage_key not in _VALID_STATUSES:
            return self._rows.get(claim_id)

        existing = self._rows.get(claim_id)
        if existing is None:
            return None
        if existing.status == "failed":
            return existing
        # ``failed`` only from ``submitted`` (filing failure) — never regress paid/etc.
        if stage_key == "failed":
            if existing.status != "submitted":
                return existing
            updated = ClaimLifecycleRecord(
                claim_id=existing.claim_id,
                status="failed",
                date=existing.date,
                direction=existing.direction,
                updated_at=_iso(when),
                amount_gbp=existing.amount_gbp,
                reported_paid_at=existing.reported_paid_at,
            )
            self._rows[claim_id] = updated
            self._save()
            return updated

        current_rank = _STAGE_RANK.get(existing.status)
        next_rank = _STAGE_RANK.get(stage_key)
        if current_rank is None or next_rank is None or next_rank <= current_rank:
            return existing

        updated = ClaimLifecycleRecord(
            claim_id=existing.claim_id,
            status=stage_key,
            date=existing.date,
            direction=existing.direction,
            updated_at=_iso(when),
            amount_gbp=existing.amount_gbp,
            reported_paid_at=existing.reported_paid_at,
        )
        self._rows[claim_id] = updated
        self._save()
        return updated

    def get(self, claim_id: str) -> ClaimLifecycleRecord | None:
        return self._rows.get(claim_id)

    def all(self) -> list[ClaimLifecycleRecord]:
        return [self._rows[k] for k in sorted(self._rows)]

    def open_for_table2(self) -> list[ClaimLifecycleRecord]:
        return [r for r in self.all() if r.reported_paid_at is None]

    def mark_reported_paid(
        self,
        claim_ids: Iterable[str],
        when: datetime | None = None,
    ) -> None:
        stamp = _iso(when)
        changed = False
        for claim_id in claim_ids:
            row = self._rows.get(claim_id)
            if row is None:
                continue
            # AD-20 / FR39: only paid rows leave Table 2 via reported_paid_at.
            if row.status != "paid":
                continue
            if row.reported_paid_at is not None:
                continue
            self._rows[claim_id] = ClaimLifecycleRecord(
                claim_id=row.claim_id,
                status=row.status,
                date=row.date,
                direction=row.direction,
                updated_at=stamp,
                amount_gbp=row.amount_gbp,
                reported_paid_at=stamp,
            )
            changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {cid: asdict(row) for cid, row in sorted(self._rows.items())}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _require_claim_id(claim_id: str) -> str:
    cleaned = claim_id.strip()
    if not cleaned:
        raise ValueError("claim_id must be non-empty")
    return cleaned


def _coerce_amount(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"invalid amount_gbp: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    raise ValueError(f"invalid amount_gbp: {value!r}")


def _normalize_reported(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _record_from_dict(claim_id: str, payload: object) -> ClaimLifecycleRecord:
    if not isinstance(payload, dict):
        raise ValueError(f"invalid lifecycle row for {claim_id}")
    status = str(payload.get("status", "submitted"))
    if status not in _VALID_STATUSES:
        raise ValueError(f"invalid lifecycle status {status!r} for {claim_id}")
    return ClaimLifecycleRecord(
        claim_id=str(payload.get("claim_id", claim_id)),
        status=status,
        date=str(payload.get("date", "")),
        direction=str(payload.get("direction", "")),
        updated_at=str(payload.get("updated_at", "")),
        amount_gbp=_coerce_amount(payload.get("amount_gbp")),
        reported_paid_at=_normalize_reported(payload.get("reported_paid_at")),
    )
