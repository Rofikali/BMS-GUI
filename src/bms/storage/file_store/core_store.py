from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bms.core import AppendRecord, BmsCore, WalRecoveryResult


class CoreFileStore:
    """Thin Python repository facade over the native C durability core."""

    def __init__(self, data_root: Path, core: BmsCore | None = None) -> None:
        self.data_root = data_root
        self.core = core or BmsCore()

        self.wal = self.data_root / "wal" / "current.wal.jsonl"
        self.business_events = self.data_root / "events" / "business_events.jsonl"
        self.journal_entries = self.data_root / "accounting" / "journal_entries.jsonl"
        self.journal_lines = self.data_root / "accounting" / "journal_lines.jsonl"
        self.periods = self.data_root / "accounting" / "periods.jsonl"
        self.items = self.data_root / "inventory" / "items.jsonl"
        self.stock_movements = self.data_root / "inventory" / "stock_movements.jsonl"
        self.invoices = self.data_root / "billing" / "invoices.jsonl"
        self.invoice_lines = self.data_root / "billing" / "invoice_lines.jsonl"
        self.audit_records = self.data_root / "audit" / "audit_records.jsonl"

    def append_record(
        self,
        path: Path,
        record_type: str,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, object],
        *,
        record_id: str | None = None,
        created_at: str | None = None,
        schema_version: int = 1,
    ) -> int:
        return self.core.append_record(
            path,
            AppendRecord(
                record_id=record_id or f"rec_{uuid4().hex}",
                record_type=record_type,
                created_at=created_at or _utc_now(),
                actor_id=actor_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                payload=payload,
                schema_version=schema_version,
            ),
        )

    def append_business_event(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, object],
        *,
        correlation_id: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        event_id = f"evt_{uuid4().hex}"
        created_at = occurred_at or _utc_now()
        return self.append_record(
            self.business_events,
            "event.business",
            actor_id,
            correlation_id or event_id,
            idempotency_key or event_id,
            {
                "event_type": event_type,
                "occurred_at": created_at,
                **payload,
            },
            record_id=event_id,
            created_at=created_at,
        )


    def append_audit_record(
        self,
        action: str,
        actor_id: str,
        target_type: str,
        target_id: str,
        correlation_id: str,
        *,
        occurred_at: str | None = None,
        details: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        created_at = occurred_at or _utc_now()
        record_id = f"aud_{action}_{target_id}"
        return self.append_record(
            self.audit_records,
            "audit.record",
            actor_id,
            correlation_id,
            idempotency_key or record_id,
            {
                "action": action,
                "actor_id": actor_id,
                "occurred_at": created_at,
                "target_type": target_type,
                "target_id": target_id,
                "correlation_id": correlation_id,
                "details": details or {},
            },
            record_id=record_id,
            created_at=created_at,
        )

    def verify_business_events(self) -> int:
        return self.core.verify_file(self.business_events)

    def wal_smoke_commit(self, actor_id: str = "usr_system") -> None:
        transaction_id = f"txn_smoke_{uuid4().hex}"
        created_at = _utc_now()
        correlation_id = f"corr_{transaction_id}"
        self.core.append_wal_pending(
            self.wal,
            transaction_id,
            created_at,
            actor_id,
            correlation_id,
            {"operation": "wal.smoke_commit"},
        )
        self.core.append_wal_committed(
            self.wal,
            transaction_id,
            created_at,
            actor_id,
            correlation_id,
        )

    def inspect_wal_startup(self, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        return self.core.inspect_wal_startup(self.wal, required_snapshot_path)

    def recover_wal_startup(self, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        return self.core.recover_wal_startup(self.wal, required_snapshot_path)

    def read_payloads(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []

        self.core.verify_file(path)
        payloads: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as records:
            for line in records:
                line = line.strip()
                if not line:
                    continue
                envelope = json.loads(line)
                payload = envelope.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError(f"record in {path} has non-object payload")
                payloads.append(payload)
        return payloads


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
