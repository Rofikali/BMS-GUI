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


@dataclass(frozen=True)
class RefundLineCommand:
    item_id: str
    quantity: int
    unit_price_minor: int
    description: str = ""
    restock: bool = True


@dataclass(frozen=True)
class CreateRefundCommand:
    refund_id: str
    original_invoice_id: str
    period_id: str
    timestamp: str
    actor_id: str
    correlation_id: str
    currency: str
    reason: str
    lines: tuple[RefundLineCommand, ...]


@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    original_invoice_id: str
    journal_id: str
    movement_ids: tuple[str, ...]
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    currency: str
