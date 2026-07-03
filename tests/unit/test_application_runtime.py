from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import ApplicationRuntimeError, StartupState, start_application
from bms.app.use_cases import CreateInvoiceUseCase, CreateRefundUseCase
from bms.app.bootstrap import initialize_data_root


class ApplicationRuntimeTests(unittest.TestCase):
    def test_start_application_constructs_services_when_storage_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = start_application(Path(temp_dir))

            self.assertEqual(runtime.startup_health.state, StartupState.HEALTHY)
            self.assertIs(runtime.billing.inventory, runtime.inventory)
            self.assertIs(runtime.billing.accounting, runtime.accounting)
            self.assertIsInstance(runtime.create_invoice, CreateInvoiceUseCase)
            self.assertIsInstance(runtime.create_refund, CreateRefundUseCase)
            self.assertIs(runtime.create_invoice.billing, runtime.billing)
            self.assertIs(runtime.create_refund.billing, runtime.billing)

    def test_start_application_refuses_recovery_required_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_pending_runtime",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_pending_runtime",
                {"operation": "unit.pending"},
            )

            with self.assertRaisesRegex(ApplicationRuntimeError, "recovery_required"):
                start_application(root)

    def test_start_application_refuses_protected_mode_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.wal.write_text(
                '{"schema_version":1,"sequence":1,"record_id":"wal_bad","record_type":"wal.transaction","created_at":"2026-05-14T00:00:00Z","actor_id":"usr_test","correlation_id":"corr_bad","idempotency_key":"wal_bad","payload":{"transaction_id":"txn_bad","state":"pending","payload":{}},"checksum":"sha256:bad"}\n',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ApplicationRuntimeError, "protected_mode"):
                start_application(root)


if __name__ == "__main__":
    unittest.main()
