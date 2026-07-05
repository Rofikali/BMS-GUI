from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StockMovementType(StrEnum):
    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True)
class Item:
    item_id: str
    sku: str
    name: str
    active: bool = True
    business_unit: str = "retail"


@dataclass(frozen=True)
class StockMovementCommand:
    movement_id: str
    item_id: str
    movement_type: StockMovementType
    quantity_delta: int
    timestamp: str
    actor_id: str
    reason: str
    source_module: str
    source_document_id: str
    correlation_id: str


@dataclass(frozen=True)
class StockMovementResult:
    movement_id: str
    item_id: str
    quantity_delta: int
    quantity_on_hand: int


@dataclass(frozen=True)
class StockOnHand:
    item_id: str
    quantity_on_hand: int
