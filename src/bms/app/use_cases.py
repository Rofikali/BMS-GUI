from __future__ import annotations

from dataclasses import dataclass

from bms.domain.accounting import JournalLine, PostJournalCommand
from bms.domain.accounting.ports import AccountingPort
from bms.domain.billing.models import CreateInvoiceCommand, CreateRefundCommand, InvoiceResult, RefundResult
from bms.domain.billing.ports import BillingPort
from bms.domain.inventory.models import StockMovementCommand, StockMovementResult
from bms.domain.inventory.ports import InventoryPort
from bms.domain.reconciliation import ReconciliationService


class PeriodCloseError(ValueError):
    pass


@dataclass(frozen=True)
class InventoryPostingAccounts:
    inventory: str = "1200"
    owner_equity: str = "3000"
    inventory_adjustment_expense: str = "5100"


@dataclass(frozen=True)
class CommitStockMovementUseCase:
    inventory: InventoryPort
    accounting: AccountingPort
    posting_accounts: InventoryPostingAccounts = InventoryPostingAccounts()

    def execute(self, command: StockMovementCommand) -> StockMovementResult:
        period_id = command.period_id or _period_id_from_timestamp(command.timestamp)
        if self.accounting.is_period_closed(period_id):
            raise ValueError(f"period {period_id} is closed")

        result = self.inventory.commit_movement(command)
        if result.value_delta_minor:
            self.accounting.post_journal(
                PostJournalCommand(
                    journal_id=f"jrn_inventory_{command.movement_id}",
                    period_id=period_id,
                    timestamp=command.timestamp,
                    actor_id=command.actor_id,
                    source_module="inventory",
                    source_document_id=command.source_document_id,
                    correlation_id=command.correlation_id,
                    description=f"Inventory movement {command.movement_id}",
                    lines=self._journal_lines(result),
                )
            )
        return result

    def _journal_lines(self, result: StockMovementResult) -> tuple[JournalLine, ...]:
        accounts = self.posting_accounts
        if result.value_delta_minor > 0:
            return (
                JournalLine(accounts.inventory, debit_minor=result.value_delta_minor),
                JournalLine(accounts.owner_equity, credit_minor=result.value_delta_minor),
            )
        value_minor = abs(result.value_delta_minor)
        return (
            JournalLine(accounts.inventory_adjustment_expense, debit_minor=value_minor),
            JournalLine(accounts.inventory, credit_minor=value_minor),
        )


@dataclass(frozen=True)
class ClosePeriodUseCase:
    accounting: AccountingPort
    reconciliation: ReconciliationService

    def execute(
        self,
        period_id: str,
        *,
        actor_id: str,
        closed_at: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        report = self.reconciliation.get_reconciliation_report(period_id)
        if not report.passed:
            failed = ", ".join(check.name for check in report.checks if not check.passed)
            raise PeriodCloseError(f"period {period_id} cannot close; reconciliation failed: {failed}")
        self.accounting.close_period(
            period_id,
            actor_id=actor_id,
            closed_at=closed_at,
            correlation_id=correlation_id,
        )


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


def _period_id_from_timestamp(timestamp: str) -> str:
    if len(timestamp) < 7:
        raise ValueError("stock movement timestamp cannot be converted to an accounting period")
    return f"FY{timestamp[:7]}"
