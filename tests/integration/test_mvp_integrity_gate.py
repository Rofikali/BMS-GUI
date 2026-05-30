from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import StartupHealthService, StartupState, start_command_facade
from bms.app.bootstrap import initialize_data_root
from bms.core import BMS_OK, BMS_WAL_RECOVERY_CLEAN
from bms.domain.accounting import AccountingError, AccountingService, JournalLine, PostJournalCommand
from bms.domain.billing import (
    BillingError,
    BillingService,
    CreateInvoiceCommand,
    CreateRefundCommand,
    InvoiceLineCommand,
    RefundLineCommand,
)
from bms.domain.inventory import InventoryService, Item
from bms.domain.reporting import ReportingService
from bms.services import BackupService


class MvpIntegrityGateTests(unittest.TestCase):
    def test_invoice_lifecycle_survives_restart_with_verified_durable_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            store, billing, inventory, accounting = _services(root)

            inventory.register_item(
                Item("ITEM-1", "SKU-1", "Test Item"),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_ITEM-1",
            )
            inventory.adjust_stock(
                movement_id="MOV-STOCK-IN",
                item_id="ITEM-1",
                quantity_delta=5,
                timestamp="2026-05-14T00:05:00Z",
                actor_id="usr_inventory",
                reason="opening stock",
                source_document_id="STK-1001",
                correlation_id="corr_stock_in",
            )

            result = billing.create_invoice(_invoice())

            self.assertEqual(result.subtotal_minor, 100000)
            self.assertEqual(result.tax_minor, 18000)
            self.assertEqual(result.total_minor, 118000)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertTrue(accounting.get_trial_balance("FY2026-05").is_balanced)
            _assert_verified_counts(
                self,
                store,
                {
                    "items": 1,
                    "stock_movements": 2,
                    "invoices": 1,
                    "invoice_lines": 1,
                    "journal_entries": 1,
                    "journal_lines": 3,
                    "audit_records": 5,
                    "business_events": 5,
                    "wal": 10,
                },
            )

            restarted_store, _billing, restarted_inventory, restarted_accounting = _services(root)
            startup_health = StartupHealthService(restarted_store).inspect()
            wal_startup = restarted_store.inspect_wal_startup()
            invoices = restarted_store.read_payloads(restarted_store.invoices)
            audit_actions = [payload["action"] for payload in restarted_store.read_payloads(restarted_store.audit_records)]
            event_types = [payload["event_type"] for payload in restarted_store.read_payloads(restarted_store.business_events)]
            balances = restarted_accounting.get_ledger_balances("FY2026-05")
            reports = ReportingService(restarted_store)
            invoice_report = reports.get_invoice_report("FY2026-05")
            stock_report = reports.get_stock_report(low_stock_threshold=3)
            tax_report = reports.get_tax_report("FY2026-05")
            trial_balance_report = reports.get_trial_balance_report("FY2026-05")

            self.assertEqual(startup_health.state, StartupState.HEALTHY)
            self.assertEqual(wal_startup.status, BMS_OK)
            self.assertEqual(wal_startup.decision, BMS_WAL_RECOVERY_CLEAN)
            self.assertEqual(invoices[0]["invoice_id"], "INV-1001")
            self.assertEqual(invoices[0]["total_minor"], 118000)
            self.assertEqual(restarted_inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertTrue(restarted_accounting.get_trial_balance("FY2026-05").is_balanced)
            self.assertEqual(balances["1000"].balance_minor, 118000)
            self.assertEqual(balances["4000"].balance_minor, 100000)
            self.assertEqual(balances["2100"].balance_minor, 18000)
            self.assertIn("inventory.item_registered", audit_actions)
            self.assertIn("inventory.stock_moved", audit_actions)
            self.assertIn("accounting.journal_posted", audit_actions)
            self.assertIn("billing.invoice_created", audit_actions)
            self.assertIn("inventory.item_registered.v1", event_types)
            self.assertIn("inventory.stock_moved.v1", event_types)
            self.assertIn("accounting.journal_posted.v1", event_types)
            self.assertIn("billing.sale_completed.v1", event_types)
            self.assertEqual(invoice_report.rows[0].invoice_id, "INV-1001")
            self.assertEqual(invoice_report.totals[0].total_minor, 118000)
            self.assertEqual(stock_report.rows[0].quantity_on_hand, 3)
            self.assertTrue(stock_report.rows[0].low_stock)
            self.assertEqual(tax_report.invoice_tax_collected_minor, 18000)
            self.assertEqual(tax_report.tax_payable_balance_minor, 18000)
            self.assertTrue(trial_balance_report.is_balanced)

            backup = BackupService(restarted_store).create_backup(created_at="2026-05-14T03:00:00Z")
            restore = BackupService.restore_backup(backup.backup_path, restore_root)
            restored_reports = ReportingService(initialize_data_root(restore_root))

            self.assertEqual(restore.verified_record_counts, backup.verified_record_counts)
            self.assertEqual(restored_reports.get_invoice_report("FY2026-05").totals[0].total_minor, 118000)
            self.assertEqual(restored_reports.get_stock_report().rows[0].quantity_on_hand, 3)
            self.assertTrue(restored_reports.get_trial_balance_report("FY2026-05").is_balanced)

    def test_application_facade_runs_invoice_lifecycle_from_raw_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            facade = start_command_facade(root)

            facade.register_item(_register_item_payload())
            facade.commit_stock_movement(_stock_movement_payload("MOV-FACADE-GATE-IN", 5, "adjustment"))
            invoice = facade.create_invoice(_facade_invoice_payload())

            restarted = start_command_facade(root)
            invoice_report = restarted.invoice_report("FY2026-05")
            stock_report = restarted.stock_report(low_stock_threshold=3)
            tax_report = restarted.tax_report("FY2026-05")
            trial_balance = restarted.trial_balance_report("FY2026-05")
            backup = restarted.create_backup(_backup_payload())
            restore = BackupService.restore_backup(Path(backup["backup_path"]), restore_root)
            restored = start_command_facade(restore_root)

            self.assertEqual(invoice["total_minor"], 118000)
            self.assertEqual(invoice_report["totals"][0]["total_minor"], 118000)
            self.assertEqual(stock_report["rows"][0]["quantity_on_hand"], 3)
            self.assertEqual(tax_report["tax_payable_balance_minor"], 18000)
            self.assertTrue(trial_balance["is_balanced"])
            self.assertEqual(restore.verified_record_counts, backup["verified_record_counts"])
            self.assertEqual(restored.invoice_report("FY2026-05")["totals"][0]["total_minor"], 118000)
            self.assertEqual(restored.stock_report()["rows"][0]["quantity_on_hand"], 3)

    def test_refund_lifecycle_survives_restart_backup_restore_and_over_refund_guard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            store, billing, inventory, accounting = _services(root)

            inventory.register_item(
                Item("ITEM-1", "SKU-1", "Test Item"),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_ITEM-1",
            )
            inventory.adjust_stock(
                movement_id="MOV-REFUND-GATE-IN",
                item_id="ITEM-1",
                quantity_delta=5,
                timestamp="2026-05-14T00:05:00Z",
                actor_id="usr_inventory",
                reason="opening stock",
                source_document_id="STK-1001",
                correlation_id="corr_refund_gate_stock_in",
            )
            invoice = billing.create_invoice(_invoice())
            refund = billing.create_refund(_refund("REF-1001", original_invoice_id=invoice.invoice_id, quantity=1))

            self.assertEqual(refund.total_minor, 59000)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 4)
            self.assertTrue(accounting.get_trial_balance("FY2026-05").is_balanced)

            restarted_store, restarted_billing, restarted_inventory, _restarted_accounting = _services(root)
            restarted_reports = ReportingService(restarted_store)

            self.assertEqual(restarted_reports.get_invoice_report("FY2026-05").totals[0].total_minor, 118000)
            self.assertEqual(restarted_reports.get_refund_report("FY2026-05").totals[0].total_minor, 59000)
            self.assertEqual(restarted_reports.get_tax_report("FY2026-05").tax_payable_balance_minor, 9000)
            self.assertEqual(restarted_inventory.get_stock_on_hand("ITEM-1"), 4)
            with self.assertRaisesRegex(BillingError, "exceeds remaining refundable quantity"):
                restarted_billing.create_refund(_refund("REF-OVER-RESTART", original_invoice_id=invoice.invoice_id, quantity=2))

            backup = BackupService(restarted_store).create_backup(created_at="2026-05-14T05:00:00Z")
            restore = BackupService.restore_backup(backup.backup_path, restore_root)
            restored_store, restored_billing, restored_inventory, _restored_accounting = _services(restore_root)
            restored_reports = ReportingService(restored_store)

            self.assertEqual(restore.verified_record_counts, backup.verified_record_counts)
            self.assertEqual(restored_reports.get_refund_report("FY2026-05").totals[0].total_minor, 59000)
            self.assertEqual(restored_inventory.get_stock_on_hand("ITEM-1"), 4)
            with self.assertRaisesRegex(BillingError, "exceeds remaining refundable quantity"):
                restored_billing.create_refund(_refund("REF-OVER-RESTORED", original_invoice_id=invoice.invoice_id, quantity=2))

    def test_period_close_blocks_mutations_and_survives_backup_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            store, billing, inventory, accounting = _services(root)

            inventory.register_item(
                Item("ITEM-1", "SKU-1", "Test Item"),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_ITEM-1",
            )
            inventory.adjust_stock(
                movement_id="MOV-PERIOD-CLOSE-IN",
                item_id="ITEM-1",
                quantity_delta=5,
                timestamp="2026-05-14T00:05:00Z",
                actor_id="usr_inventory",
                reason="opening stock",
                source_document_id="STK-1001",
                correlation_id="corr_period_close_stock_in",
            )
            billing.create_invoice(_invoice())

            accounting.close_period(
                "FY2026-05",
                actor_id="usr_accountant",
                closed_at="2026-05-14T04:00:00Z",
                correlation_id="corr_close_FY2026_05",
            )

            reports = ReportingService(store)
            self.assertEqual(reports.get_invoice_report("FY2026-05").totals[0].total_minor, 118000)
            self.assertTrue(reports.get_trial_balance_report("FY2026-05").is_balanced)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)
            with self.assertRaisesRegex(BillingError, "closed"):
                billing.create_invoice(_invoice_with_id("INV-CLOSED-PERIOD"))
            with self.assertRaisesRegex(AccountingError, "closed"):
                accounting.post_journal(_manual_journal("JRN-CLOSED-PERIOD"))

            restarted_store, _restarted_billing, _restarted_inventory, restarted_accounting = _services(root)
            with self.assertRaisesRegex(AccountingError, "closed"):
                restarted_accounting.post_journal(_manual_journal("JRN-CLOSED-AFTER-RESTART"))

            backup = BackupService(restarted_store).create_backup(created_at="2026-05-14T05:00:00Z")
            restore = BackupService.restore_backup(backup.backup_path, restore_root)
            restored_store, restored_billing, restored_inventory, restored_accounting = _services(restore_root)
            restored_reports = ReportingService(restored_store)

            self.assertEqual(restore.verified_record_counts, backup.verified_record_counts)
            self.assertEqual(restored_store.core.verify_file(restored_store.periods), 1)
            self.assertEqual(restored_reports.get_invoice_report("FY2026-05").totals[0].total_minor, 118000)
            self.assertEqual(restored_inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertTrue(restored_reports.get_trial_balance_report("FY2026-05").is_balanced)
            with self.assertRaisesRegex(BillingError, "closed"):
                restored_billing.create_invoice(_invoice_with_id("INV-CLOSED-RESTORED"))
            with self.assertRaisesRegex(AccountingError, "closed"):
                restored_accounting.post_journal(_manual_journal("JRN-CLOSED-RESTORED"))


def _services(root: Path) -> tuple[object, BillingService, InventoryService, AccountingService]:
    store = initialize_data_root(root)
    inventory = InventoryService(store)
    accounting = AccountingService(store)
    billing = BillingService(store, inventory, accounting)
    return store, billing, inventory, accounting


def _invoice() -> CreateInvoiceCommand:
    return _invoice_with_id("INV-1001")


def _invoice_with_id(invoice_id: str) -> CreateInvoiceCommand:
    return CreateInvoiceCommand(
        invoice_id=invoice_id,
        customer_id="CUS-1",
        period_id="FY2026-05",
        timestamp="2026-05-14T02:00:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{invoice_id}",
        payment_method="cash",
        currency="INR",
        lines=(InvoiceLineCommand("ITEM-1", 2, 50000, "Test Item"),),
    )


def _refund(refund_id: str, *, original_invoice_id: str, quantity: int) -> CreateRefundCommand:
    return CreateRefundCommand(
        refund_id=refund_id,
        original_invoice_id=original_invoice_id,
        period_id="FY2026-05",
        timestamp="2026-05-14T03:00:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{refund_id}",
        currency="INR",
        reason="customer return",
        lines=(RefundLineCommand("ITEM-1", quantity, 50000, "Test Item", restock=True),),
    )


def _manual_journal(journal_id: str) -> PostJournalCommand:
    return PostJournalCommand(
        journal_id=journal_id,
        period_id="FY2026-05",
        timestamp="2026-05-14T04:30:00Z",
        actor_id="usr_accountant",
        source_module="manual",
        source_document_id=journal_id,
        correlation_id=f"corr_{journal_id}",
        description="Manual closed-period mutation attempt",
        lines=(
            JournalLine("1000", debit_minor=1000),
            JournalLine("4000", credit_minor=1000),
        ),
    )


def _assert_verified_counts(
    test_case: unittest.TestCase,
    store: object,
    expected_counts: dict[str, int],
) -> None:
    for attribute_name, expected_count in expected_counts.items():
        path = getattr(store, attribute_name)
        test_case.assertEqual(
            store.core.verify_file(path),
            expected_count,
            f"{attribute_name} should contain {expected_count} verified record(s)",
        )


def _backup_payload() -> dict[str, object]:
    return {
        "actor_id": "usr_admin",
        "created_at": "2026-05-14T03:00:00Z",
    }


def _register_item_payload() -> dict[str, object]:
    return {
        "item": {"item_id": "ITEM-1", "sku": "SKU-1", "name": "Test Item", "active": True},
        "actor_id": "usr_inventory",
        "created_at": "2026-05-14T00:00:00Z",
        "correlation_id": "corr_item_ITEM-1",
    }


def _stock_movement_payload(movement_id: str, quantity_delta: int, movement_type: str) -> dict[str, object]:
    return {
        "movement_id": movement_id,
        "item_id": "ITEM-1",
        "movement_type": movement_type,
        "quantity_delta": quantity_delta,
        "timestamp": "2026-05-14T00:05:00Z",
        "actor_id": "usr_inventory",
        "reason": "opening stock",
        "source_module": "inventory",
        "source_document_id": "STK-1001",
        "correlation_id": f"corr_{movement_id}",
    }


def _facade_invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-FACADE-GATE-1",
        "customer_id": "CUS-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T02:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_FACADE_GATE_1",
        "payment_method": "cash",
        "currency": "INR",
        "lines": [
            {
                "item_id": "ITEM-1",
                "quantity": 2,
                "unit_price_minor": 50000,
                "description": "Test Item",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
