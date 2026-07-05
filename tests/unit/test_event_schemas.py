from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.events import EventSchemaError


class EventSchemaTests(unittest.TestCase):
    def test_known_business_event_is_validated_before_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))

            store.append_business_event(
                "billing.sale_completed.v1",
                "usr_cashier",
                {
                    "invoice_id": "INV-EVENT-1",
                    "customer_id": "CUS-1",
                    "currency": "INR",
                    "subtotal_minor": 100000,
                    "tax_minor": 18000,
                    "total_minor": 118000,
                    "payment_method": "cash",
                    "line_count": 1,
                },
                correlation_id="corr_INV_EVENT_1",
                occurred_at="2026-05-14T02:00:00Z",
            )

            payload = store.read_payloads(store.business_events)[0]
            self.assertEqual(payload["event_type"], "billing.sale_completed.v1")
            self.assertEqual(payload["total_minor"], 118000)

    def test_unknown_business_event_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))

            with self.assertRaisesRegex(EventSchemaError, "unknown business event"):
                store.append_business_event("unknown.event.v1", "usr_test", {}, occurred_at="2026-05-14T00:00:00Z")

    def test_inventory_item_registered_event_keeps_business_unit_dimension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))

            store.append_business_event(
                "inventory.item_registered.v1",
                "usr_inventory",
                {
                    "item_id": "ITEM-GROCERY",
                    "sku": "SKU-GROCERY",
                    "name": "Grocery Item",
                    "active": True,
                    "business_unit": "grocery",
                },
                correlation_id="corr_ITEM_GROCERY",
                occurred_at="2026-05-14T00:00:00Z",
            )

            payload = store.read_payloads(store.business_events)[0]
            self.assertEqual(payload["business_unit"], "grocery")

    def test_invalid_business_event_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = initialize_data_root(Path(temp_dir))

            with self.assertRaisesRegex(EventSchemaError, "payload is invalid"):
                store.append_business_event(
                    "billing.sale_completed.v1",
                    "usr_cashier",
                    {
                        "invoice_id": "INV-EVENT-2",
                        "customer_id": "CUS-1",
                        "currency": "INR",
                        "subtotal_minor": 100000,
                        "tax_minor": 18000,
                        "total_minor": 118000,
                        "payment_method": "cash",
                        "line_count": 0,
                    },
                    occurred_at="2026-05-14T02:00:00Z",
                )


if __name__ == "__main__":
    unittest.main()
