from __future__ import annotations

from dataclasses import dataclass

from bms.domain.billing.models import CreateInvoiceCommand, CreateRefundCommand, InvoiceResult, RefundResult
from bms.domain.billing.ports import BillingPort


@dataclass(frozen=True)
class CreateInvoiceUseCase:
    billing: BillingPort

    def execute(self, command: CreateInvoiceCommand) -> InvoiceResult:
        return self.billing.create_invoice(command)


@dataclass(frozen=True)
class CreateRefundUseCase:
    billing: BillingPort

    def execute(self, command: CreateRefundCommand) -> RefundResult:
        return self.billing.create_refund(command)
