from __future__ import annotations

import tempfile
from pathlib import Path

from bms.app.auth import default_identity_documents
from bms.storage.file_store.core_store import CoreFileStore


DATA_DIRECTORIES = (
    "wal/archive",
    "events",
    "accounting/snapshots",
    "inventory/snapshots",
    "billing/snapshots",
    "audit",
    "users",
    "tax",
    "reports/generated",
    "backups",
    "temp",
)


def initialize_data_root(data_root: Path) -> CoreFileStore:
    for directory in DATA_DIRECTORIES:
        (data_root / directory).mkdir(parents=True, exist_ok=True)
    _initialize_identity_files(data_root)
    return CoreFileStore(data_root)


def _initialize_identity_files(data_root: Path) -> None:
    users_json, roles_json = default_identity_documents()
    users_path = data_root / "users" / "users.json"
    roles_path = data_root / "users" / "roles.json"
    if not users_path.exists():
        users_path.write_text(users_json, encoding="utf-8")
    if not roles_path.exists():
        roles_path.write_text(roles_json, encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="bms-core-smoke-") as temp_dir:
        store = initialize_data_root(Path(temp_dir))
        store.wal_smoke_commit()
        sequence = store.append_business_event(
            "audit.record_created.v1",
            "usr_admin",
            {
                "action": "system.bootstrap",
                "target_type": "system",
                "target_id": "local",
            },
        )
        count = store.verify_business_events()
        print(
            f"BMS core smoke passed: appended sequence {sequence}; verified {count} business event(s)."
        )


if __name__ == "__main__":
    main()
