from __future__ import annotations

from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from bms.domain.billing.models import CreateInvoiceCommand, InvoiceLineCommand


NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class InvoiceLineCommandSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: NonEmptyStr
    quantity: StrictInt
    unit_price_minor: StrictInt
    description: StrictStr = ""

    def to_command(self) -> InvoiceLineCommand:
        return InvoiceLineCommand(
            item_id=self.item_id,
            quantity=self.quantity,
            unit_price_minor=self.unit_price_minor,
            description=self.description,
        )


class CreateInvoiceCommandSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    invoice_id: NonEmptyStr
    customer_id: NonEmptyStr
    period_id: NonEmptyStr
    timestamp: NonEmptyStr
    actor_id: NonEmptyStr
    correlation_id: NonEmptyStr
    payment_method: NonEmptyStr
    currency: NonEmptyStr
    lines: tuple[InvoiceLineCommandSchema, ...] = Field(min_length=1)

    def to_command(self) -> CreateInvoiceCommand:
        return CreateInvoiceCommand(
            invoice_id=self.invoice_id,
            customer_id=self.customer_id,
            period_id=self.period_id,
            timestamp=self.timestamp,
            actor_id=self.actor_id,
            correlation_id=self.correlation_id,
            payment_method=self.payment_method,
            currency=self.currency,
            lines=tuple(line.to_command() for line in self.lines),
        )


def validate_create_invoice_command_payload(payload: Mapping[str, Any]) -> CreateInvoiceCommand:
    return CreateInvoiceCommandSchema.model_validate(payload).to_command()
