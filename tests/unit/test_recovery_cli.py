from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.app.recovery_cli import main


class RecoveryCliTests(unittest.TestCase):
    def test_inspect_reports_safe_pending_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_cli_safe",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_cli_safe",
                {"operation": "unit.pending"},
            )

            code, stdout, stderr = _run_cli("inspect", "--data-root", str(root))
            payload = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["automatic_recovery_safe"])
            self.assertEqual(payload["startup_health"]["state"], "recovery_required")
            self.assertEqual(payload["pending_transactions"][0]["transaction_id"], "txn_cli_safe")

    def test_recover_rolls_back_safe_pending_wal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_cli_recover",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_cli_recover",
                {"operation": "unit.pending"},
            )

            code, stdout, stderr = _run_cli("recover", "--data-root", str(root))
            payload = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["before"]["state"], "recovery_required")
            self.assertEqual(payload["after"]["state"], "healthy")
            self.assertEqual(store.core.verify_file(store.wal), 0)

    def test_recover_refuses_manual_reconciliation_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_cli_partial")

            code, stdout, stderr = _run_cli("recover", "--data-root", str(root))
            payload = json.loads(stderr)

            self.assertEqual(code, 4)
            self.assertEqual(stdout, "")
            self.assertFalse(payload["ok"])
            self.assertIn("manual reconciliation", payload["error"])
            self.assertFalse(payload["diagnostics"]["automatic_recovery_safe"])
            self.assertEqual(
                payload["diagnostics"]["pending_transactions"][0]["side_effects"],
                ["journal entry exists"],
            )

    def test_reconcile_records_resolving_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_cli_reconcile")

            code, stdout, stderr = _run_cli(
                "reconcile",
                "--data-root",
                str(root),
                "--transaction-id",
                "txn_cli_reconcile",
                "--decision",
                "accepted_existing_records",
                "--actor-id",
                "usr_admin",
                "--reason",
                "support accepted existing records",
            )
            payload = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["resolved"])
            self.assertEqual(payload["transaction_id"], "txn_cli_reconcile")
            self.assertEqual(store.core.verify_file(store.reconciliation_records), 1)

    def test_reconcile_rejects_unauthorized_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_cli_unauthorized")

            code, stdout, stderr = _run_cli(
                "reconcile",
                "--data-root",
                str(root),
                "--transaction-id",
                "txn_cli_unauthorized",
                "--decision",
                "accepted_existing_records",
                "--actor-id",
                "usr_cashier",
                "--reason",
                "cashier should not reconcile recovery",
            )
            payload = json.loads(stderr)

            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error_type"], "AuthorizationError")

    def test_resolve_accounting_adjustment_posts_correction_and_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_cli_adjustment")
            reconcile_code, _stdout, _stderr = _run_cli(
                "reconcile",
                "--data-root",
                str(root),
                "--transaction-id",
                "txn_cli_adjustment",
                "--decision",
                "requires_accounting_adjustment",
                "--actor-id",
                "usr_admin",
                "--reason",
                "needs correction journal",
            )
            self.assertEqual(reconcile_code, 0)

            code, stdout, stderr = _run_cli(
                "resolve-accounting-adjustment",
                "--data-root",
                str(root),
                "--transaction-id",
                "txn_cli_adjustment",
                "--actor-id",
                "usr_admin",
                "--reason",
                "posted correction journal",
                "--journal-json",
                json.dumps(_correction_journal_payload("txn_cli_adjustment")),
            )
            payload = json.loads(stdout)

            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["resolved"])
            self.assertEqual(payload["correction_journal_id"], "JRN-REC-txn_cli_adjustment")
            self.assertEqual(store.core.verify_file(store.reconciliation_records), 2)

    def test_report_exports_support_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_cli_report")

            code, stdout, stderr = _run_cli("report", "--data-root", str(root))
            payload = json.loads(stdout)

            self.assertEqual(code, 4)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["recommended_next_action"], "run_bms_recovery_reconcile")
            self.assertEqual(payload["pending_transactions"][0]["transaction_id"], "txn_cli_report")
            self.assertEqual(payload["reconciliation_records"], [])

    def test_inspect_reports_protected_mode_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.wal.write_text(
                '{"schema_version":1,"sequence":1,"record_id":"wal_bad","record_type":"wal.transaction","created_at":"2026-05-14T00:00:00Z","actor_id":"usr_test","correlation_id":"corr_bad","idempotency_key":"wal_bad","payload":{"transaction_id":"txn_bad","state":"pending","payload":{}},"checksum":"sha256:bad"}\n',
                encoding="utf-8",
            )

            code, stdout, stderr = _run_cli("inspect", "--data-root", str(root))
            payload = json.loads(stdout)

            self.assertEqual(code, 3)
            self.assertEqual(stderr, "")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["startup_health"]["state"], "protected_mode")


def _run_cli(*args: str) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(args)
    return code, stdout.getvalue(), stderr.getvalue()


def _append_partial_invoice_wal_and_journal(store: object, *, transaction_id: str) -> None:
    store.core.append_wal_pending(
        store.wal,
        transaction_id,
        "2026-05-14T00:00:00Z",
        "usr_cashier",
        f"corr_{transaction_id}",
        {
            "operation": "billing.create_invoice",
            "invoice_id": f"INV-{transaction_id}",
            "journal_id": f"jrn_INV-{transaction_id}",
            "movement_ids": [],
        },
    )
    store.append_record(
        store.journal_entries,
        "accounting.journal_entry",
        "usr_cashier",
        f"corr_{transaction_id}",
        f"journal_entry_jrn_INV-{transaction_id}",
        {
            "journal_id": f"jrn_INV-{transaction_id}",
            "period_id": "FY2026-05",
            "debit_total_minor": 118000,
            "credit_total_minor": 118000,
            "currency": "INR",
        },
        record_id=f"jrn_jrn_INV-{transaction_id}",
        created_at="2026-05-14T00:00:00Z",
    )


def _correction_journal_payload(transaction_id: str) -> dict[str, object]:
    return {
        "journal_id": f"JRN-REC-{transaction_id}",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T03:05:00Z",
        "actor_id": "usr_admin",
        "source_module": "recovery",
        "source_document_id": transaction_id,
        "correlation_id": f"corr_{transaction_id}",
        "description": "Recovery accounting adjustment",
        "lines": [
            {"account_code": "4000", "debit_minor": 100000, "currency": "INR"},
            {"account_code": "2100", "debit_minor": 18000, "currency": "INR"},
            {"account_code": "1000", "credit_minor": 118000, "currency": "INR"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
