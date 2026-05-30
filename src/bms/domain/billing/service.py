from __future__ import annotations

from uuid import uuid4

from bms.domain.accounting import AccountingService, JournalLine, PostJournalCommand
from bms.domain.billing.models import CreateInvoiceCommand, CreateRefundCommand, InvoiceResult, RefundResult
from bms.domain.inventory import InventoryService, StockMovementCommand, StockMovementType
from bms.storage.file_store.core_store import CoreFileStore


class BillingError(ValueError):
    pass


class BillingService:
    def __init__(
        self,
        store: CoreFileStore,
        inventory: InventoryService,
        accounting: AccountingService,
        *,
        tax_rate_basis_points: int = 1800,
    ) -> None:
        self.store = store
        self.inventory = inventory
        self.accounting = accounting
        self.tax_rate_basis_points = tax_rate_basis_points

    def create_invoice(self, command: CreateInvoiceCommand) -> InvoiceResult:
        self._validate_command(command)
        self._reject_duplicate_invoice(command.invoice_id)
        if self.accounting.is_period_closed(command.period_id):
            raise BillingError(f"period {command.period_id} is closed")

        subtotal_minor = sum(line.quantity * line.unit_price_minor for line in command.lines)
        tax_minor = _calculate_tax(subtotal_minor, self.tax_rate_basis_points)
        total_minor = subtotal_minor + tax_minor
        movement_ids = tuple(f"mov_{command.invoice_id}_{index}" for index, _line in enumerate(command.lines, start=1))
        journal_id = f"jrn_{command.invoice_id}"

        self._validate_stock_available(command)

        journal_lines = [
            JournalLine("1000", debit_minor=total_minor, currency=command.currency, memo=f"Invoice {command.invoice_id}"),
            JournalLine("4000", credit_minor=subtotal_minor, currency=command.currency, memo=f"Invoice {command.invoice_id}"),
        ]
        if tax_minor:
            journal_lines.append(
                JournalLine("2100", credit_minor=tax_minor, currency=command.currency, memo=f"Invoice {command.invoice_id} tax")
            )

        parent_transaction_id = f"txn_billing_create_invoice_{command.invoice_id}_{uuid4().hex}"
        self.store.core.append_wal_pending(
            self.store.wal,
            parent_transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
            {
                "operation": "billing.create_invoice",
                "invoice_id": command.invoice_id,
                "journal_id": journal_id,
                "movement_ids": list(movement_ids),
                "expected_records": {
                    "billing.invoices": 1,
                    "billing.invoice_lines": len(command.lines),
                    "inventory.stock_movements": len(command.lines),
                    "accounting.journal_entries": 1,
                    "accounting.journal_lines": len(journal_lines),
                    "audit.records": len(command.lines) + 2,
                    "business_events": len(command.lines) + 2,
                },
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "currency": command.currency,
            },
        )

        self.accounting.post_journal(
            PostJournalCommand(
                journal_id=journal_id,
                period_id=command.period_id,
                timestamp=command.timestamp,
                actor_id=command.actor_id,
                source_module="billing",
                source_document_id=command.invoice_id,
                correlation_id=command.correlation_id,
                description=f"Invoice {command.invoice_id} sale",
                lines=tuple(journal_lines),
            )
        )

        for index, line in enumerate(command.lines, start=1):
            self.inventory.commit_movement(
                StockMovementCommand(
                    movement_id=movement_ids[index - 1],
                    item_id=line.item_id,
                    movement_type=StockMovementType.STOCK_OUT,
                    quantity_delta=-line.quantity,
                    timestamp=command.timestamp,
                    actor_id=command.actor_id,
                    reason="invoice sale",
                    source_module="billing",
                    source_document_id=command.invoice_id,
                    correlation_id=command.correlation_id,
                )
            )

        self.store.append_record(
            self.store.invoices,
            "billing.invoice",
            command.actor_id,
            command.correlation_id,
            f"invoice_{command.invoice_id}",
            {
                "invoice_id": command.invoice_id,
                "customer_id": command.customer_id,
                "period_id": command.period_id,
                "timestamp": command.timestamp,
                "actor_id": command.actor_id,
                "payment_method": command.payment_method,
                "currency": command.currency,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "journal_id": journal_id,
                "movement_ids": list(movement_ids),
                "correlation_id": command.correlation_id,
                "status": "completed",
            },
            record_id=f"inv_{command.invoice_id}",
            created_at=command.timestamp,
        )
        for index, line in enumerate(command.lines, start=1):
            line_subtotal = line.quantity * line.unit_price_minor
            self.store.append_record(
                self.store.invoice_lines,
                "billing.invoice_line",
                command.actor_id,
                command.correlation_id,
                f"invoice_line_{command.invoice_id}_{index}",
                {
                    "invoice_id": command.invoice_id,
                    "line_no": index,
                    "item_id": line.item_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price_minor": line.unit_price_minor,
                    "line_subtotal_minor": line_subtotal,
                    "currency": command.currency,
                },
                record_id=f"ivl_{command.invoice_id}_{index}",
                created_at=command.timestamp,
            )
        self.store.append_audit_record(
            "billing.invoice_created",
            command.actor_id,
            "invoice",
            command.invoice_id,
            command.correlation_id,
            occurred_at=command.timestamp,
            details={
                "customer_id": command.customer_id,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "line_count": len(command.lines),
            },
            idempotency_key=f"audit_invoice_created_{command.invoice_id}",
        )
        self.store.append_business_event(
            "billing.sale_completed.v1",
            command.actor_id,
            {
                "invoice_id": command.invoice_id,
                "customer_id": command.customer_id,
                "currency": command.currency,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "payment_method": command.payment_method,
                "line_count": len(command.lines),
            },
            correlation_id=command.correlation_id,
            occurred_at=command.timestamp,
            idempotency_key=f"event_sale_completed_{command.invoice_id}",
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            parent_transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
        )
        return InvoiceResult(command.invoice_id, journal_id, movement_ids, subtotal_minor, tax_minor, total_minor, command.currency)

    def create_refund(self, command: CreateRefundCommand) -> RefundResult:
        self._validate_refund_command(command)
        self._reject_duplicate_refund(command.refund_id)
        original_invoice = self._get_invoice(command.original_invoice_id)
        if original_invoice is None:
            raise BillingError(f"original invoice {command.original_invoice_id} was not found")
        if self.accounting.is_period_closed(command.period_id):
            raise BillingError(f"period {command.period_id} is closed")
        if original_invoice.get("currency") != command.currency:
            raise BillingError("refund currency must match original invoice currency")
        self._validate_refund_against_original_invoice(command)

        subtotal_minor = sum(line.quantity * line.unit_price_minor for line in command.lines)
        tax_minor = _calculate_tax(subtotal_minor, self.tax_rate_basis_points)
        total_minor = subtotal_minor + tax_minor
        movement_ids = tuple(
            f"mov_refund_{command.refund_id}_{index}"
            for index, line in enumerate(command.lines, start=1)
            if line.restock
        )
        journal_id = f"jrn_refund_{command.refund_id}"
        journal_lines = [
            JournalLine("4000", debit_minor=subtotal_minor, currency=command.currency, memo=f"Refund {command.refund_id}"),
            JournalLine("1000", credit_minor=total_minor, currency=command.currency, memo=f"Refund {command.refund_id}"),
        ]
        if tax_minor:
            journal_lines.append(
                JournalLine("2100", debit_minor=tax_minor, currency=command.currency, memo=f"Refund {command.refund_id} tax")
            )

        parent_transaction_id = f"txn_billing_create_refund_{command.refund_id}_{uuid4().hex}"
        self.store.core.append_wal_pending(
            self.store.wal,
            parent_transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
            {
                "operation": "billing.create_refund",
                "refund_id": command.refund_id,
                "original_invoice_id": command.original_invoice_id,
                "journal_id": journal_id,
                "movement_ids": list(movement_ids),
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "currency": command.currency,
            },
        )
        self.accounting.post_journal(
            PostJournalCommand(
                journal_id=journal_id,
                period_id=command.period_id,
                timestamp=command.timestamp,
                actor_id=command.actor_id,
                source_module="billing",
                source_document_id=command.refund_id,
                correlation_id=command.correlation_id,
                description=f"Refund {command.refund_id} for invoice {command.original_invoice_id}",
                lines=tuple(journal_lines),
            )
        )

        movement_index = 0
        for line in command.lines:
            if not line.restock:
                continue
            movement_id = movement_ids[movement_index]
            movement_index += 1
            self.inventory.commit_movement(
                StockMovementCommand(
                    movement_id=movement_id,
                    item_id=line.item_id,
                    movement_type=StockMovementType.STOCK_IN,
                    quantity_delta=line.quantity,
                    timestamp=command.timestamp,
                    actor_id=command.actor_id,
                    reason="refund return",
                    source_module="billing",
                    source_document_id=command.refund_id,
                    correlation_id=command.correlation_id,
                )
            )

        self.store.append_record(
            self.store.refunds,
            "billing.refund",
            command.actor_id,
            command.correlation_id,
            f"refund_{command.refund_id}",
            {
                "refund_id": command.refund_id,
                "original_invoice_id": command.original_invoice_id,
                "period_id": command.period_id,
                "timestamp": command.timestamp,
                "actor_id": command.actor_id,
                "currency": command.currency,
                "reason": command.reason,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "journal_id": journal_id,
                "movement_ids": list(movement_ids),
                "correlation_id": command.correlation_id,
                "status": "completed",
            },
            record_id=f"ref_{command.refund_id}",
            created_at=command.timestamp,
        )
        for index, line in enumerate(command.lines, start=1):
            self.store.append_record(
                self.store.refund_lines,
                "billing.refund_line",
                command.actor_id,
                command.correlation_id,
                f"refund_line_{command.refund_id}_{index}",
                {
                    "refund_id": command.refund_id,
                    "line_no": index,
                    "item_id": line.item_id,
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price_minor": line.unit_price_minor,
                    "line_subtotal_minor": line.quantity * line.unit_price_minor,
                    "restock": line.restock,
                    "currency": command.currency,
                },
                record_id=f"rfl_{command.refund_id}_{index}",
                created_at=command.timestamp,
            )
        self.store.append_audit_record(
            "billing.refund_created",
            command.actor_id,
            "refund",
            command.refund_id,
            command.correlation_id,
            occurred_at=command.timestamp,
            details={
                "original_invoice_id": command.original_invoice_id,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "line_count": len(command.lines),
            },
            idempotency_key=f"audit_refund_created_{command.refund_id}",
        )
        self.store.append_business_event(
            "billing.refund_completed.v1",
            command.actor_id,
            {
                "refund_id": command.refund_id,
                "original_invoice_id": command.original_invoice_id,
                "currency": command.currency,
                "subtotal_minor": subtotal_minor,
                "tax_minor": tax_minor,
                "total_minor": total_minor,
                "line_count": len(command.lines),
            },
            correlation_id=command.correlation_id,
            occurred_at=command.timestamp,
            idempotency_key=f"event_refund_completed_{command.refund_id}",
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            parent_transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
        )
        return RefundResult(command.refund_id, command.original_invoice_id, journal_id, movement_ids, subtotal_minor, tax_minor, total_minor, command.currency)

    def _validate_command(self, command: CreateInvoiceCommand) -> None:
        required = {
            "invoice_id": command.invoice_id,
            "customer_id": command.customer_id,
            "period_id": command.period_id,
            "timestamp": command.timestamp,
            "actor_id": command.actor_id,
            "correlation_id": command.correlation_id,
            "payment_method": command.payment_method,
            "currency": command.currency,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise BillingError(f"missing required invoice field(s): {', '.join(missing)}")
        if not command.lines:
            raise BillingError("invoice must contain at least one line")
        if self.tax_rate_basis_points < 0:
            raise BillingError("tax rate cannot be negative")
        for line in command.lines:
            if not line.item_id:
                raise BillingError("invoice line item_id is required")
            if line.quantity <= 0:
                raise BillingError("invoice line quantity must be positive")
            if line.unit_price_minor < 0:
                raise BillingError("invoice line unit price cannot be negative")

    def _validate_refund_command(self, command: CreateRefundCommand) -> None:
        required = {
            "refund_id": command.refund_id,
            "original_invoice_id": command.original_invoice_id,
            "period_id": command.period_id,
            "timestamp": command.timestamp,
            "actor_id": command.actor_id,
            "correlation_id": command.correlation_id,
            "currency": command.currency,
            "reason": command.reason,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise BillingError(f"missing required refund field(s): {', '.join(missing)}")
        if not command.lines:
            raise BillingError("refund must contain at least one line")
        if self.tax_rate_basis_points < 0:
            raise BillingError("tax rate cannot be negative")
        for line in command.lines:
            if not line.item_id:
                raise BillingError("refund line item_id is required")
            if line.quantity <= 0:
                raise BillingError("refund line quantity must be positive")
            if line.unit_price_minor < 0:
                raise BillingError("refund line unit price cannot be negative")

    def _reject_duplicate_invoice(self, invoice_id: str) -> None:
        for payload in self.store.read_payloads(self.store.invoices):
            if payload.get("invoice_id") == invoice_id:
                raise BillingError(f"invoice {invoice_id} is already completed")

    def _reject_duplicate_refund(self, refund_id: str) -> None:
        for payload in self.store.read_payloads(self.store.refunds):
            if payload.get("refund_id") == refund_id:
                raise BillingError(f"refund {refund_id} is already completed")

    def _get_invoice(self, invoice_id: str) -> dict[str, object] | None:
        for payload in self.store.read_payloads(self.store.invoices):
            if payload.get("invoice_id") == invoice_id:
                return payload
        return None

    def _validate_refund_against_original_invoice(self, command: CreateRefundCommand) -> None:
        remaining_by_line = self._original_invoice_quantities(command.original_invoice_id)
        if not remaining_by_line:
            raise BillingError(f"original invoice {command.original_invoice_id} has no refundable lines")

        prior_refund_ids = {
            _required_str(payload, "refund_id")
            for payload in self.store.read_payloads(self.store.refunds)
            if payload.get("original_invoice_id") == command.original_invoice_id
        }
        for payload in self.store.read_payloads(self.store.refund_lines):
            if payload.get("refund_id") not in prior_refund_ids:
                continue
            key = (_required_str(payload, "item_id"), _required_int(payload, "unit_price_minor"))
            remaining_by_line[key] = remaining_by_line.get(key, 0) - _required_int(payload, "quantity")

        requested_by_line: dict[tuple[str, int], int] = {}
        for line in command.lines:
            key = (line.item_id, line.unit_price_minor)
            requested_by_line[key] = requested_by_line.get(key, 0) + line.quantity

        for key, requested_quantity in requested_by_line.items():
            remaining_quantity = remaining_by_line.get(key, 0)
            item_id, unit_price_minor = key
            if remaining_quantity <= 0:
                raise BillingError(
                    f"refund line {item_id} at unit price {unit_price_minor} is not available on original invoice"
                )
            if requested_quantity > remaining_quantity:
                raise BillingError(
                    f"refund quantity for item {item_id} at unit price {unit_price_minor} exceeds remaining refundable quantity"
                )

    def _original_invoice_quantities(self, invoice_id: str) -> dict[tuple[str, int], int]:
        quantities: dict[tuple[str, int], int] = {}
        for payload in self.store.read_payloads(self.store.invoice_lines):
            if payload.get("invoice_id") != invoice_id:
                continue
            key = (_required_str(payload, "item_id"), _required_int(payload, "unit_price_minor"))
            quantities[key] = quantities.get(key, 0) + _required_int(payload, "quantity")
        return quantities

    def _validate_stock_available(self, command: CreateInvoiceCommand) -> None:
        required_by_item: dict[str, int] = {}
        for line in command.lines:
            required_by_item[line.item_id] = required_by_item.get(line.item_id, 0) + line.quantity
        for item_id, required_quantity in required_by_item.items():
            item = self.inventory.get_item(item_id)
            if item is None:
                raise BillingError(f"unknown item {item_id}")
            if not item.active:
                raise BillingError(f"inactive item {item_id}")
            available = self.inventory.get_stock_on_hand(item_id)
            if available < required_quantity:
                raise BillingError(f"insufficient stock for item {item_id}")


def _calculate_tax(subtotal_minor: int, tax_rate_basis_points: int) -> int:
    return subtotal_minor * tax_rate_basis_points // 10000


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BillingError(f"stored billing payload field {key} is not a non-empty string")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise BillingError(f"stored billing payload field {key} is not an integer")
    return value
