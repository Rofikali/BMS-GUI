from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import (
    ApplicationRecoveryError,
    StartupState,
    export_application_recovery_diagnostics,
    export_application_recovery_report,
    inspect_application_recovery,
    reconcile_recovery_transaction,
    recover_application_storage,
    resolve_recovery_accounting_adjustment,
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

    def test_inspect_application_recovery_reports_safe_pending_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_pending_safe",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_pending_safe",
                {"operation": "unit.pending"},
            )

            diagnostics = inspect_application_recovery(root)

            self.assertEqual(diagnostics.startup_health.state, StartupState.RECOVERY_REQUIRED)
            self.assertTrue(diagnostics.automatic_recovery_safe)
            self.assertEqual(len(diagnostics.pending_transactions), 1)
            self.assertEqual(diagnostics.pending_transactions[0].transaction_id, "txn_pending_safe")
            self.assertEqual(diagnostics.pending_transactions[0].operation, "unit.pending")
            self.assertEqual(diagnostics.pending_transactions[0].correlation_id, "corr_pending_safe")
            self.assertEqual(diagnostics.pending_transactions[0].side_effects, ())

    def test_export_application_recovery_diagnostics_returns_json_safe_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_pending_export",
                "2026-05-14T00:00:00Z",
                "usr_test",
                "corr_pending_export",
                {"operation": "unit.pending"},
            )

            exported = export_application_recovery_diagnostics(root)

            self.assertEqual(exported["startup_health"]["state"], "recovery_required")
            self.assertTrue(exported["automatic_recovery_safe"])
            self.assertEqual(exported["pending_transactions"][0]["transaction_id"], "txn_pending_export")
            self.assertEqual(exported["pending_transactions"][0]["operation"], "unit.pending")
            self.assertEqual(exported["pending_transactions"][0]["side_effects"], [])

    def test_inspect_application_recovery_reports_manual_reconciliation_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.core.append_wal_pending(
                store.wal,
                "txn_invoice_partial",
                "2026-05-14T00:00:00Z",
                "usr_cashier",
                "corr_invoice_partial",
                {
                    "operation": "billing.create_invoice",
                    "invoice_id": "INV-PARTIAL",
                    "journal_id": "jrn_INV-PARTIAL",
                    "movement_ids": ["mov_INV-PARTIAL_1"],
                },
            )
            store.append_record(
                store.journal_entries,
                "accounting.journal_entry",
                "usr_cashier",
                "corr_invoice_partial",
                "journal_entry_jrn_INV-PARTIAL",
                {
                    "journal_id": "jrn_INV-PARTIAL",
                    "period_id": "FY2026-05",
                    "debit_total_minor": 118000,
                    "credit_total_minor": 118000,
                    "currency": "INR",
                },
                record_id="jrn_jrn_INV-PARTIAL",
                created_at="2026-05-14T00:00:00Z",
            )

            diagnostics = inspect_application_recovery(root)

            self.assertFalse(diagnostics.automatic_recovery_safe)
            self.assertEqual(len(diagnostics.pending_transactions), 1)
            transaction = diagnostics.pending_transactions[0]
            self.assertEqual(transaction.transaction_id, "txn_invoice_partial")
            self.assertEqual(transaction.operation, "billing.create_invoice")
            self.assertEqual(transaction.correlation_id, "corr_invoice_partial")
            self.assertEqual(transaction.side_effects, ("journal entry exists",))
            with self.assertRaisesRegex(ApplicationRecoveryError, "journal entry exists"):
                recover_application_storage(root)

    def test_inspect_application_recovery_reports_partial_refund_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_refund_wal_and_journal(store, transaction_id="txn_refund_partial")

            diagnostics = inspect_application_recovery(root)

            self.assertFalse(diagnostics.automatic_recovery_safe)
            self.assertEqual(len(diagnostics.pending_transactions), 1)
            transaction = diagnostics.pending_transactions[0]
            self.assertEqual(transaction.transaction_id, "txn_refund_partial")
            self.assertEqual(transaction.operation, "billing.create_refund")
            self.assertEqual(transaction.correlation_id, "corr_txn_refund_partial")
            self.assertEqual(transaction.side_effects, ("journal entry exists",))
            with self.assertRaisesRegex(ApplicationRecoveryError, "journal entry exists"):
                recover_application_storage(root)

    def test_reconcile_recovery_transaction_records_audit_event_and_resolves_allowed_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_reconcile_resolve")

            result = reconcile_recovery_transaction(
                root,
                transaction_id="txn_reconcile_resolve",
                decision="accepted_existing_records",
                actor_id="usr_admin",
                reason="support accepted posted journal as source of truth",
                created_at="2026-05-14T03:00:00Z",
            )
            diagnostics = inspect_application_recovery(root)
            runtime = start_application(root)

            self.assertEqual(result.reconciliation_id, "rec_txn_reconcile_resolve")
            self.assertTrue(result.resolved)
            self.assertEqual(diagnostics.pending_transactions, ())
            self.assertEqual(runtime.startup_health.state, StartupState.HEALTHY)
            self.assertEqual(store.core.verify_file(store.reconciliation_records), 1)
            audit_actions = [payload["action"] for payload in store.read_payloads(store.audit_records)]
            event_types = [payload["event_type"] for payload in store.read_payloads(store.business_events)]
            self.assertIn("recovery.reconciliation_recorded", audit_actions)
            self.assertIn("recovery.reconciliation_recorded.v1", event_types)

    def test_reconcile_recovery_transaction_non_resolving_decision_keeps_startup_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_reconcile_adjust")

            result = reconcile_recovery_transaction(
                root,
                transaction_id="txn_reconcile_adjust",
                decision="requires_accounting_adjustment",
                actor_id="usr_admin",
                reason="journal exists without completed invoice",
                created_at="2026-05-14T03:00:00Z",
            )
            diagnostics = inspect_application_recovery(root)

            self.assertFalse(result.resolved)
            self.assertEqual(len(diagnostics.pending_transactions), 1)
            with self.assertRaisesRegex(Exception, "recovery_required"):
                start_application(root)

    def test_resolve_recovery_accounting_adjustment_posts_correction_and_unblocks_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_reconcile_adjust_resolve")
            reconcile_recovery_transaction(
                root,
                transaction_id="txn_reconcile_adjust_resolve",
                decision="requires_accounting_adjustment",
                actor_id="usr_admin",
                reason="journal exists without completed invoice",
                created_at="2026-05-14T03:00:00Z",
            )

            result = resolve_recovery_accounting_adjustment(
                root,
                transaction_id="txn_reconcile_adjust_resolve",
                actor_id="usr_admin",
                reason="posted correction journal",
                journal_payload=_correction_journal_payload("txn_reconcile_adjust_resolve"),
                created_at="2026-05-14T03:05:00Z",
            )
            diagnostics = inspect_application_recovery(root)
            runtime = start_application(root)

            self.assertTrue(result.resolved)
            self.assertEqual(result.correction_journal_id, "JRN-REC-txn_reconcile_adjust_resolve")
            self.assertEqual(diagnostics.pending_transactions, ())
            self.assertEqual(runtime.startup_health.state, StartupState.HEALTHY)
            self.assertEqual(store.core.verify_file(store.reconciliation_records), 2)
            journal_ids = [payload["journal_id"] for payload in store.read_payloads(store.journal_entries)]
            self.assertIn("JRN-REC-txn_reconcile_adjust_resolve", journal_ids)
            event_payloads = store.read_payloads(store.business_events)
            self.assertIn(
                "JRN-REC-txn_reconcile_adjust_resolve",
                [
                    payload.get("correction_journal_id")
                    for payload in event_payloads
                    if payload.get("event_type") == "recovery.reconciliation_recorded.v1"
                ],
            )

    def test_export_application_recovery_report_tracks_recommendation_and_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_report_adjust")

            initial_report = export_application_recovery_report(root)
            self.assertFalse(initial_report["normal_startup_allowed"])
            self.assertEqual(initial_report["recommended_next_action"], "run_bms_recovery_reconcile")
            self.assertEqual(initial_report["pending_transactions"][0]["transaction_id"], "txn_report_adjust")

            reconcile_recovery_transaction(
                root,
                transaction_id="txn_report_adjust",
                decision="requires_accounting_adjustment",
                actor_id="usr_admin",
                reason="journal exists without completed invoice",
                created_at="2026-05-14T03:00:00Z",
            )
            adjustment_report = export_application_recovery_report(root)
            self.assertEqual(
                adjustment_report["recommended_next_action"],
                "run_bms_recovery_resolve_accounting_adjustment",
            )
            self.assertEqual(len(adjustment_report["reconciliation_records"]), 1)
            self.assertEqual(adjustment_report["audit_references"][0]["action"], "recovery.reconciliation_recorded")

            resolve_recovery_accounting_adjustment(
                root,
                transaction_id="txn_report_adjust",
                actor_id="usr_admin",
                reason="posted correction journal",
                journal_payload=_correction_journal_payload("txn_report_adjust"),
                created_at="2026-05-14T03:05:00Z",
            )
            resolved_report = export_application_recovery_report(root)
            self.assertTrue(resolved_report["normal_startup_allowed"])
            self.assertEqual(resolved_report["recommended_next_action"], "normal_startup_allowed")
            self.assertEqual(resolved_report["pending_transactions"], [])
            self.assertEqual(resolved_report["correction_journals"][0]["journal_id"], "JRN-REC-txn_report_adjust")
            self.assertIn(
                "recovery.accounting_adjustment_resolved",
                [payload["action"] for payload in resolved_report["audit_references"]],
            )

    def test_resolve_recovery_accounting_adjustment_requires_prior_adjustment_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_reconcile_no_prior")

            with self.assertRaisesRegex(ApplicationRecoveryError, "no reconciliation record"):
                resolve_recovery_accounting_adjustment(
                    root,
                    transaction_id="txn_reconcile_no_prior",
                    actor_id="usr_admin",
                    reason="posted correction journal",
                    journal_payload=_correction_journal_payload("txn_reconcile_no_prior"),
                    created_at="2026-05-14T03:05:00Z",
                )

    def test_reconcile_recovery_transaction_rejects_duplicate_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            _append_partial_invoice_wal_and_journal(store, transaction_id="txn_reconcile_duplicate")
            reconcile_recovery_transaction(
                root,
                transaction_id="txn_reconcile_duplicate",
                decision="requires_accounting_adjustment",
                actor_id="usr_admin",
                reason="first decision",
                created_at="2026-05-14T03:00:00Z",
            )

            with self.assertRaisesRegex(ApplicationRecoveryError, "already reconciled"):
                reconcile_recovery_transaction(
                    root,
                    transaction_id="txn_reconcile_duplicate",
                    decision="accepted_existing_records",
                    actor_id="usr_admin",
                    reason="second decision",
                    created_at="2026-05-14T03:05:00Z",
                )

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
            "movement_ids": [f"mov_INV-{transaction_id}_1"],
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


def _append_partial_refund_wal_and_journal(store: object, *, transaction_id: str) -> None:
    store.core.append_wal_pending(
        store.wal,
        transaction_id,
        "2026-05-14T00:00:00Z",
        "usr_cashier",
        f"corr_{transaction_id}",
        {
            "operation": "billing.create_refund",
            "refund_id": f"REF-{transaction_id}",
            "original_invoice_id": f"INV-{transaction_id}",
            "journal_id": f"jrn_refund_REF-{transaction_id}",
            "movement_ids": [f"mov_refund_REF-{transaction_id}_1"],
        },
    )
    store.append_record(
        store.journal_entries,
        "accounting.journal_entry",
        "usr_cashier",
        f"corr_{transaction_id}",
        f"journal_entry_jrn_refund_REF-{transaction_id}",
        {
            "journal_id": f"jrn_refund_REF-{transaction_id}",
            "period_id": "FY2026-05",
            "debit_total_minor": 59000,
            "credit_total_minor": 59000,
            "currency": "INR",
        },
        record_id=f"jrn_jrn_refund_REF-{transaction_id}",
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
