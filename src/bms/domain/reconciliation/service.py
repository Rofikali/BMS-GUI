from __future__ import annotations

from bms.domain.accounting import AccountingService
from bms.domain.inventory import InventoryService
from bms.domain.reconciliation.models import ReconciliationCheck, ReconciliationReport
from bms.storage.ports import DurableStorePort


class ReconciliationError(ValueError):
    pass


class ReconciliationService:
    def __init__(self, store: DurableStorePort) -> None:
        self.store = store

    def get_reconciliation_report(self, period_id: str) -> ReconciliationReport:
        if not period_id:
            raise ReconciliationError("period_id is required")

        accounting = AccountingService(self.store)
        balances = accounting.get_ledger_balances(period_id)
        checks = (
            _check(
                "inventory_subledger_to_ledger",
                expected_minor=InventoryService(self.store).get_inventory_value_delta_minor(period_id),
                actual_minor=_balance(balances, "1200"),
            ),
            _check(
                "tax_report_to_tax_payable",
                expected_minor=_invoice_tax_minor(self.store, period_id) - _refund_tax_minor(self.store, period_id),
                actual_minor=_balance(balances, "2100"),
            ),
            _check(
                "sales_report_to_sales_revenue",
                expected_minor=_invoice_subtotal_minor(self.store, period_id),
                actual_minor=_credit_total(balances, "4000"),
            ),
            _check(
                "refund_report_to_sales_returns",
                expected_minor=_refund_subtotal_minor(self.store, period_id),
                actual_minor=_debit_total(balances, "4100"),
            ),
            _check(
                "billing_cogs_to_cogs_ledger",
                expected_minor=_invoice_cogs_minor(self.store, period_id) - _refund_cogs_minor(self.store, period_id),
                actual_minor=_balance(balances, "5000"),
            ),
        )
        return ReconciliationReport(period_id=period_id, checks=checks)

    def export_reconciliation_report(self, period_id: str) -> dict[str, object]:
        from bms.domain.reconciliation.schemas import ReconciliationReportSchema, dump_reconciliation_schema

        return dump_reconciliation_schema(
            ReconciliationReportSchema.from_report(self.get_reconciliation_report(period_id))
        )


def _check(name: str, *, expected_minor: int, actual_minor: int) -> ReconciliationCheck:
    difference_minor = actual_minor - expected_minor
    return ReconciliationCheck(
        name=name,
        expected_minor=expected_minor,
        actual_minor=actual_minor,
        difference_minor=difference_minor,
        passed=difference_minor == 0,
    )


def _balance(balances: dict[str, object], account_code: str) -> int:
    balance = balances.get(account_code)
    if balance is None:
        return 0
    return int(getattr(balance, "balance_minor"))


def _debit_total(balances: dict[str, object], account_code: str) -> int:
    balance = balances.get(account_code)
    if balance is None:
        return 0
    return int(getattr(balance, "debit_total_minor"))


def _credit_total(balances: dict[str, object], account_code: str) -> int:
    balance = balances.get(account_code)
    if balance is None:
        return 0
    return int(getattr(balance, "credit_total_minor"))


def _invoice_subtotal_minor(store: DurableStorePort, period_id: str) -> int:
    return sum(_int_payload(payload, "subtotal_minor") for payload in _period_payloads(store, store.invoices, period_id))


def _invoice_tax_minor(store: DurableStorePort, period_id: str) -> int:
    return sum(_int_payload(payload, "tax_minor") for payload in _period_payloads(store, store.invoices, period_id))


def _refund_subtotal_minor(store: DurableStorePort, period_id: str) -> int:
    return sum(_int_payload(payload, "subtotal_minor") for payload in _period_payloads(store, store.refunds, period_id))


def _refund_tax_minor(store: DurableStorePort, period_id: str) -> int:
    return sum(_int_payload(payload, "tax_minor") for payload in _period_payloads(store, store.refunds, period_id))


def _invoice_cogs_minor(store: DurableStorePort, period_id: str) -> int:
    invoice_periods = {
        _str_payload(payload, "invoice_id"): _str_payload(payload, "period_id")
        for payload in store.read_payloads(store.invoices)
    }
    return sum(
        _int_payload(payload, "cogs_minor")
        for payload in store.read_payloads(store.invoice_lines)
        if invoice_periods.get(_str_payload(payload, "invoice_id")) == period_id
    )


def _refund_cogs_minor(store: DurableStorePort, period_id: str) -> int:
    refund_periods = {
        _str_payload(payload, "refund_id"): _str_payload(payload, "period_id")
        for payload in store.read_payloads(store.refunds)
    }
    return sum(
        _int_payload(payload, "cogs_minor")
        for payload in store.read_payloads(store.refund_lines)
        if refund_periods.get(_str_payload(payload, "refund_id")) == period_id
    )


def _period_payloads(store: DurableStorePort, path: object, period_id: str) -> tuple[dict[str, object], ...]:
    return tuple(
        payload
        for payload in store.read_payloads(path)
        if _str_payload(payload, "period_id") == period_id
    )


def _str_payload(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ReconciliationError(f"stored reconciliation payload field {key} is not a non-empty string")
    return value


def _int_payload(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReconciliationError(f"stored reconciliation payload field {key} is not an integer")
    return value
