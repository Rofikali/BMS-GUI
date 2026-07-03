from __future__ import annotations

import ctypes
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BMS_OK = 0
BMS_ERR_DUPLICATE_IDEMPOTENCY_KEY = 5
BMS_ERR_RECOVERY_REQUIRED = 7
BMS_ERR_PROTECTED_MODE = 8

BMS_WAL_RECOVERY_CLEAN = 0
BMS_WAL_RECOVERY_PENDING_ROLLBACK = 1
BMS_WAL_RECOVERY_COMMITTED_MISSING_SNAPSHOT = 2
BMS_WAL_RECOVERY_PROTECTED_READ_ONLY = 3


@dataclass(frozen=True)
class WalRecoveryResult:
    status: int
    decision: int


class BmsCoreError(RuntimeError):
    def __init__(self, operation: str, status: int) -> None:
        super().__init__(f"{operation} failed with BmsStatus {status}")
        self.operation = operation
        self.status = status


class _CBmsRecord(ctypes.Structure):
    _fields_ = [
        ("schema_version", ctypes.c_int),
        ("sequence", ctypes.c_ulonglong),
        ("record_id", ctypes.c_char_p),
        ("record_type", ctypes.c_char_p),
        ("created_at", ctypes.c_char_p),
        ("actor_id", ctypes.c_char_p),
        ("correlation_id", ctypes.c_char_p),
        ("idempotency_key", ctypes.c_char_p),
        ("payload_json", ctypes.c_char_p),
        ("checksum", ctypes.c_char * 72),
    ]


@dataclass(frozen=True)
class AppendRecord:
    record_id: str
    record_type: str
    created_at: str
    actor_id: str
    correlation_id: str
    idempotency_key: str
    payload: dict[str, Any]
    schema_version: int = 1


class BmsCore:
    def __init__(self, library_path: Path | None = None) -> None:
        self.library_path = library_path or find_core_library()
        self._lib = ctypes.CDLL(str(self.library_path))
        self._configure_api()

    def append_record(self, path: Path, record: AppendRecord) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(record.payload, sort_keys=True, separators=(",", ":"))
        c_record = _CBmsRecord(
            record.schema_version,
            0,
            record.record_id.encode(),
            record.record_type.encode(),
            record.created_at.encode(),
            record.actor_id.encode(),
            record.correlation_id.encode(),
            record.idempotency_key.encode(),
            payload_json.encode(),
            b"",
        )
        status = self._lib.bms_jsonl_append_record(str(path).encode(), ctypes.byref(c_record))
        if status != BMS_OK:
            raise BmsCoreError("bms_jsonl_append_record", status)
        return int(c_record.sequence)

    def verify_file(self, path: Path) -> int:
        valid_records = ctypes.c_ulonglong(0)
        status = self._lib.bms_jsonl_verify_file(str(path).encode(), ctypes.byref(valid_records))
        if status != BMS_OK:
            raise BmsCoreError("bms_jsonl_verify_file", status)
        return int(valid_records.value)

    def append_wal_pending(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> None:
        wal_path.parent.mkdir(parents=True, exist_ok=True)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        status = self._lib.bms_wal_append_pending(
            str(wal_path).encode(),
            transaction_id.encode(),
            created_at.encode(),
            actor_id.encode(),
            correlation_id.encode(),
            payload_json.encode(),
        )
        if status != BMS_OK:
            raise BmsCoreError("bms_wal_append_pending", status)

    def append_wal_committed(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
    ) -> None:
        status = self._lib.bms_wal_append_committed(
            str(wal_path).encode(),
            transaction_id.encode(),
            created_at.encode(),
            actor_id.encode(),
            correlation_id.encode(),
        )
        if status != BMS_OK:
            raise BmsCoreError("bms_wal_append_committed", status)

    def inspect_wal_startup(self, wal_path: Path, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        decision = ctypes.c_int(BMS_WAL_RECOVERY_CLEAN)
        snapshot = str(required_snapshot_path).encode() if required_snapshot_path else None
        status = self._lib.bms_wal_inspect_startup(str(wal_path).encode(), snapshot, ctypes.byref(decision))
        if status not in (BMS_OK, BMS_ERR_RECOVERY_REQUIRED, BMS_ERR_PROTECTED_MODE):
            raise BmsCoreError("bms_wal_inspect_startup", status)
        return WalRecoveryResult(status=int(status), decision=int(decision.value))

    def recover_wal_startup(self, wal_path: Path, required_snapshot_path: Path | None = None) -> WalRecoveryResult:
        decision = ctypes.c_int(BMS_WAL_RECOVERY_CLEAN)
        snapshot = str(required_snapshot_path).encode() if required_snapshot_path else None
        status = self._lib.bms_wal_recover_startup(str(wal_path).encode(), snapshot, ctypes.byref(decision))
        if status not in (BMS_OK, BMS_ERR_RECOVERY_REQUIRED, BMS_ERR_PROTECTED_MODE):
            raise BmsCoreError("bms_wal_recover_startup", status)
        return WalRecoveryResult(status=int(status), decision=int(decision.value))

    def _configure_api(self) -> None:
        self._lib.bms_jsonl_append_record.argtypes = [ctypes.c_char_p, ctypes.POINTER(_CBmsRecord)]
        self._lib.bms_jsonl_append_record.restype = ctypes.c_int
        self._lib.bms_jsonl_verify_file.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_ulonglong)]
        self._lib.bms_jsonl_verify_file.restype = ctypes.c_int
        self._lib.bms_wal_append_pending.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._lib.bms_wal_append_pending.restype = ctypes.c_int
        self._lib.bms_wal_append_committed.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._lib.bms_wal_append_committed.restype = ctypes.c_int
        self._lib.bms_wal_inspect_startup.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.bms_wal_inspect_startup.restype = ctypes.c_int
        self._lib.bms_wal_recover_startup.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        self._lib.bms_wal_recover_startup.restype = ctypes.c_int


def find_core_library() -> Path:
    root = Path(__file__).resolve().parents[2]
    names = {
        "linux": ("libbms_core_python.so", "libbms_core.so"),
        "darwin": ("libbms_core_python.dylib", "libbms_core.dylib"),
        "win32": ("bms_core_python.dll", "libbms_core_python.dll", "bms_core.dll", "libbms_core.dll"),
    }.get(sys.platform, ("libbms_core_python.so",))
    search_roots = [root / "build" / "verify", root / "build-ninja", root / "build", root]
    for search_root in search_roots:
        for name in names:
            candidate = search_root / name
            if candidate.exists():
                return candidate
    expected = ", ".join(str(search_root / name) for search_root in search_roots for name in names)
    raise FileNotFoundError(f"C core shared library not found. Build with cmake first. Looked for: {expected}")
