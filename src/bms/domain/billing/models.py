from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceLineCommand:
    item_id: str
    quantity: int
    unit_price_minor: int
    description: str = ""


@dataclass(frozen=True)
class CreateInvoiceCommand:
    invoice_id: str
    customer_id: str
    period_id: str
    timestamp: str
    actor_id: str
    correlation_id: str
    payment_method: str
    currency: str
    lines: tuple[InvoiceLineCommand, ...]


@dataclass(frozen=True)
class InvoiceResult:
    invoice_id: str
    journal_id: str
    movement_ids: tuple[str, ...]
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    currency: str
