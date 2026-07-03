from __future__ import annotations

from uuid import uuid4

from bms.domain.inventory.models import Item, StockMovementCommand, StockMovementResult, StockMovementType
from bms.storage.ports import DurableStorePort


class InventoryError(ValueError):
    pass


class InventoryService:
    def __init__(self, store: DurableStorePort, *, allow_negative_stock: bool = False) -> None:
        self.store = store
        self.allow_negative_stock = allow_negative_stock

    def register_item(
        self,
        item: Item,
        *,
        actor_id: str,
        created_at: str,
        correlation_id: str,
    ) -> Item:
        self._validate_item(item)
        self._reject_duplicate_item(item)

        transaction_id = f"txn_inventory_register_item_{item.item_id}_{uuid4().hex}"
        self.store.core.append_wal_pending(
            self.store.wal,
            transaction_id,
            created_at,
            actor_id,
            correlation_id,
            {
                "operation": "inventory.register_item",
                "item_id": item.item_id,
                "sku": item.sku,
            },
        )
        self.store.append_record(
            self.store.items,
            "inventory.item_registered",
            actor_id,
            correlation_id,
            f"item_registered_{item.item_id}",
            {
                "item_id": item.item_id,
                "sku": item.sku,
                "name": item.name,
                "active": item.active,
                "created_at": created_at,
                "actor_id": actor_id,
                "correlation_id": correlation_id,
            },
            record_id=f"itm_{item.item_id}",
            created_at=created_at,
        )
        self.store.append_audit_record(
            "inventory.item_registered",
            actor_id,
            "inventory_item",
            item.item_id,
            correlation_id,
            occurred_at=created_at,
            details={"sku": item.sku, "name": item.name, "active": item.active},
            idempotency_key=f"audit_item_registered_{item.item_id}",
        )
        self.store.append_business_event(
            "inventory.item_registered.v1",
            actor_id,
            {"item_id": item.item_id, "sku": item.sku, "name": item.name, "active": item.active},
            correlation_id=correlation_id,
            occurred_at=created_at,
            idempotency_key=f"event_item_registered_{item.item_id}",
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            transaction_id,
            created_at,
            actor_id,
            correlation_id,
        )
        return item

    def get_items(self) -> dict[str, Item]:
        items: dict[str, Item] = {}
        for payload in self.store.read_payloads(self.store.items):
            item_id = payload.get("item_id")
            sku = payload.get("sku")
            name = payload.get("name")
            active = payload.get("active")
            if not isinstance(item_id, str) or not isinstance(sku, str) or not isinstance(name, str):
                raise InventoryError("stored item payload has invalid identity fields")
            if isinstance(active, bool):
                item_active = active
            else:
                raise InventoryError("stored item payload active field is not a boolean")
            items[item_id] = Item(item_id=item_id, sku=sku, name=name, active=item_active)
        return dict(sorted(items.items()))

    def get_item(self, item_id: str) -> Item | None:
        return self.get_items().get(item_id)

    def commit_movement(self, command: StockMovementCommand) -> StockMovementResult:
        self._validate_command(command)
        self._reject_duplicate_movement(command.movement_id)
        self._validate_movement_item(command.item_id)

        current_quantity = self.get_stock_on_hand(command.item_id)
        next_quantity = current_quantity + command.quantity_delta
        if next_quantity < 0 and not self.allow_negative_stock:
            raise InventoryError(f"movement would make stock negative for item {command.item_id}")

        transaction_id = f"txn_inventory_{command.movement_id}_{uuid4().hex}"
        self.store.core.append_wal_pending(
            self.store.wal,
            transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
            {
                "operation": "inventory.commit_movement",
                "movement_id": command.movement_id,
                "item_id": command.item_id,
                "quantity_delta": command.quantity_delta,
                "source_document_id": command.source_document_id,
            },
        )
        self.store.append_record(
            self.store.stock_movements,
            "inventory.stock_movement",
            command.actor_id,
            command.correlation_id,
            f"stock_movement_{command.movement_id}",
            {
                "movement_id": command.movement_id,
                "item_id": command.item_id,
                "movement_type": command.movement_type.value,
                "quantity_delta": command.quantity_delta,
                "quantity_on_hand_after": next_quantity,
                "timestamp": command.timestamp,
                "actor_id": command.actor_id,
                "reason": command.reason,
                "source_module": command.source_module,
                "source_document_id": command.source_document_id,
                "correlation_id": command.correlation_id,
            },
            record_id=f"stm_{command.movement_id}",
            created_at=command.timestamp,
        )
        self.store.append_audit_record(
            "inventory.stock_moved",
            command.actor_id,
            "inventory_item",
            command.item_id,
            command.correlation_id,
            occurred_at=command.timestamp,
            details={
                "movement_id": command.movement_id,
                "movement_type": command.movement_type.value,
                "quantity_delta": command.quantity_delta,
                "quantity_on_hand_after": next_quantity,
                "reason": command.reason,
                "source_module": command.source_module,
                "source_document_id": command.source_document_id,
            },
            idempotency_key=f"audit_stock_moved_{command.movement_id}",
        )
        self.store.append_business_event(
            "inventory.stock_moved.v1",
            command.actor_id,
            {
                "movement_id": command.movement_id,
                "item_id": command.item_id,
                "movement_type": command.movement_type.value,
                "quantity_delta": command.quantity_delta,
                "quantity_on_hand_after": next_quantity,
                "source_document_id": command.source_document_id,
            },
            correlation_id=command.correlation_id,
            occurred_at=command.timestamp,
            idempotency_key=f"event_stock_moved_{command.movement_id}",
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
        )
        return StockMovementResult(command.movement_id, command.item_id, command.quantity_delta, next_quantity)

    def adjust_stock(
        self,
        *,
        movement_id: str,
        item_id: str,
        quantity_delta: int,
        timestamp: str,
        actor_id: str,
        reason: str,
        source_document_id: str,
        correlation_id: str,
    ) -> StockMovementResult:
        return self.commit_movement(
            StockMovementCommand(
                movement_id=movement_id,
                item_id=item_id,
                movement_type=StockMovementType.ADJUSTMENT,
                quantity_delta=quantity_delta,
                timestamp=timestamp,
                actor_id=actor_id,
                reason=reason,
                source_module="inventory",
                source_document_id=source_document_id,
                correlation_id=correlation_id,
            )
        )

    def get_stock_on_hand(self, item_id: str) -> int:
        quantity = 0
        for payload in self.store.read_payloads(self.store.stock_movements):
            if payload.get("item_id") == item_id:
                quantity += _int_payload(payload, "quantity_delta")
        return quantity

    def get_all_stock_on_hand(self) -> dict[str, int]:
        quantities: dict[str, int] = {}
        for payload in self.store.read_payloads(self.store.stock_movements):
            item_id = payload.get("item_id")
            if not isinstance(item_id, str):
                raise InventoryError("stored stock movement item_id is not a string")
            quantities[item_id] = quantities.get(item_id, 0) + _int_payload(payload, "quantity_delta")
        return dict(sorted(quantities.items()))

    def _validate_item(self, item: Item) -> None:
        required = {"item_id": item.item_id, "sku": item.sku, "name": item.name}
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise InventoryError(f"missing required item field(s): {', '.join(missing)}")

    def _reject_duplicate_item(self, item: Item) -> None:
        for existing in self.get_items().values():
            if existing.item_id == item.item_id:
                raise InventoryError(f"item {item.item_id} is already registered")
            if existing.sku == item.sku:
                raise InventoryError(f"sku {item.sku} is already registered")

    def _validate_movement_item(self, item_id: str) -> None:
        item = self.get_item(item_id)
        if item is None:
            raise InventoryError(f"unknown item {item_id}")
        if not item.active:
            raise InventoryError(f"inactive item {item_id}")

    def _validate_command(self, command: StockMovementCommand) -> None:
        required = {
            "movement_id": command.movement_id,
            "item_id": command.item_id,
            "timestamp": command.timestamp,
            "actor_id": command.actor_id,
            "reason": command.reason,
            "source_module": command.source_module,
            "source_document_id": command.source_document_id,
            "correlation_id": command.correlation_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise InventoryError(f"missing required stock movement field(s): {', '.join(missing)}")
        if command.quantity_delta == 0:
            raise InventoryError("stock movement quantity_delta cannot be zero")
        if command.movement_type == StockMovementType.STOCK_IN and command.quantity_delta < 0:
            raise InventoryError("stock_in movement must increase stock")
        if command.movement_type == StockMovementType.STOCK_OUT and command.quantity_delta > 0:
            raise InventoryError("stock_out movement must decrease stock")

    def _reject_duplicate_movement(self, movement_id: str) -> None:
        for payload in self.store.read_payloads(self.store.stock_movements):
            if payload.get("movement_id") == movement_id:
                raise InventoryError(f"stock movement {movement_id} is already committed")


def _int_payload(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InventoryError(f"stored payload field {key} is not an integer")
    return value
