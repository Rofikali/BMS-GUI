from __future__ import annotations

import tarfile
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingService
from bms.domain.billing import BillingService, CreateInvoiceCommand, InvoiceLineCommand
from bms.domain.inventory import InventoryService, Item
from bms.domain.reporting import ReportingService
from bms.services import BackupError, BackupService


class BackupServiceTests(unittest.TestCase):
    def test_backup_restore_validates_and_preserves_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            store, billing, inventory, _accounting = _services(root)
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-BACKUP-1"))

            backup = BackupService(store).create_backup(
                created_at="2026-05-14T03:00:00Z"
            )
            restore = BackupService.restore_backup(backup.backup_path, restore_root)
            restored_reports = ReportingService(initialize_data_root(restore_root))

            self.assertTrue(backup.backup_path.exists())
            self.assertEqual(backup.verified_record_counts["invoices"], 1)
            self.assertEqual(
                restore.verified_record_counts, backup.verified_record_counts
            )
            self.assertEqual(
                restored_reports.get_invoice_report("FY2026-05").totals[0].total_minor,
                118000,
            )
            self.assertEqual(
                restored_reports.get_stock_report().rows[0].quantity_on_hand, 3
            )
            self.assertTrue(
                restored_reports.get_trial_balance_report("FY2026-05").is_balanced
            )

    def test_restore_rejects_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_path = Path(temp_dir) / "bad-backup.tar.gz"
            restore_root = Path(temp_dir) / "restored"
            manifest_bytes = b'{"format":"not.bms","created_at":"2026-05-14T03:00:00Z","verified_record_counts":{}}'
            with tarfile.open(backup_path, "w:gz") as archive:
                manifest_info = tarfile.TarInfo("backup_manifest.json")
                manifest_info.size = len(manifest_bytes)
                archive.addfile(manifest_info, BytesIO(manifest_bytes))

            with self.assertRaisesRegex(BackupError, "manifest"):
                BackupService.restore_backup(backup_path, restore_root)

    def test_restore_rejects_non_empty_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            store = initialize_data_root(root)
            backup = BackupService(store).create_backup(
                created_at="2026-05-14T03:00:00Z"
            )
            restore_root = Path(temp_dir) / "restored"
            restore_root.mkdir()
            (restore_root / "existing.txt").write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(BackupError, "not empty"):
                BackupService.restore_backup(backup.backup_path, restore_root)


def _services(
    root: Path,
) -> tuple[object, BillingService, InventoryService, AccountingService]:
    store = initialize_data_root(root)
    inventory = InventoryService(store)
    accounting = AccountingService(store)
    billing = BillingService(store, inventory, accounting)
    return store, billing, inventory, accounting


def _register_and_stock_item(inventory: InventoryService, *, quantity: int) -> None:
    inventory.register_item(
        Item("ITEM-1", "SKU-1", "Test Item"),
        actor_id="usr_inventory",
        created_at="2026-05-14T00:00:00Z",
        correlation_id="corr_item_ITEM-1",
    )
    inventory.adjust_stock(
        movement_id="MOV-STOCK-IN",
        item_id="ITEM-1",
        quantity_delta=quantity,
        timestamp="2026-05-14T00:05:00Z",
        actor_id="usr_inventory",
        reason="opening stock",
        source_document_id="STK-1001",
        correlation_id="corr_stock_in",
    )


def _invoice(invoice_id: str) -> CreateInvoiceCommand:
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


if __name__ == "__main__":
    unittest.main()
