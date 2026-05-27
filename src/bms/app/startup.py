from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from bms.core import (
    BmsCoreError,
    BMS_ERR_PROTECTED_MODE,
    BMS_ERR_RECOVERY_REQUIRED,
    BMS_OK,
    BMS_WAL_RECOVERY_CLEAN,
    BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT,
    BMS_WAL_RECOVERY_PENDING_ROLLBACK,
    BMS_WAL_RECOVERY_PROTECTED_READ_ONLY,
)
from bms.storage.file_store.core_store import CoreFileStore


class StartupState(StrEnum):
    HEALTHY = "healthy"
    RECOVERY_REQUIRED = "recovery_required"
    PROTECTED_MODE = "protected_mode"


@dataclass(frozen=True)
class StartupHealth:
    state: StartupState
    wal_status: int
    wal_decision: int
    message: str


class StartupHealthService:
    def __init__(self, store: CoreFileStore) -> None:
        self.store = store

    def inspect(self, required_snapshot_path: Path | None = None) -> StartupHealth:
        result = self.store.inspect_wal_startup(required_snapshot_path)
        if result.status == BMS_OK and result.decision == BMS_WAL_RECOVERY_CLEAN:
            source_health = self._inspect_source_files()
            if source_health is not None:
                return source_health
            return StartupHealth(
                state=StartupState.HEALTHY,
                wal_status=result.status,
                wal_decision=result.decision,
                message="storage is clean",
            )
        if result.status == BMS_ERR_PROTECTED_MODE or result.decision == BMS_WAL_RECOVERY_PROTECTED_READ_ONLY:
            return StartupHealth(
                state=StartupState.PROTECTED_MODE,
                wal_status=result.status,
                wal_decision=result.decision,
                message="storage entered protected read-only mode",
            )
        if result.status == BMS_ERR_RECOVERY_REQUIRED and result.decision in _RECOVERY_REQUIRED_DECISIONS:
            return StartupHealth(
                state=StartupState.RECOVERY_REQUIRED,
                wal_status=result.status,
                wal_decision=result.decision,
                message="storage recovery is required before normal startup",
            )
        return StartupHealth(
            state=StartupState.PROTECTED_MODE,
            wal_status=result.status,
            wal_decision=result.decision,
            message="storage startup returned an unknown WAL state",
        )

    def _inspect_source_files(self) -> StartupHealth | None:
        for attribute_name in _SOURCE_FILE_ATTRIBUTES:
            path = getattr(self.store, attribute_name)
            try:
                self.store.core.verify_file(path)
            except BmsCoreError:
                return StartupHealth(
                    state=StartupState.PROTECTED_MODE,
                    wal_status=BMS_ERR_PROTECTED_MODE,
                    wal_decision=BMS_WAL_RECOVERY_PROTECTED_READ_ONLY,
                    message=f"source file failed integrity verification: {path.name}",
                )
        return None


_RECOVERY_REQUIRED_DECISIONS = {
    BMS_WAL_RECOVERY_PENDING_ROLLBACK,
    BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT,
}

_SOURCE_FILE_ATTRIBUTES = (
    "business_events",
    "journal_entries",
    "journal_lines",
    "periods",
    "items",
    "stock_movements",
    "invoices",
    "invoice_lines",
    "refunds",
    "refund_lines",
    "audit_records",
    "reconciliation_records",
)
