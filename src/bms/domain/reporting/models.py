from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CurrencyTotals:
    currency: str
    subtotal_minor: int = 0
    tax_minor: int = 0
    total_minor: int = 0


@dataclass(frozen=True)
class BusinessUnitRevenueRow:
    business_unit: str
    currency: str
    invoice_subtotal_minor: int
    refund_subtotal_minor: int
    net_revenue_minor: int


@dataclass(frozen=True)
class BusinessUnitRevenueReport:
    period_id: str | None
    rows: tuple[BusinessUnitRevenueRow, ...]


@dataclass(frozen=True)
class InvoiceReportRow:
    invoice_id: str
    customer_id: str
    period_id: str
    timestamp: str
    status: str
    payment_method: str
    currency: str
    subtotal_minor: int
    tax_minor: int
    total_minor: int


@dataclass(frozen=True)
class InvoiceReport:
    period_id: str | None
    rows: tuple[InvoiceReportRow, ...]
    totals: tuple[CurrencyTotals, ...]


@dataclass(frozen=True)
class RefundReportRow:
    refund_id: str
    original_invoice_id: str
    period_id: str
    timestamp: str
    status: str
    reason: str
    currency: str
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    journal_id: str
    movement_ids: tuple[str, ...]


@dataclass(frozen=True)
class RefundReport:
    period_id: str | None
    rows: tuple[RefundReportRow, ...]
    totals: tuple[CurrencyTotals, ...]


@dataclass(frozen=True)
class RefundAvailabilityReportRow:
    invoice_id: str
    period_id: str
    item_id: str
    description: str
    currency: str
    unit_price_minor: int
    original_quantity: int
    refunded_quantity: int
    remaining_quantity: int
    original_subtotal_minor: int
    refunded_subtotal_minor: int
    remaining_subtotal_minor: int


@dataclass(frozen=True)
class RefundAvailabilityReport:
    period_id: str | None
    rows: tuple[RefundAvailabilityReportRow, ...]


@dataclass(frozen=True)
class StockReportRow:
    item_id: str
    sku: str
    name: str
    business_unit: str
    active: bool
    quantity_on_hand: int
    low_stock: bool


@dataclass(frozen=True)
class StockReport:
    low_stock_threshold: int
    rows: tuple[StockReportRow, ...]


@dataclass(frozen=True)
class LedgerReportRow:
    period_id: str
    account_code: str
    account_name: str
    account_type: str
    debit_total_minor: int
    credit_total_minor: int
    balance_minor: int
    currency: str


@dataclass(frozen=True)
class LedgerReport:
    period_id: str
    rows: tuple[LedgerReportRow, ...]


@dataclass(frozen=True)
class ProfitAndLossReport:
    period_id: str
    currency: str
    revenue_minor: int
    contra_revenue_minor: int
    net_revenue_minor: int
    expense_minor: int
    net_income_minor: int


@dataclass(frozen=True)
class TaxReport:
    period_id: str
    currency: str
    invoice_tax_collected_minor: int
    tax_payable_balance_minor: int


@dataclass(frozen=True)
class TrialBalanceReport:
    period_id: str
    debit_total_minor: int
    credit_total_minor: int
    is_balanced: bool
