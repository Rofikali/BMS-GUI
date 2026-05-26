from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import StartupHealthService, StartupState
from bms.app.bootstrap import initialize_data_root
from bms.core import BMS_ERR_PROTECTED_MODE, BMS_ERR_RECOVERY_REQUIRED, BMS_OK


class StartupHealthServiceTests(unittest.TestCase):
    def test_clean_wal_reports_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))
            store.wal_smoke_commit("usr_test")

            health = StartupHealthService(store).inspect()

            self.assertEqual(health.state, StartupState.HEALTHY)
            self.assertEqual(health.wal_status, BMS_OK)

    def test_uncommitted_pending_wal_reports_recovery_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))
            store.core.append_wal_pending(
                store.wal,
                "txn_pending_startup",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_pending_startup",
                {"operation": "unit.pending"},
            )

            health = StartupHealthService(store).inspect()

            self.assertEqual(health.state, StartupState.RECOVERY_REQUIRED)
            self.assertEqual(health.wal_status, BMS_ERR_RECOVERY_REQUIRED)

    def test_corrupt_wal_reports_protected_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))
            store.wal.write_text(
                '{"schema_version":1,"sequence":1,"record_id":"wal_bad","record_type":"wal.transaction","created_at":"2026-05-14T00:00:00Z","actor_id":"usr_test","correlation_id":"corr_bad","idempotency_key":"wal_bad","payload":{"transaction_id":"txn_bad","state":"pending","payload":{}},"checksum":"sha256:bad"}\n',
                encoding="utf-8",
            )

            health = StartupHealthService(store).inspect()

            self.assertEqual(health.state, StartupState.PROTECTED_MODE)
            self.assertEqual(health.wal_status, BMS_ERR_PROTECTED_MODE)


if __name__ == "__main__":
    unittest.main()
