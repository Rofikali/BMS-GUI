from __future__ import annotations

from typing import Any

from bms.domain.accounting import AccountingService
from bms.domain.inventory import InventoryService

from bms.domain.reporting.models import (
    CurrencyTotals,
    InvoiceReport,
    InvoiceReportRow,
    LedgerReport,
    LedgerReportRow,
    StockReport,
    StockReportRow,
    TaxReport,
    TrialBalanceReport,
)
from bms.domain.reporting.schemas import (
    InvoiceReportSchema,
    LedgerReportSchema,
    StockReportSchema,
    TaxReportSchema,
    TrialBalanceReportSchema,
    dump_report_schema,
)
from bms.storage.file_store.core_store import CoreFileStore


class ReportingError(ValueError):
    pass


class ReportingService:
    def __init__(self, store: CoreFileStore) -> None:
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
                active=item.active,
                quantity_on_hand=quantities.get(item.item_id, 0),
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

    def export_stock_report(self, *, low_stock_threshold: int = 0) -> dict[str, Any]:
        return dump_report_schema(StockReportSchema.from_report(self.get_stock_report(low_stock_threshold=low_stock_threshold)))

    def export_ledger_report(self, period_id: str) -> dict[str, Any]:
        return dump_report_schema(LedgerReportSchema.from_report(self.get_ledger_report(period_id)))

    def export_tax_report(self, period_id: str, *, currency: str = "INR") -> dict[str, Any]:
        return dump_report_schema(TaxReportSchema.from_report(self.get_tax_report(period_id, currency=currency)))

    def export_trial_balance_report(self, period_id: str) -> dict[str, Any]:
        return dump_report_schema(TrialBalanceReportSchema.from_report(self.get_trial_balance_report(period_id)))


def _str_payload(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReportingError(f"stored report payload field {key} is not a non-empty string")
    return value


def _int_payload(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportingError(f"stored report payload field {key} is not an integer")
    return value
