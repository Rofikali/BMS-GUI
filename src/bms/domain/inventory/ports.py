from __future__ import annotations

from typing import Protocol

from bms.domain.inventory.models import Item, StockMovementCommand, StockMovementResult


class InventoryPort(Protocol):
    def register_item(
        self,
        item: Item,
        *,
        actor_id: str,
        created_at: str,
        correlation_id: str,
    ) -> Item:
        raise NotImplementedError

    def get_item(self, item_id: str) -> Item | None:
        raise NotImplementedError

    def commit_movement(self, command: StockMovementCommand) -> StockMovementResult:
        raise NotImplementedError

    def get_stock_on_hand(self, item_id: str) -> int:
        raise NotImplementedError

    def get_inventory_value_minor(self, item_id: str) -> int:
        raise NotImplementedError

    def get_weighted_average_unit_cost_minor(self, item_id: str) -> int:
        raise NotImplementedError
