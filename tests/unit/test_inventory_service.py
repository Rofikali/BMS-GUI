from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.inventory import InventoryError, InventoryService, Item, StockMovementCommand, StockMovementType


class InventoryServiceTests(unittest.TestCase):
    def test_stock_movement_appends_and_rebuilds_stock_on_hand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            result = service.commit_movement(_movement("MOV-1", quantity_delta=10, unit_cost_minor=25000))
            service.commit_movement(_movement("MOV-2", quantity_delta=-3, movement_type=StockMovementType.STOCK_OUT))

            self.assertEqual(result.quantity_on_hand, 10)
            self.assertEqual(result.value_delta_minor, 250000)
            self.assertEqual(result.inventory_value_after_minor, 250000)
            self.assertEqual(service.get_stock_on_hand("ITEM-1"), 7)
            self.assertEqual(service.get_inventory_value_minor("ITEM-1"), 175000)
            self.assertEqual(service.get_weighted_average_unit_cost_minor("ITEM-1"), 25000)
            self.assertEqual(service.get_all_stock_on_hand(), {"ITEM-1": 7})
            self.assertEqual(service.store.core.verify_file(service.store.stock_movements), 2)

    def test_stock_movement_recalculates_weighted_average_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            service.commit_movement(_movement("MOV-COST-1", quantity_delta=2, unit_cost_minor=30000))
            service.commit_movement(_movement("MOV-COST-2", quantity_delta=3, unit_cost_minor=50000))
            out = service.commit_movement(
                _movement("MOV-COST-3", quantity_delta=-2, movement_type=StockMovementType.STOCK_OUT)
            )

            self.assertEqual(service.get_stock_on_hand("ITEM-1"), 3)
            self.assertEqual(service.get_weighted_average_unit_cost_minor("ITEM-1"), 42000)
            self.assertEqual(out.unit_cost_minor, 42000)
            self.assertEqual(out.value_delta_minor, -84000)
            self.assertEqual(service.get_inventory_value_minor("ITEM-1"), 126000)

    def test_stock_on_hand_survives_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = InventoryService(initialize_data_root(root))
            _register_item(service)
            service.commit_movement(_movement("MOV-3", quantity_delta=8))

            restarted = InventoryService(initialize_data_root(root))

            self.assertEqual(restarted.get_stock_on_hand("ITEM-1"), 8)

    def test_negative_stock_is_blocked_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            with self.assertRaisesRegex(InventoryError, "negative"):
                service.commit_movement(_movement("MOV-4", quantity_delta=-1, movement_type=StockMovementType.STOCK_OUT))

            self.assertEqual(service.get_stock_on_hand("ITEM-1"), 0)

    def test_negative_stock_can_be_enabled_by_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)), allow_negative_stock=True)
            _register_item(service)

            result = service.commit_movement(_movement("MOV-5", quantity_delta=-1, movement_type=StockMovementType.STOCK_OUT))

            self.assertEqual(result.quantity_on_hand, -1)
            self.assertEqual(service.get_stock_on_hand("ITEM-1"), -1)

    def test_duplicate_movement_id_does_not_double_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)
            service.commit_movement(_movement("MOV-6", quantity_delta=5))

            with self.assertRaisesRegex(InventoryError, "already committed"):
                service.commit_movement(_movement("MOV-6", quantity_delta=5))

            self.assertEqual(service.get_stock_on_hand("ITEM-1"), 5)

    def test_stock_movement_writes_audit_and_business_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            service.commit_movement(_movement("MOV-7", quantity_delta=4))

            audit_payloads = service.store.read_payloads(service.store.audit_records)
            event_payloads = service.store.read_payloads(service.store.business_events)
            self.assertEqual(audit_payloads[0]["action"], "inventory.item_registered")
            self.assertEqual(audit_payloads[1]["action"], "inventory.stock_moved")
            self.assertEqual(audit_payloads[1]["target_id"], "ITEM-1")
            self.assertEqual(event_payloads[0]["event_type"], "inventory.item_registered.v1")
            self.assertEqual(event_payloads[1]["event_type"], "inventory.stock_moved.v1")
            self.assertEqual(service.store.core.verify_file(service.store.audit_records), 2)
            self.assertEqual(service.store.core.verify_file(service.store.business_events), 2)

    def test_stock_movement_requires_reason_and_source_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            with self.assertRaisesRegex(InventoryError, "reason"):
                service.commit_movement(_movement("MOV-8", quantity_delta=1, reason=""))
            with self.assertRaisesRegex(InventoryError, "source_document_id"):
                service.commit_movement(_movement("MOV-9", quantity_delta=1, source_document_id=""))

    def test_item_registration_persists_identity_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = InventoryService(initialize_data_root(root))

            service.register_item(
                Item("ITEM-1", "SKU-1", "Test Item"),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_ITEM-1",
            )

            restarted = InventoryService(initialize_data_root(root))
            item = restarted.get_item("ITEM-1")

            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.sku, "SKU-1")
            self.assertEqual(item.name, "Test Item")
            self.assertTrue(item.active)
            self.assertEqual(restarted.store.core.verify_file(restarted.store.items), 1)

    def test_duplicate_item_id_or_sku_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            _register_item(service)

            with self.assertRaisesRegex(InventoryError, "already registered"):
                service.register_item(
                    Item("ITEM-1", "SKU-2", "Other Item"),
                    actor_id="usr_inventory",
                    created_at="2026-05-14T00:00:00Z",
                    correlation_id="corr_dup_item",
                )
            with self.assertRaisesRegex(InventoryError, "sku"):
                service.register_item(
                    Item("ITEM-2", "SKU-1", "Other Item"),
                    actor_id="usr_inventory",
                    created_at="2026-05-14T00:00:00Z",
                    correlation_id="corr_dup_sku",
                )

    def test_stock_movement_rejects_unknown_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))

            with self.assertRaisesRegex(InventoryError, "unknown item"):
                service.commit_movement(_movement("MOV-UNKNOWN", quantity_delta=1))

    def test_stock_movement_rejects_inactive_item(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = InventoryService(initialize_data_root(Path(temp_dir)))
            service.register_item(
                Item("ITEM-1", "SKU-1", "Test Item", active=False),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_inactive",
            )

            with self.assertRaisesRegex(InventoryError, "inactive item"):
                service.commit_movement(_movement("MOV-INACTIVE", quantity_delta=1))


def _movement(
    movement_id: str,
    *,
    quantity_delta: int,
    movement_type: StockMovementType = StockMovementType.STOCK_IN,
    reason: str = "opening stock",
    source_document_id: str = "STK-1001",
    unit_cost_minor: int = 0,
) -> StockMovementCommand:
    return StockMovementCommand(
        movement_id=movement_id,
        item_id="ITEM-1",
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        timestamp="2026-05-14T00:00:00Z",
        actor_id="usr_inventory",
        reason=reason,
        source_module="inventory",
        source_document_id=source_document_id,
        correlation_id=f"corr_{movement_id}",
        unit_cost_minor=unit_cost_minor,
    )


def _register_item(service: InventoryService) -> None:
    service.register_item(
        Item("ITEM-1", "SKU-1", "Test Item"),
        actor_id="usr_inventory",
        created_at="2026-05-14T00:00:00Z",
        correlation_id="corr_item_ITEM-1",
    )


if __name__ == "__main__":
    unittest.main()
