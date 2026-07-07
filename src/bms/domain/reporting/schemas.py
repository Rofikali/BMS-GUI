from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from bms.domain.reporting.models import (
    BusinessUnitRevenueReport,
    BusinessUnitRevenueRow,
    CurrencyTotals,
    InvoiceReport,
    InvoiceReportRow,
    LedgerReport,
    LedgerReportRow,
    ProfitAndLossReport,
    RefundAvailabilityReport,
    RefundAvailabilityReportRow,
    RefundReport,
    RefundReportRow,
    StockReport,
    StockReportRow,
    TaxReport,
    TrialBalanceReport,
)


class _ReportSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class CurrencyTotalsSchema(_ReportSchema):
    currency: str
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)


class BusinessUnitRevenueRowSchema(_ReportSchema):
    business_unit: str
    currency: str
    invoice_subtotal_minor: int = Field(ge=0)
    refund_subtotal_minor: int = Field(ge=0)
    net_revenue_minor: int


class BusinessUnitRevenueReportSchema(_ReportSchema):
    period_id: str | None
    rows: tuple[BusinessUnitRevenueRowSchema, ...]

    @classmethod
    def from_report(cls, report: BusinessUnitRevenueReport) -> BusinessUnitRevenueReportSchema:
        return cls.model_validate(report)


class InvoiceReportRowSchema(_ReportSchema):
    invoice_id: str
    customer_id: str
    period_id: str
    timestamp: str
    status: str
    payment_method: str
    currency: str
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)


class InvoiceReportSchema(_ReportSchema):
    period_id: str | None
    rows: tuple[InvoiceReportRowSchema, ...]
    totals: tuple[CurrencyTotalsSchema, ...]

    @classmethod
    def from_report(cls, report: InvoiceReport) -> InvoiceReportSchema:
        return cls.model_validate(report)


class RefundReportRowSchema(_ReportSchema):
    refund_id: str
    original_invoice_id: str
    period_id: str
    timestamp: str
    status: str
    reason: str
    currency: str
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)
    journal_id: str
    movement_ids: tuple[str, ...]


class RefundReportSchema(_ReportSchema):
    period_id: str | None
    rows: tuple[RefundReportRowSchema, ...]
    totals: tuple[CurrencyTotalsSchema, ...]

    @classmethod
    def from_report(cls, report: RefundReport) -> RefundReportSchema:
        return cls.model_validate(report)


class RefundAvailabilityReportRowSchema(_ReportSchema):
    invoice_id: str
    period_id: str
    item_id: str
    description: str
    currency: str
    unit_price_minor: int = Field(ge=0)
    original_quantity: int = Field(ge=0)
    refunded_quantity: int = Field(ge=0)
    remaining_quantity: int = Field(ge=0)
    original_subtotal_minor: int = Field(ge=0)
    refunded_subtotal_minor: int = Field(ge=0)
    remaining_subtotal_minor: int = Field(ge=0)


class RefundAvailabilityReportSchema(_ReportSchema):
    period_id: str | None
    rows: tuple[RefundAvailabilityReportRowSchema, ...]

    @classmethod
    def from_report(cls, report: RefundAvailabilityReport) -> RefundAvailabilityReportSchema:
        return cls.model_validate(report)


class StockReportRowSchema(_ReportSchema):
    item_id: str
    sku: str
    name: str
    business_unit: str
    active: bool
    quantity_on_hand: int
    average_unit_cost_minor: int = Field(ge=0)
    inventory_value_minor: int
    low_stock: bool


class StockReportSchema(_ReportSchema):
    low_stock_threshold: int = Field(ge=0)
    rows: tuple[StockReportRowSchema, ...]

    @classmethod
    def from_report(cls, report: StockReport) -> StockReportSchema:
        return cls.model_validate(report)


class LedgerReportRowSchema(_ReportSchema):
    period_id: str
    account_code: str
    account_name: str
    account_type: str
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)
    balance_minor: int
    currency: str


class LedgerReportSchema(_ReportSchema):
    period_id: str
    rows: tuple[LedgerReportRowSchema, ...]

    @classmethod
    def from_report(cls, report: LedgerReport) -> LedgerReportSchema:
        return cls.model_validate(report)


class ProfitAndLossReportSchema(_ReportSchema):
    period_id: str
    currency: str
    revenue_minor: int = Field(ge=0)
    contra_revenue_minor: int = Field(ge=0)
    net_revenue_minor: int
    cogs_minor: int = Field(ge=0)
    gross_profit_minor: int
    expense_minor: int = Field(ge=0)
    operating_expense_minor: int = Field(ge=0)
    net_income_minor: int

    @classmethod
    def from_report(cls, report: ProfitAndLossReport) -> ProfitAndLossReportSchema:
        return cls.model_validate(report)


class TaxReportSchema(_ReportSchema):
    period_id: str
    currency: str
    invoice_tax_collected_minor: int = Field(ge=0)
    tax_payable_balance_minor: int

    @classmethod
    def from_report(cls, report: TaxReport) -> TaxReportSchema:
        return cls.model_validate(report)


class TrialBalanceReportSchema(_ReportSchema):
    period_id: str
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)
    is_balanced: bool

    @classmethod
    def from_report(cls, report: TrialBalanceReport) -> TrialBalanceReportSchema:
        return cls.model_validate(report)


def dump_report_schema(schema: BaseModel) -> dict[str, Any]:
    return schema.model_dump(mode="json")
