from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.core import BMS_OK, BMS_WAL_RECOVERY_CLEAN, BMS_WAL_RECOVERY_PENDING_ROLLBACK


class CoreFileStoreTests(unittest.TestCase):
    def test_core_file_store_appends_and_verifies_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)

            sequence = store.append_business_event(
                "audit.record_created.v1",
                "usr_test",
                {"action": "test.event", "target_type": "test", "target_id": "unit"},
            )

            self.assertEqual(sequence, 1)
            self.assertEqual(store.verify_business_events(), 1)

    def test_core_file_store_wal_smoke_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)

            store.wal_smoke_commit("usr_test")

            self.assertEqual(store.core.verify_file(root / "wal" / "current.wal.jsonl"), 2)

    def test_core_file_store_recovers_uncommitted_wal_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)

            store.core.append_wal_pending(
                store.wal,
                "txn_recover_python",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_recover_python",
                {"operation": "unit.recover"},
            )

            recovery = store.recover_wal_startup()
            self.assertEqual(recovery.status, BMS_OK)
            self.assertEqual(recovery.decision, BMS_WAL_RECOVERY_PENDING_ROLLBACK)
            self.assertEqual(store.core.verify_file(store.wal), 0)

            inspection = store.inspect_wal_startup()
            self.assertEqual(inspection.status, BMS_OK)
            self.assertEqual(inspection.decision, BMS_WAL_RECOVERY_CLEAN)


if __name__ == "__main__":
    unittest.main()
