from __future__ import annotations

from typing import Any

from bms.domain.accounting import AccountingService
from bms.domain.inventory import InventoryService

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
from bms.domain.reporting.schemas import (
    BusinessUnitRevenueReportSchema,
    InvoiceReportSchema,
    LedgerReportSchema,
    ProfitAndLossReportSchema,
    RefundAvailabilityReportSchema,
    RefundReportSchema,
    StockReportSchema,
    TaxReportSchema,
    TrialBalanceReportSchema,
    dump_report_schema,
)
from bms.storage.ports import DurableStorePort


class ReportingError(ValueError):
    pass


class ReportingService:
    def __init__(self, store: DurableStorePort) -> None:
        self.store = store

    def get_invoice_report(self, period_id: str | None = None) -> InvoiceReport:
        rows = []
        totals_by_currency: dict[str, dict[str, int]] = {}
        for payload in self.store.read_payloads(self.store.invoices):
            invoice_period_id = _str_payload(payload, "period_id")
            if period_id is not None and invoice_period_id != period_id:
                continue

            currency = _str_payload(payload, "currency")
            subtotal_minor = _int_payload(payload, "subtotal_minor")
            tax_minor = _int_payload(payload, "tax_minor")
            total_minor = _int_payload(payload, "total_minor")
            rows.append(
                InvoiceReportRow(
                    invoice_id=_str_payload(payload, "invoice_id"),
                    customer_id=_str_payload(payload, "customer_id"),
                    period_id=invoice_period_id,
                    timestamp=_str_payload(payload, "timestamp"),
                    status=_str_payload(payload, "status"),
                    payment_method=_str_payload(payload, "payment_method"),
                    currency=currency,
                    subtotal_minor=subtotal_minor,
                    tax_minor=tax_minor,
                    total_minor=total_minor,
                )
            )
            totals = totals_by_currency.setdefault(currency, {"subtotal": 0, "tax": 0, "total": 0})
            totals["subtotal"] += subtotal_minor
            totals["tax"] += tax_minor
            totals["total"] += total_minor

        return InvoiceReport(
            period_id=period_id,
            rows=tuple(sorted(rows, key=lambda row: (row.timestamp, row.invoice_id))),
            totals=tuple(
                CurrencyTotals(
                    currency=currency,
                    subtotal_minor=totals["subtotal"],
                    tax_minor=totals["tax"],
                    total_minor=totals["total"],
                )
                for currency, totals in sorted(totals_by_currency.items())
            ),
        )

    def get_refund_report(self, period_id: str | None = None) -> RefundReport:
        rows = []
        totals_by_currency: dict[str, dict[str, int]] = {}
        for payload in self.store.read_payloads(self.store.refunds):
            refund_period_id = _str_payload(payload, "period_id")
            if period_id is not None and refund_period_id != period_id:
                continue

            currency = _str_payload(payload, "currency")
            subtotal_minor = _int_payload(payload, "subtotal_minor")
            tax_minor = _int_payload(payload, "tax_minor")
            total_minor = _int_payload(payload, "total_minor")
            rows.append(
                RefundReportRow(
                    refund_id=_str_payload(payload, "refund_id"),
                    original_invoice_id=_str_payload(payload, "original_invoice_id"),
                    period_id=refund_period_id,
                    timestamp=_str_payload(payload, "timestamp"),
                    status=_str_payload(payload, "status"),
                    reason=_str_payload(payload, "reason"),
                    currency=currency,
                    subtotal_minor=subtotal_minor,
                    tax_minor=tax_minor,
                    total_minor=total_minor,
                    journal_id=_str_payload(payload, "journal_id"),
                    movement_ids=_string_tuple_payload(payload, "movement_ids"),
                )
            )
            totals = totals_by_currency.setdefault(currency, {"subtotal": 0, "tax": 0, "total": 0})
            totals["subtotal"] += subtotal_minor
            totals["tax"] += tax_minor
            totals["total"] += total_minor

        return RefundReport(
            period_id=period_id,
            rows=tuple(sorted(rows, key=lambda row: (row.timestamp, row.refund_id))),
            totals=tuple(
                CurrencyTotals(
                    currency=currency,
                    subtotal_minor=totals["subtotal"],
                    tax_minor=totals["tax"],
                    total_minor=totals["total"],
                )
                for currency, totals in sorted(totals_by_currency.items())
            ),
        )

    def get_refund_availability_report(self, period_id: str | None = None) -> RefundAvailabilityReport:
        invoice_periods: dict[str, str] = {}
        for payload in self.store.read_payloads(self.store.invoices):
            invoice_id = _str_payload(payload, "invoice_id")
            invoice_periods[invoice_id] = _str_payload(payload, "period_id")

        original_lines: dict[tuple[str, str, int], dict[str, object]] = {}
        for payload in self.store.read_payloads(self.store.invoice_lines):
            invoice_id = _str_payload(payload, "invoice_id")
            invoice_period_id = invoice_periods.get(invoice_id)
            if invoice_period_id is None:
                raise ReportingError(f"invoice line references unknown invoice {invoice_id}")
            if period_id is not None and invoice_period_id != period_id:
                continue

            item_id = _str_payload(payload, "item_id")
            unit_price_minor = _int_payload(payload, "unit_price_minor")
            key = (invoice_id, item_id, unit_price_minor)
            line = original_lines.setdefault(
                key,
                {
                    "invoice_id": invoice_id,
                    "period_id": invoice_period_id,
                    "item_id": item_id,
                    "description": _text_payload(payload, "description"),
                    "currency": _str_payload(payload, "currency"),
                    "unit_price_minor": unit_price_minor,
                    "quantity": 0,
                },
            )
            line["quantity"] = int(line["quantity"]) + _int_payload(payload, "quantity")

        refund_invoice_by_id = {
            _str_payload(payload, "refund_id"): _str_payload(payload, "original_invoice_id")
            for payload in self.store.read_payloads(self.store.refunds)
        }
        refunded_quantities: dict[tuple[str, str, int], int] = {}
        for payload in self.store.read_payloads(self.store.refund_lines):
            refund_id = _str_payload(payload, "refund_id")
            original_invoice_id = refund_invoice_by_id.get(refund_id)
            if original_invoice_id is None:
                raise ReportingError(f"refund line references unknown refund {refund_id}")
            invoice_period_id = invoice_periods.get(original_invoice_id)
            if invoice_period_id is None:
                raise ReportingError(f"refund {refund_id} references unknown invoice {original_invoice_id}")
            if period_id is not None and invoice_period_id != period_id:
                continue

            key = (
                original_invoice_id,
                _str_payload(payload, "item_id"),
                _int_payload(payload, "unit_price_minor"),
            )
            refunded_quantities[key] = refunded_quantities.get(key, 0) + _int_payload(payload, "quantity")

        rows = []
        for key, line in original_lines.items():
            invoice_id, item_id, unit_price_minor = key
            original_quantity = int(line["quantity"])
            refunded_quantity = refunded_quantities.get(key, 0)
            remaining_quantity = max(original_quantity - refunded_quantity, 0)
            rows.append(
                RefundAvailabilityReportRow(
                    invoice_id=invoice_id,
                    period_id=str(line["period_id"]),
                    item_id=item_id,
                    description=str(line["description"]),
                    currency=str(line["currency"]),
                    unit_price_minor=unit_price_minor,
                    original_quantity=original_quantity,
                    refunded_quantity=refunded_quantity,
                    remaining_quantity=remaining_quantity,
                    original_subtotal_minor=original_quantity * unit_price_minor,
                    refunded_subtotal_minor=refunded_quantity * unit_price_minor,
                    remaining_subtotal_minor=remaining_quantity * unit_price_minor,
                )
            )

        return RefundAvailabilityReport(
            period_id=period_id,
            rows=tuple(sorted(rows, key=lambda row: (row.invoice_id, row.item_id, row.unit_price_minor))),
        )

    def get_business_unit_revenue_report(
        self,
        period_id: str | None = None,
        *,
        currency: str = "INR",
    ) -> BusinessUnitRevenueReport:
        invoice_periods = {
            _str_payload(payload, "invoice_id"): _str_payload(payload, "period_id")
            for payload in self.store.read_payloads(self.store.invoices)
        }
        refund_periods = {
            _str_payload(payload, "refund_id"): _str_payload(payload, "period_id")
            for payload in self.store.read_payloads(self.store.refunds)
        }
        totals: dict[str, dict[str, int]] = {}
        for payload in self.store.read_payloads(self.store.invoice_lines):
            invoice_id = _str_payload(payload, "invoice_id")
            invoice_period_id = invoice_periods.get(invoice_id)
            if invoice_period_id is None:
                raise ReportingError(f"invoice line references unknown invoice {invoice_id}")
            if period_id is not None and invoice_period_id != period_id:
                continue
            if _str_payload(payload, "currency") != currency:
                continue
            business_unit = _business_unit_payload(payload)
            unit_totals = totals.setdefault(business_unit, {"invoice": 0, "refund": 0})
            unit_totals["invoice"] += _int_payload(payload, "line_subtotal_minor")

        for payload in self.store.read_payloads(self.store.refund_lines):
            refund_id = _str_payload(payload, "refund_id")
            refund_period_id = refund_periods.get(refund_id)
            if refund_period_id is None:
                raise ReportingError(f"refund line references unknown refund {refund_id}")
            if period_id is not None and refund_period_id != period_id:
                continue
            if _str_payload(payload, "currency") != currency:
                continue
            business_unit = _business_unit_payload(payload)
            unit_totals = totals.setdefault(business_unit, {"invoice": 0, "refund": 0})
            unit_totals["refund"] += _int_payload(payload, "line_subtotal_minor")

        return BusinessUnitRevenueReport(
            period_id=period_id,
            rows=tuple(
                BusinessUnitRevenueRow(
                    business_unit=business_unit,
                    currency=currency,
                    invoice_subtotal_minor=unit_totals["invoice"],
                    refund_subtotal_minor=unit_totals["refund"],
                    net_revenue_minor=unit_totals["invoice"] - unit_totals["refund"],
                )
                for business_unit, unit_totals in sorted(totals.items())
            ),
        )

    def get_stock_report(self, *, low_stock_threshold: int = 0) -> StockReport:
        if low_stock_threshold < 0:
            raise ReportingError("low_stock_threshold cannot be negative")

        inventory = InventoryService(self.store)
        quantities = inventory.get_all_stock_on_hand()
        rows = [
            StockReportRow(
                item_id=item.item_id,
                sku=item.sku,
                name=item.name,
                business_unit=item.business_unit,
                active=item.active,
                quantity_on_hand=quantities.get(item.item_id, 0),
                average_unit_cost_minor=inventory.get_weighted_average_unit_cost_minor(item.item_id),
                inventory_value_minor=inventory.get_inventory_value_minor(item.item_id),
                low_stock=quantities.get(item.item_id, 0) <= low_stock_threshold,
            )
            for item in inventory.get_items().values()
        ]
        return StockReport(
            low_stock_threshold=low_stock_threshold,
            rows=tuple(sorted(rows, key=lambda row: row.sku)),
        )

    def get_ledger_report(self, period_id: str) -> LedgerReport:
        accounting = AccountingService(self.store)
        rows = [
            LedgerReportRow(
                period_id=balance.period_id,
                account_code=balance.account_code,
                account_name=balance.account_name,
                account_type=balance.account_type.value,
                debit_total_minor=balance.debit_total_minor,
                credit_total_minor=balance.credit_total_minor,
                balance_minor=balance.balance_minor,
                currency=balance.currency,
            )
            for balance in accounting.get_ledger_balances(period_id).values()
        ]
        return LedgerReport(period_id=period_id, rows=tuple(rows))

    def get_profit_and_loss_report(
        self,
        period_id: str,
        *,
        currency: str = "INR",
    ) -> ProfitAndLossReport:
        balances = AccountingService(self.store).get_ledger_balances(period_id)
        revenue_minor = 0
        contra_revenue_minor = 0
        expense_minor = 0
        cogs_minor = 0
        for balance in balances.values():
            if balance.currency != currency:
                continue
            if balance.account_type.value == "revenue":
                revenue_minor += balance.credit_total_minor
                contra_revenue_minor += balance.debit_total_minor
            elif balance.account_type.value == "expense":
                net_expense_minor = max(
                    balance.debit_total_minor - balance.credit_total_minor,
                    0,
                )
                expense_minor += net_expense_minor
                if balance.account_code == "5000":
                    cogs_minor += net_expense_minor
        net_revenue_minor = revenue_minor - contra_revenue_minor
        operating_expense_minor = expense_minor - cogs_minor
        gross_profit_minor = net_revenue_minor - cogs_minor
        return ProfitAndLossReport(
            period_id=period_id,
            currency=currency,
            revenue_minor=revenue_minor,
            contra_revenue_minor=contra_revenue_minor,
            net_revenue_minor=net_revenue_minor,
            cogs_minor=cogs_minor,
            gross_profit_minor=gross_profit_minor,
            expense_minor=expense_minor,
            operating_expense_minor=operating_expense_minor,
            net_income_minor=gross_profit_minor - operating_expense_minor,
        )

    def get_tax_report(self, period_id: str, *, currency: str = "INR") -> TaxReport:
        invoice_report = self.get_invoice_report(period_id)
        invoice_tax_collected_minor = sum(total.tax_minor for total in invoice_report.totals if total.currency == currency)
        tax_payable_balance_minor = 0
        balances = AccountingService(self.store).get_ledger_balances(period_id)
        tax_payable = balances.get("2100")
        if tax_payable is not None and tax_payable.currency == currency:
            tax_payable_balance_minor = tax_payable.balance_minor

        return TaxReport(
            period_id=period_id,
            currency=currency,
            invoice_tax_collected_minor=invoice_tax_collected_minor,
            tax_payable_balance_minor=tax_payable_balance_minor,
        )

    def get_trial_balance_report(self, period_id: str) -> TrialBalanceReport:
        trial_balance = AccountingService(self.store).get_trial_balance(period_id)
        return TrialBalanceReport(
            period_id=trial_balance.period_id,
            debit_total_minor=trial_balance.debit_total_minor,
            credit_total_minor=trial_balance.credit_total_minor,
            is_balanced=trial_balance.is_balanced,
        )

    def export_invoice_report(self, period_id: str | None = None) -> dict[str, Any]:
        return dump_report_schema(InvoiceReportSchema.from_report(self.get_invoice_report(period_id)))

    def export_refund_report(self, period_id: str | None = None) -> dict[str, Any]:
        return dump_report_schema(RefundReportSchema.from_report(self.get_refund_report(period_id)))

    def export_refund_availability_report(self, period_id: str | None = None) -> dict[str, Any]:
        return dump_report_schema(
            RefundAvailabilityReportSchema.from_report(self.get_refund_availability_report(period_id))
        )

    def export_business_unit_revenue_report(
        self,
        period_id: str | None = None,
        *,
        currency: str = "INR",
    ) -> dict[str, Any]:
        return dump_report_schema(
            BusinessUnitRevenueReportSchema.from_report(
                self.get_business_unit_revenue_report(period_id, currency=currency)
            )
        )

    def export_stock_report(self, *, low_stock_threshold: int = 0) -> dict[str, Any]:
        return dump_report_schema(StockReportSchema.from_report(self.get_stock_report(low_stock_threshold=low_stock_threshold)))

    def export_ledger_report(self, period_id: str) -> dict[str, Any]:
        return dump_report_schema(LedgerReportSchema.from_report(self.get_ledger_report(period_id)))

    def export_profit_and_loss_report(self, period_id: str, *, currency: str = "INR") -> dict[str, Any]:
        return dump_report_schema(
            ProfitAndLossReportSchema.from_report(
                self.get_profit_and_loss_report(period_id, currency=currency)
            )
        )

    def export_tax_report(self, period_id: str, *, currency: str = "INR") -> dict[str, Any]:
        return dump_report_schema(TaxReportSchema.from_report(self.get_tax_report(period_id, currency=currency)))

    def export_trial_balance_report(self, period_id: str) -> dict[str, Any]:
        return dump_report_schema(TrialBalanceReportSchema.from_report(self.get_trial_balance_report(period_id)))


def _str_payload(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReportingError(f"stored report payload field {key} is not a non-empty string")
    return value


def _text_payload(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ReportingError(f"stored report payload field {key} is not a string")
    return value


def _business_unit_payload(payload: dict[str, object]) -> str:
    value = payload.get("business_unit", "retail")
    if not isinstance(value, str) or not value:
        raise ReportingError("stored report payload field business_unit is not a non-empty string")
    return value


def _int_payload(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportingError(f"stored report payload field {key} is not an integer")
    return value


def _string_tuple_payload(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ReportingError(f"stored report payload field {key} is not a string list")
    return tuple(value)
