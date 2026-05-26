from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class EventSchemaError(ValueError):
    pass


class _BusinessEventSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str
    occurred_at: str


class AuditRecordCreatedV1(_BusinessEventSchema):
    event_type: Literal["audit.record_created.v1"]
    action: str
    target_type: str
    target_id: str


class InventoryItemRegisteredV1(_BusinessEventSchema):
    event_type: Literal["inventory.item_registered.v1"]
    item_id: str
    sku: str
    name: str
    active: bool


class InventoryStockMovedV1(_BusinessEventSchema):
    event_type: Literal["inventory.stock_moved.v1"]
    movement_id: str
    item_id: str
    movement_type: Literal["stock_in", "stock_out", "adjustment"]
    quantity_delta: int
    quantity_on_hand_after: int
    source_document_id: str


class AccountingJournalPostedV1(_BusinessEventSchema):
    event_type: Literal["accounting.journal_posted.v1"]
    journal_id: str
    period_id: str
    source_document_id: str
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)
    currency: str


class AccountingPeriodClosedV1(_BusinessEventSchema):
    event_type: Literal["accounting.period_closed.v1"]
    period_id: str
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)


class BillingSaleCompletedV1(_BusinessEventSchema):
    event_type: Literal["billing.sale_completed.v1"]
    invoice_id: str
    customer_id: str
    currency: str
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)
    payment_method: str
    line_count: int = Field(ge=1)


_EVENT_SCHEMAS: dict[str, type[_BusinessEventSchema]] = {
    "audit.record_created.v1": AuditRecordCreatedV1,
    "inventory.item_registered.v1": InventoryItemRegisteredV1,
    "inventory.stock_moved.v1": InventoryStockMovedV1,
    "accounting.journal_posted.v1": AccountingJournalPostedV1,
    "accounting.period_closed.v1": AccountingPeriodClosedV1,
    "billing.sale_completed.v1": BillingSaleCompletedV1,
}


def validate_business_event_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    schema = _EVENT_SCHEMAS.get(event_type)
    if schema is None:
        raise EventSchemaError(f"unknown business event type {event_type}")
    try:
        return schema.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise EventSchemaError(f"business event {event_type} payload is invalid") from exc
