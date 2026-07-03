from __future__ import annotations

from pathlib import Path
from typing import Protocol

from bms.core import AppendRecord, WalRecoveryResult


class DurabilityCorePort(Protocol):
    def append_record(self, path: Path, record: AppendRecord) -> int:
        raise NotImplementedError

    def verify_file(self, path: Path) -> int:
        raise NotImplementedError

    def append_wal_pending(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
        payload: dict[str, object],
    ) -> None:
        raise NotImplementedError

    def append_wal_committed(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
    ) -> None:
        raise NotImplementedError

    def inspect_wal_startup(
        self,
        wal_path: Path,
        required_snapshot_path: Path | None = None,
    ) -> WalRecoveryResult:
        raise NotImplementedError

    def recover_wal_startup(
        self,
        wal_path: Path,
        required_snapshot_path: Path | None = None,
    ) -> WalRecoveryResult:
        raise NotImplementedError


class DurableStorePort(Protocol):
    data_root: Path
    core: DurabilityCorePort

    wal: Path
    business_events: Path
    journal_entries: Path
    journal_lines: Path
    periods: Path
    items: Path
    stock_movements: Path
    invoices: Path
    invoice_lines: Path
    refunds: Path
    refund_lines: Path
    audit_records: Path
    reconciliation_records: Path
    users: Path
    roles: Path

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
        raise NotImplementedError

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
        raise NotImplementedError

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
        raise NotImplementedError

    def verify_business_events(self) -> int:
        raise NotImplementedError

    def wal_smoke_commit(self, actor_id: str = "usr_system") -> None:
        raise NotImplementedError

    def inspect_wal_startup(self, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        raise NotImplementedError

    def recover_wal_startup(self, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        raise NotImplementedError

    def read_payloads(self, path: Path) -> list[dict[str, object]]:
        raise NotImplementedError
