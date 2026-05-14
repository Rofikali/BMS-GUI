from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bms.core import AppendRecord, BmsCore


class CoreFileStore:
    def __init__(self, data_root: Path, core: BmsCore | None = None) -> None:
        self.data_root = data_root
        self.core = core or BmsCore()

    @property
    def event_log(self) -> Path:
        return self.data_root / "events" / "business_events.jsonl"

    @property
    def journal_entries(self) -> Path:
        return self.data_root / "accounting" / "journal_entries.jsonl"

    @property
    def journal_lines(self) -> Path:
        return self.data_root / "accounting" / "journal_lines.jsonl"

    @property
    def wal(self) -> Path:
        return self.data_root / "wal" / "current.wal.jsonl"

    def append_record(
        self,
        path: Path,
        record_type: str,
        actor_id: str,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, object],
        record_id: str | None = None,
        created_at: str | None = None,
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
            ),
        )

    def append_business_event(
        self,
        event_type: str,
        actor_id: str,
        payload: dict[str, object],
        correlation_id: str | None = None,
        occurred_at: str | None = None,
    ) -> int:
        now = occurred_at or _utc_now()
        event_correlation_id = correlation_id or f"corr_{uuid4().hex}"
        record_id = f"evt_{uuid4().hex}"
        return self.core.append_record(
            self.event_log,
            AppendRecord(
                record_id=record_id,
                record_type="event.business",
                created_at=now,
                actor_id=actor_id,
                correlation_id=event_correlation_id,
                idempotency_key=f"{event_type}_{record_id}",
                payload={
                    "event_type": event_type,
                    "occurred_at": now,
                    "source_module": "app",
                    "payload": payload,
                },
            ),
        )

    def verify_business_events(self) -> int:
        return self.core.verify_file(self.event_log)

    def read_payloads(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        self.core.verify_file(path)
        payloads: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    payload = json.loads(line)["payload"]
                    if isinstance(payload, dict):
                        payloads.append(payload)
        return payloads

    def wal_smoke_commit(self, actor_id: str = "usr_admin") -> None:
        now = _utc_now()
        transaction_id = f"txn_{uuid4().hex}"
        correlation_id = f"corr_{uuid4().hex}"
        self.core.append_wal_pending(
            self.wal,
            transaction_id,
            now,
            actor_id,
            correlation_id,
            {"operation": "app.startup.smoke"},
        )
        self.core.append_wal_committed(self.wal, transaction_id, _utc_now(), actor_id, correlation_id)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
