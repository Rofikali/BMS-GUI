from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import start_command_facade


class ReconciliationServiceTests(unittest.TestCase):
    def test_reconciliation_matches_subledgers_to_ledger_balances(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            facade.register_item(_register_item_payload())
            facade.commit_stock_movement(_stock_movement_payload())
            facade.create_invoice(_invoice_payload())
            facade.create_refund(_refund_payload())

            report = facade.reconciliation_report("FY2026-05")
            checks = {check["name"]: check for check in report["checks"]}

            self.assertTrue(report["passed"])
            self.assertEqual(checks["inventory_subledger_to_ledger"]["expected_minor"], 120000)
            self.assertEqual(checks["inventory_subledger_to_ledger"]["actual_minor"], 120000)
            self.assertEqual(checks["tax_report_to_tax_payable"]["expected_minor"], 9000)
            self.assertEqual(checks["sales_report_to_sales_revenue"]["expected_minor"], 100000)
            self.assertEqual(checks["refund_report_to_sales_returns"]["expected_minor"], 50000)
            self.assertEqual(checks["billing_cogs_to_cogs_ledger"]["expected_minor"], 30000)
            self.assertTrue(all(check["passed"] for check in checks.values()))


def _register_item_payload() -> dict[str, object]:
    return {
        "item": {
            "item_id": "ITEM-1",
            "sku": "SKU-1",
            "name": "Test Item",
            "active": True,
            "business_unit": "retail",
        },
        "actor_id": "usr_inventory",
        "created_at": "2026-05-14T08:00:00Z",
        "correlation_id": "corr_item_ITEM_1",
    }


def _stock_movement_payload() -> dict[str, object]:
    return {
        "movement_id": "MOV-IN-1",
        "item_id": "ITEM-1",
        "movement_type": "adjustment",
        "quantity_delta": 5,
        "timestamp": "2026-05-14T08:05:00Z",
        "actor_id": "usr_inventory",
        "reason": "opening stock",
        "source_module": "inventory",
        "source_document_id": "OPEN-ITEM-1",
        "correlation_id": "corr_stock_ITEM_1",
        "unit_cost_minor": 30000,
        "period_id": "FY2026-05",
    }


def _invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-1",
        "customer_id": "CUS-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T09:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_1",
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


def _refund_payload() -> dict[str, object]:
    return {
        "refund_id": "REF-1",
        "original_invoice_id": "INV-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T10:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_REF_1",
        "currency": "INR",
        "reason": "customer return",
        "lines": [
            {
                "item_id": "ITEM-1",
                "quantity": 1,
                "unit_price_minor": 50000,
                "description": "Test Item",
                "restock": True,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
