from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from pydantic import ValidationError

from bms.app.bootstrap import initialize_data_root
from bms.services.backup_schemas import BackupManifestSchema
from bms.storage.file_store.core_store import CoreFileStore


class BackupError(ValueError):
    pass


LIVE_RESTORE_UNSUPPORTED_MESSAGE = (
    "restore over live data is not supported; restore into a clean target and "
    "validate the restored reports before replacing a live data root"
)


@dataclass(frozen=True)
class BackupResult:
    backup_path: Path
    created_at: str
    verified_record_counts: dict[str, int]


@dataclass(frozen=True)
class RestoreResult:
    restored_root: Path
    verified_record_counts: dict[str, int]


class BackupService:
    def __init__(self, store: CoreFileStore) -> None:
        self.store = store

    def create_backup(self, backup_dir: Path | None = None, *, created_at: str | None = None) -> BackupResult:
        created_at = created_at or _utc_now()
        backup_dir = backup_dir or self.store.data_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        verified_record_counts = self.validate_data_root(self.store.data_root)
        backup_path = backup_dir / f"bms-backup-{_safe_timestamp(created_at)}.tar.gz"
        if backup_path.exists():
            raise BackupError(f"backup already exists: {backup_path}")
        manifest = BackupManifestSchema(
            created_at=created_at,
            verified_record_counts=verified_record_counts,
        )

        with tarfile.open(backup_path, "w:gz") as archive:
            manifest_bytes = manifest.model_dump_json().encode("utf-8")
            manifest_info = tarfile.TarInfo("backup_manifest.json")
            manifest_info.size = len(manifest_bytes)
            manifest_info.mtime = int(datetime.now(UTC).timestamp())
            archive.addfile(manifest_info, BytesIO(manifest_bytes))
            for path in sorted(self.store.data_root.rglob("*")):
                if path == backup_path or _is_excluded_from_backup(self.store.data_root, path):
                    continue
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(self.store.data_root)))

        return BackupResult(backup_path=backup_path, created_at=created_at, verified_record_counts=verified_record_counts)

    @staticmethod
    def restore_backup(backup_path: Path, restored_root: Path) -> RestoreResult:
        if restored_root.exists() and any(restored_root.iterdir()):
            raise BackupError(f"restore target {restored_root} is not empty")
        restored_root.mkdir(parents=True, exist_ok=True)
        restored_root_resolved = restored_root.resolve()

        with tarfile.open(backup_path, "r:gz") as archive:
            members = archive.getmembers()
            manifest_members = [member for member in members if member.name == "backup_manifest.json" and member.isfile()]
            if len(manifest_members) != 1:
                raise BackupError("backup manifest is missing or ambiguous")
            manifest_file = archive.extractfile(manifest_members[0])
            if manifest_file is None:
                raise BackupError("backup manifest cannot be read")
            try:
                manifest = BackupManifestSchema.model_validate_json(manifest_file.read().decode("utf-8"))
            except (ValidationError, json.JSONDecodeError) as exc:
                raise BackupError("backup manifest is invalid") from exc

            for member in members:
                if not member.isfile() and not member.isdir():
                    raise BackupError(f"backup member has unsafe type: {member.name}")
                target = (restored_root / member.name).resolve()
                if not target.is_relative_to(restored_root_resolved):
                    raise BackupError(f"backup member escapes restore root: {member.name}")
            archive.extractall(restored_root)

        verified_record_counts = BackupService.validate_data_root(restored_root)
        if verified_record_counts != manifest.verified_record_counts:
            raise BackupError("restored record counts do not match backup manifest")

        return RestoreResult(
            restored_root=restored_root,
            verified_record_counts=verified_record_counts,
        )

    @staticmethod
    def restore_over_live_data(backup_path: Path, live_root: Path) -> RestoreResult:
        raise BackupError(LIVE_RESTORE_UNSUPPORTED_MESSAGE)

    @staticmethod
    def validate_data_root(data_root: Path) -> dict[str, int]:
        store = initialize_data_root(data_root)
        counts: dict[str, int] = {}
        for name in _DURABLE_FILE_ATTRIBUTES:
            path = getattr(store, name)
            if path.exists():
                counts[name] = store.core.verify_file(path)
        return dict(sorted(counts.items()))


_DURABLE_FILE_ATTRIBUTES = (
    "wal",
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


def _is_excluded_from_backup(data_root: Path, path: Path) -> bool:
    relative_parts = path.relative_to(data_root).parts
    return bool(relative_parts and relative_parts[0] in {"backups", "temp"})


def _safe_timestamp(timestamp: str) -> str:
    return timestamp.replace(":", "").replace("-", "").replace(".", "").replace("Z", "z")


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
