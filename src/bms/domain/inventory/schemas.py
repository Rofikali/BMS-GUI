from __future__ import annotations

from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from bms.domain.inventory.models import Item, StockMovementCommand, StockMovementType


NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class ItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: NonEmptyStr
    sku: NonEmptyStr
    name: NonEmptyStr
    active: StrictBool = True

    def to_item(self) -> Item:
        return Item(
            item_id=self.item_id,
            sku=self.sku,
            name=self.name,
            active=self.active,
        )


class StockMovementCommandSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    movement_id: NonEmptyStr
    item_id: NonEmptyStr
    movement_type: StockMovementType
    quantity_delta: StrictInt
    timestamp: NonEmptyStr
    actor_id: NonEmptyStr
    reason: NonEmptyStr
    source_module: NonEmptyStr
    source_document_id: NonEmptyStr
    correlation_id: NonEmptyStr

    def to_command(self) -> StockMovementCommand:
        return StockMovementCommand(
            movement_id=self.movement_id,
            item_id=self.item_id,
            movement_type=self.movement_type,
            quantity_delta=self.quantity_delta,
            timestamp=self.timestamp,
            actor_id=self.actor_id,
            reason=self.reason,
            source_module=self.source_module,
            source_document_id=self.source_document_id,
            correlation_id=self.correlation_id,
        )


def validate_item_payload(payload: Mapping[str, Any]) -> Item:
    return ItemSchema.model_validate(payload).to_item()


def validate_stock_movement_command_payload(payload: Mapping[str, Any]) -> StockMovementCommand:
    return StockMovementCommandSchema.model_validate(payload).to_command()
