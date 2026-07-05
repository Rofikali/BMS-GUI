from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingService
from bms.domain.billing import (
    BillingService,
    CreateInvoiceCommand,
    CreateRefundCommand,
    InvoiceLineCommand,
    RefundLineCommand,
)
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
            billing.create_refund(
                _refund("REF-REPORT-1", original_invoice_id="INV-REPORT-1")
            )

            restarted_store = initialize_data_root(root)
            reports = ReportingService(restarted_store)

            invoice_report = reports.get_invoice_report("FY2026-05")
            refund_report = reports.get_refund_report("FY2026-05")
            refund_availability = reports.get_refund_availability_report("FY2026-05")
            stock_report = reports.get_stock_report(low_stock_threshold=3)
            ledger_report = reports.get_ledger_report("FY2026-05")
            profit_and_loss_report = reports.get_profit_and_loss_report("FY2026-05")
            tax_report = reports.get_tax_report("FY2026-05")
            trial_balance_report = reports.get_trial_balance_report("FY2026-05")
            business_unit_revenue = reports.get_business_unit_revenue_report("FY2026-05")
            invoice_export = reports.export_invoice_report("FY2026-05")
            refund_export = reports.export_refund_report("FY2026-05")
            refund_availability_export = reports.export_refund_availability_report("FY2026-05")
            stock_export = reports.export_stock_report(low_stock_threshold=3)
            ledger_export = reports.export_ledger_report("FY2026-05")
            profit_and_loss_export = reports.export_profit_and_loss_report("FY2026-05")
            tax_export = reports.export_tax_report("FY2026-05")
            trial_balance_export = reports.export_trial_balance_report("FY2026-05")
            business_unit_revenue_export = reports.export_business_unit_revenue_report("FY2026-05")

            self.assertEqual(len(invoice_report.rows), 1)
            self.assertEqual(invoice_report.rows[0].invoice_id, "INV-REPORT-1")
            self.assertEqual(invoice_report.rows[0].total_minor, 118000)
            self.assertEqual(invoice_report.totals[0].currency, "INR")
            self.assertEqual(invoice_report.totals[0].subtotal_minor, 100000)
            self.assertEqual(invoice_report.totals[0].tax_minor, 18000)
            self.assertEqual(invoice_report.totals[0].total_minor, 118000)
            self.assertEqual(len(refund_report.rows), 1)
            self.assertEqual(refund_report.rows[0].refund_id, "REF-REPORT-1")
            self.assertEqual(refund_report.rows[0].original_invoice_id, "INV-REPORT-1")
            self.assertEqual(refund_report.rows[0].reason, "customer return")
            self.assertEqual(refund_report.rows[0].total_minor, 59000)
            self.assertEqual(refund_report.totals[0].currency, "INR")
            self.assertEqual(refund_report.totals[0].tax_minor, 9000)
            self.assertEqual(refund_report.totals[0].total_minor, 59000)
            self.assertEqual(len(refund_availability.rows), 1)
            self.assertEqual(refund_availability.rows[0].invoice_id, "INV-REPORT-1")
            self.assertEqual(refund_availability.rows[0].original_quantity, 2)
            self.assertEqual(refund_availability.rows[0].refunded_quantity, 1)
            self.assertEqual(refund_availability.rows[0].remaining_quantity, 1)
            self.assertEqual(refund_availability.rows[0].remaining_subtotal_minor, 50000)
            self.assertEqual(stock_report.rows[0].item_id, "ITEM-1")
            self.assertEqual(stock_report.rows[0].business_unit, "grocery")
            self.assertEqual(stock_report.rows[0].quantity_on_hand, 4)
            self.assertFalse(stock_report.rows[0].low_stock)
            self.assertEqual(
                {row.account_code for row in ledger_report.rows},
                {"1000", "2100", "4000"},
            )
            self.assertEqual(profit_and_loss_report.revenue_minor, 100000)
            self.assertEqual(profit_and_loss_report.contra_revenue_minor, 50000)
            self.assertEqual(profit_and_loss_report.net_revenue_minor, 50000)
            self.assertEqual(profit_and_loss_report.expense_minor, 0)
            self.assertEqual(profit_and_loss_report.net_income_minor, 50000)
            self.assertEqual(tax_report.invoice_tax_collected_minor, 18000)
            self.assertEqual(tax_report.tax_payable_balance_minor, 9000)
            self.assertTrue(trial_balance_report.is_balanced)
            self.assertEqual(len(business_unit_revenue.rows), 1)
            self.assertEqual(business_unit_revenue.rows[0].business_unit, "grocery")
            self.assertEqual(business_unit_revenue.rows[0].invoice_subtotal_minor, 100000)
            self.assertEqual(business_unit_revenue.rows[0].refund_subtotal_minor, 50000)
            self.assertEqual(business_unit_revenue.rows[0].net_revenue_minor, 50000)
            self.assertEqual(invoice_export["totals"][0]["total_minor"], 118000)
            self.assertEqual(refund_export["rows"][0]["refund_id"], "REF-REPORT-1")
            self.assertEqual(refund_export["totals"][0]["total_minor"], 59000)
            self.assertEqual(refund_availability_export["rows"][0]["remaining_quantity"], 1)
            self.assertEqual(stock_export["rows"][0]["quantity_on_hand"], 4)
            self.assertEqual(stock_export["rows"][0]["business_unit"], "grocery")
            self.assertEqual({row["account_code"] for row in ledger_export["rows"]}, {"1000", "2100", "4000"})
            self.assertEqual(profit_and_loss_export["net_income_minor"], 50000)
            self.assertEqual(tax_export["invoice_tax_collected_minor"], 18000)
            self.assertTrue(trial_balance_export["is_balanced"])
            self.assertEqual(business_unit_revenue_export["rows"][0]["business_unit"], "grocery")

    def test_reports_rebuild_when_snapshot_outputs_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, billing, inventory, _accounting = _services(root)
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(
                _invoice("INV-REBUILD-1", quantity=2, unit_price_minor=50000)
            )
            for relative_path in (
                "accounting/snapshots",
                "inventory/snapshots",
                "billing/snapshots",
                "reports/generated",
            ):
                shutil.rmtree(root / relative_path)

            rebuilt_store = initialize_data_root(root)
            reports = ReportingService(rebuilt_store)

            self.assertEqual(
                reports.get_invoice_report("FY2026-05").totals[0].total_minor,
                118000,
            )
            self.assertEqual(
                reports.get_stock_report(low_stock_threshold=3).rows[0].quantity_on_hand,
                3,
            )
            self.assertEqual(
                reports.get_tax_report("FY2026-05").tax_payable_balance_minor,
                18000,
            )
            self.assertTrue(
                reports.get_trial_balance_report("FY2026-05").is_balanced
            )

    def test_refund_availability_accepts_empty_invoice_line_description(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _store, billing, inventory, _accounting = _services(root)
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(
                CreateInvoiceCommand(
                    invoice_id="INV-EMPTY-DESC",
                    customer_id="CUS-1",
                    period_id="FY2026-05",
                    timestamp="2026-05-14T02:00:00Z",
                    actor_id="usr_cashier",
                    correlation_id="corr_INV_EMPTY_DESC",
                    payment_method="cash",
                    currency="INR",
                    lines=(InvoiceLineCommand("ITEM-1", 1, 50000, ""),),
                )
            )

            report = ReportingService(initialize_data_root(root)).get_refund_availability_report("FY2026-05")

            self.assertEqual(report.rows[0].description, "")
            self.assertEqual(report.rows[0].remaining_quantity, 1)

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
        Item("ITEM-1", "SKU-1", "Test Item", business_unit="grocery"),
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


def _refund(refund_id: str, *, original_invoice_id: str) -> CreateRefundCommand:
    return CreateRefundCommand(
        refund_id=refund_id,
        original_invoice_id=original_invoice_id,
        period_id="FY2026-05",
        timestamp="2026-05-14T02:30:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{refund_id}",
        currency="INR",
        reason="customer return",
        lines=(RefundLineCommand("ITEM-1", 1, 50000, "Test Item", True),),
    )


if __name__ == "__main__":
    unittest.main()
