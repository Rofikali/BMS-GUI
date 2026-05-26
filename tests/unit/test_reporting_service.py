from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingService
from bms.domain.billing import BillingService, CreateInvoiceCommand, InvoiceLineCommand
from bms.domain.inventory import InventoryService, Item
from bms.domain.reporting import ReportingError, ReportingService


class ReportingServiceTests(unittest.TestCase):
    def test_reports_are_rebuilt_from_durable_records_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, billing, inventory, _accounting = _services(root)
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(
                _invoice("INV-REPORT-1", quantity=2, unit_price_minor=50000)
            )

            restarted_store = initialize_data_root(root)
            reports = ReportingService(restarted_store)

            invoice_report = reports.get_invoice_report("FY2026-05")
            stock_report = reports.get_stock_report(low_stock_threshold=3)
            ledger_report = reports.get_ledger_report("FY2026-05")
            tax_report = reports.get_tax_report("FY2026-05")
            trial_balance_report = reports.get_trial_balance_report("FY2026-05")
            invoice_export = reports.export_invoice_report("FY2026-05")
            stock_export = reports.export_stock_report(low_stock_threshold=3)
            ledger_export = reports.export_ledger_report("FY2026-05")
            tax_export = reports.export_tax_report("FY2026-05")
            trial_balance_export = reports.export_trial_balance_report("FY2026-05")

            self.assertEqual(len(invoice_report.rows), 1)
            self.assertEqual(invoice_report.rows[0].invoice_id, "INV-REPORT-1")
            self.assertEqual(invoice_report.rows[0].total_minor, 118000)
            self.assertEqual(invoice_report.totals[0].currency, "INR")
            self.assertEqual(invoice_report.totals[0].subtotal_minor, 100000)
            self.assertEqual(invoice_report.totals[0].tax_minor, 18000)
            self.assertEqual(invoice_report.totals[0].total_minor, 118000)
            self.assertEqual(stock_report.rows[0].item_id, "ITEM-1")
            self.assertEqual(stock_report.rows[0].quantity_on_hand, 3)
            self.assertTrue(stock_report.rows[0].low_stock)
            self.assertEqual(
                {row.account_code for row in ledger_report.rows},
                {"1000", "2100", "4000"},
            )
            self.assertEqual(tax_report.invoice_tax_collected_minor, 18000)
            self.assertEqual(tax_report.tax_payable_balance_minor, 18000)
            self.assertTrue(trial_balance_report.is_balanced)
            self.assertEqual(invoice_export["totals"][0]["total_minor"], 118000)
            self.assertEqual(stock_export["rows"][0]["quantity_on_hand"], 3)
            self.assertEqual({row["account_code"] for row in ledger_export["rows"]}, {"1000", "2100", "4000"})
            self.assertEqual(tax_export["invoice_tax_collected_minor"], 18000)
            self.assertTrue(trial_balance_export["is_balanced"])

    def test_stock_report_rejects_negative_low_stock_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            reports = ReportingService(initialize_data_root(Path(temp_dir)))

            with self.assertRaisesRegex(ReportingError, "low_stock_threshold"):
                reports.get_stock_report(low_stock_threshold=-1)


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


def _invoice(
    invoice_id: str, *, quantity: int, unit_price_minor: int
) -> CreateInvoiceCommand:
    return CreateInvoiceCommand(
        invoice_id=invoice_id,
        customer_id="CUS-1",
        period_id="FY2026-05",
        timestamp="2026-05-14T02:00:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{invoice_id}",
        payment_method="cash",
        currency="INR",
        lines=(InvoiceLineCommand("ITEM-1", quantity, unit_price_minor, "Test Item"),),
    )


if __name__ == "__main__":
    unittest.main()
