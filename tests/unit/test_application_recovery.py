from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import (
    ApplicationRecoveryError,
    StartupState,
    recover_application_storage,
    start_application,
)
from bms.app.bootstrap import initialize_data_root
from bms.core import BMS_WAL_RECOVERY_PENDING_ROLLBACK


class ApplicationRecoveryTests(unittest.TestCase):
    def test_recover_application_storage_rolls_back_uncommitted_pending_wal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_pending_recovery",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_pending_recovery",
                {"operation": "unit.pending"},
            )

            recovery = recover_application_storage(root)
            runtime = start_application(root)

            self.assertEqual(recovery.before.state, StartupState.RECOVERY_REQUIRED)
            self.assertEqual(recovery.recovery.decision, BMS_WAL_RECOVERY_PENDING_ROLLBACK)
            self.assertEqual(recovery.after.state, StartupState.HEALTHY)
            self.assertEqual(runtime.startup_health.state, StartupState.HEALTHY)
            self.assertEqual(runtime.store.core.verify_file(runtime.store.wal), 0)

    def test_recover_application_storage_refuses_protected_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.wal.write_text(
                '{"schema_version":1,"sequence":1,"record_id":"wal_bad","record_type":"wal.transaction","created_at":"2026-05-14T00:00:00Z","actor_id":"usr_test","correlation_id":"corr_bad","idempotency_key":"wal_bad","payload":{"transaction_id":"txn_bad","state":"pending","payload":{}},"checksum":"sha256:bad"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ApplicationRecoveryError, "protected"):
                recover_application_storage(root)


if __name__ == "__main__":
    unittest.main()
