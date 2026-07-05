from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingError, AccountingService, PostJournalCommandSchema
from bms.domain.billing import CreateInvoiceCommandSchema, validate_create_invoice_command_payload
from bms.domain.inventory import (
    ItemSchema,
    StockMovementCommandSchema,
    StockMovementType,
    validate_stock_movement_command_payload,
)


class CommandSchemaTests(unittest.TestCase):
    def test_billing_schema_converts_payload_to_invoice_command(self) -> None:
        command = validate_create_invoice_command_payload(_invoice_payload())

        self.assertEqual(command.invoice_id, "INV-SCHEMA-1")
        self.assertEqual(command.lines[0].item_id, "ITEM-1")
        self.assertEqual(command.lines[0].quantity, 2)
        self.assertEqual(command.lines[0].unit_price_minor, 50000)

    def test_billing_schema_rejects_extra_fields_and_wrong_types(self) -> None:
        extra_payload = {**_invoice_payload(), "unexpected": True}
        wrong_type_payload = _invoice_payload()
        wrong_type_payload["lines"] = [
            {
                "item_id": "ITEM-1",
                "quantity": "2",
                "unit_price_minor": 50000,
                "description": "Test Item",
            }
        ]

        with self.assertRaises(ValidationError):
            CreateInvoiceCommandSchema.model_validate(extra_payload)
        with self.assertRaises(ValidationError):
            CreateInvoiceCommandSchema.model_validate(wrong_type_payload)

    def test_inventory_schemas_convert_item_and_stock_movement_payloads(self) -> None:
        item = ItemSchema.model_validate(
            {
                "item_id": "ITEM-1",
                "sku": "SKU-1",
                "name": "Test Item",
                "active": True,
                "business_unit": "grocery",
            }
        ).to_item()
        movement = validate_stock_movement_command_payload(
            {
                "movement_id": "MOV-SCHEMA-1",
                "item_id": "ITEM-1",
                "movement_type": "stock_out",
                "quantity_delta": -2,
                "timestamp": "2026-05-14T02:00:00Z",
                "actor_id": "usr_cashier",
                "reason": "invoice sale",
                "source_module": "billing",
                "source_document_id": "INV-SCHEMA-1",
                "correlation_id": "corr_INV_SCHEMA_1",
            }
        )

        self.assertEqual(item.sku, "SKU-1")
        self.assertEqual(item.business_unit, "grocery")
        self.assertEqual(movement.movement_type, StockMovementType.STOCK_OUT)
        self.assertEqual(movement.quantity_delta, -2)

    def test_inventory_schema_rejects_non_boolean_item_status(self) -> None:
        with self.assertRaises(ValidationError):
            ItemSchema.model_validate(
                {"item_id": "ITEM-1", "sku": "SKU-1", "name": "Test Item", "active": "true"}
            )

    def test_accounting_schema_converts_payload_but_service_owns_balance_rule(self) -> None:
        command = PostJournalCommandSchema.model_validate(
            {
                "journal_id": "JRN-SCHEMA-1",
                "period_id": "FY2026-05",
                "timestamp": "2026-05-14T02:00:00Z",
                "actor_id": "usr_accountant",
                "source_module": "billing",
                "source_document_id": "INV-SCHEMA-1",
                "correlation_id": "corr_JRN_SCHEMA_1",
                "description": "Unbalanced boundary payload",
                "lines": [
                    {"account_code": "1000", "debit_minor": 118000, "currency": "INR"},
                    {"account_code": "4000", "credit_minor": 100000, "currency": "INR"},
                ],
            }
        ).to_command()

        self.assertEqual(command.journal_id, "JRN-SCHEMA-1")
        self.assertEqual(command.lines[0].debit_minor, 118000)
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))
            with self.assertRaisesRegex(AccountingError, "debits must equal credits"):
                service.post_journal(command)

    def test_accounting_schema_rejects_extra_line_fields(self) -> None:
        payload = {
            "journal_id": "JRN-SCHEMA-2",
            "period_id": "FY2026-05",
            "timestamp": "2026-05-14T02:00:00Z",
            "actor_id": "usr_accountant",
            "source_module": "billing",
            "source_document_id": "INV-SCHEMA-2",
            "correlation_id": "corr_JRN_SCHEMA_2",
            "description": "Extra field boundary payload",
            "lines": [
                {"account_code": "1000", "debit_minor": 118000, "currency": "INR", "extra": "nope"},
            ],
        }

        with self.assertRaises(ValidationError):
            PostJournalCommandSchema.model_validate(payload)


def _invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-SCHEMA-1",
        "customer_id": "CUS-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T02:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_SCHEMA_1",
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
