from __future__ import annotations

from typing import Protocol

from bms.domain.billing.models import CreateInvoiceCommand, CreateRefundCommand, InvoiceResult, RefundResult


class BillingPort(Protocol):
    def create_invoice(self, command: CreateInvoiceCommand) -> InvoiceResult:
        raise NotImplementedError

    def create_refund(self, command: CreateRefundCommand) -> RefundResult:
        raise NotImplementedError
