from __future__ import annotations

import tempfile
from pathlib import Path

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
    return CoreFileStore(data_root)


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
