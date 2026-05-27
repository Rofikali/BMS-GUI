from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from bms.app.auth import AuthorizationPolicy, IdentityService
from bms.app.bootstrap import initialize_data_root
from bms.app.startup import StartupHealth, StartupHealthService, StartupState
from bms.core import WalRecoveryResult
from bms.domain.accounting import AccountingService, validate_post_journal_command_payload


class ApplicationRecoveryError(RuntimeError):
    pass


class RecoveryReconciliationDecision(StrEnum):
    ACCEPTED_EXISTING_RECORDS = "accepted_existing_records"
    REQUIRES_ACCOUNTING_ADJUSTMENT = "requires_accounting_adjustment"
    REQUIRES_RESTORE_FROM_BACKUP = "requires_restore_from_backup"
    VOIDED_AS_INCOMPLETE = "voided_as_incomplete"


@dataclass(frozen=True)
class ApplicationRecoveryResult:
    before: StartupHealth
    recovery: WalRecoveryResult
    after: StartupHealth


@dataclass(frozen=True)
class PendingRecoveryTransaction:
    transaction_id: str
    operation: str
    correlation_id: str
    side_effects: tuple[str, ...]
    payload: dict[str, object]


@dataclass(frozen=True)
class ApplicationRecoveryDiagnostics:
    startup_health: StartupHealth
    pending_transactions: tuple[PendingRecoveryTransaction, ...]

    @property
    def automatic_recovery_safe(self) -> bool:
        return not any(transaction.side_effects for transaction in self.pending_transactions)


@dataclass(frozen=True)
class RecoveryReconciliationResult:
    reconciliation_id: str
    transaction_id: str
    decision: RecoveryReconciliationDecision
    resolved: bool


@dataclass(frozen=True)
class RecoveryAccountingAdjustmentResult:
    reconciliation_id: str
    transaction_id: str
    correction_journal_id: str
    resolved: bool


def inspect_application_recovery(data_root: Path, required_snapshot_path: Path | None = None) -> ApplicationRecoveryDiagnostics:
    store = initialize_data_root(data_root)
    startup_health = StartupHealthService(store).inspect(required_snapshot_path)
    return ApplicationRecoveryDiagnostics(
        startup_health=startup_health,
        pending_transactions=()
        if startup_health.state == StartupState.PROTECTED_MODE
        else tuple(_pending_transactions(store)),
    )


def export_application_recovery_diagnostics(
    data_root: Path,
    required_snapshot_path: Path | None = None,
) -> dict[str, object]:
    diagnostics = inspect_application_recovery(data_root, required_snapshot_path)
    return {
        "startup_health": {
            "state": diagnostics.startup_health.state.value,
            "wal_status": diagnostics.startup_health.wal_status,
            "wal_decision": diagnostics.startup_health.wal_decision,
            "message": diagnostics.startup_health.message,
        },
        "automatic_recovery_safe": diagnostics.automatic_recovery_safe,
        "pending_transactions": [
            {
                "transaction_id": transaction.transaction_id,
                "operation": transaction.operation,
                "correlation_id": transaction.correlation_id,
                "side_effects": list(transaction.side_effects),
                "payload": transaction.payload,
            }
            for transaction in diagnostics.pending_transactions
        ],
    }


def export_application_recovery_report(
    data_root: Path,
    required_snapshot_path: Path | None = None,
) -> dict[str, object]:
    store = initialize_data_root(data_root)
    diagnostics = export_application_recovery_diagnostics(data_root, required_snapshot_path)
    pending_transactions = diagnostics["pending_transactions"]
    reconciliation_records = store.read_payloads(store.reconciliation_records)
    correction_journals = _recovery_correction_journals(store, reconciliation_records)
    audit_references = _recovery_audit_references(store)
    event_references = _recovery_event_references(store)
    return {
        "startup_health": diagnostics["startup_health"],
        "normal_startup_allowed": diagnostics["startup_health"]["state"] == StartupState.HEALTHY.value,
        "automatic_recovery_safe": diagnostics["automatic_recovery_safe"],
        "pending_transactions": pending_transactions,
        "reconciliation_records": reconciliation_records,
        "correction_journals": correction_journals,
        "audit_references": audit_references,
        "event_references": event_references,
        "recommended_next_action": _recommended_next_action(
            diagnostics["startup_health"]["state"],
            pending_transactions,
            reconciliation_records,
        ),
    }


def recover_application_storage(
    data_root: Path,
    required_snapshot_path: Path | None = None,
) -> ApplicationRecoveryResult:
    store = initialize_data_root(data_root)
    health_service = StartupHealthService(store)
    before = health_service.inspect(required_snapshot_path)
    if before.state == StartupState.PROTECTED_MODE:
        raise ApplicationRecoveryError(f"cannot recover protected storage automatically: {before.message}")
    if before.state == StartupState.HEALTHY:
        recovery = store.recover_wal_startup(required_snapshot_path)
        return ApplicationRecoveryResult(before=before, recovery=recovery, after=health_service.inspect(required_snapshot_path))

    unsafe_transactions = [
        transaction
        for transaction in _pending_transactions(store)
        if transaction.side_effects
    ]
    if unsafe_transactions:
        joined = ", ".join(
            f"{transaction.transaction_id} ({'; '.join(transaction.side_effects)})"
            for transaction in unsafe_transactions
        )
        raise ApplicationRecoveryError(
            f"cannot automatically roll back pending transaction(s) with durable side effects: {joined}"
        )

    recovery = store.recover_wal_startup(required_snapshot_path)
    after = health_service.inspect(required_snapshot_path)
    if after.state != StartupState.HEALTHY:
        raise ApplicationRecoveryError(
            f"automatic recovery did not produce healthy storage: {after.state.value}"
        )
    return ApplicationRecoveryResult(before=before, recovery=recovery, after=after)


def reconcile_recovery_transaction(
    data_root: Path,
    *,
    transaction_id: str,
    decision: str,
    actor_id: str,
    reason: str,
    created_at: str | None = None,
) -> RecoveryReconciliationResult:
    if not transaction_id:
        raise ApplicationRecoveryError("transaction_id is required")
    if not actor_id:
        raise ApplicationRecoveryError("actor_id is required")
    if not reason:
        raise ApplicationRecoveryError("reason is required")

    store = initialize_data_root(data_root)
    _authorize_reconciliation(store, actor_id)
    reconciliation_decision = _parse_reconciliation_decision(decision)
    created_at = created_at or _utc_now()
    pending_by_id = {transaction.transaction_id: transaction for transaction in _pending_transactions(store)}
    transaction = pending_by_id.get(transaction_id)
    if transaction is None:
        raise ApplicationRecoveryError(f"pending transaction {transaction_id} was not found")
    if _has_reconciliation_record(store, transaction_id):
        raise ApplicationRecoveryError(f"transaction {transaction_id} is already reconciled")

    resolved = reconciliation_decision in _RESOLVING_RECONCILIATION_DECISIONS
    reconciliation_id = f"rec_{transaction_id}"
    payload = {
        "reconciliation_id": reconciliation_id,
        "transaction_id": transaction.transaction_id,
        "operation": transaction.operation,
        "correlation_id": transaction.correlation_id,
        "decision": reconciliation_decision.value,
        "reason": reason,
        "actor_id": actor_id,
        "created_at": created_at,
        "resolved": resolved,
        "side_effects": list(transaction.side_effects),
        "pending_payload": transaction.payload,
    }

    store.append_record(
        store.reconciliation_records,
        "recovery.reconciliation_record",
        actor_id,
        transaction.correlation_id,
        f"recovery_reconciliation_{transaction_id}",
        payload,
        record_id=reconciliation_id,
        created_at=created_at,
    )
    store.append_audit_record(
        "recovery.reconciliation_recorded",
        actor_id,
        "wal_transaction",
        transaction.transaction_id,
        transaction.correlation_id,
        occurred_at=created_at,
        details={
            "operation": transaction.operation,
            "decision": reconciliation_decision.value,
            "resolved": resolved,
            "reason": reason,
            "side_effects": list(transaction.side_effects),
        },
        idempotency_key=f"audit_recovery_reconciliation_{transaction_id}",
    )
    store.append_business_event(
        "recovery.reconciliation_recorded.v1",
        actor_id,
        {
            "reconciliation_id": reconciliation_id,
            "transaction_id": transaction.transaction_id,
            "operation": transaction.operation,
            "decision": reconciliation_decision.value,
            "resolved": resolved,
        },
        correlation_id=transaction.correlation_id,
        occurred_at=created_at,
        idempotency_key=f"event_recovery_reconciliation_{transaction_id}",
    )
    if resolved:
        store.core.append_wal_committed(
            store.wal,
            transaction.transaction_id,
            created_at,
            actor_id,
            transaction.correlation_id,
        )

    return RecoveryReconciliationResult(
        reconciliation_id=reconciliation_id,
        transaction_id=transaction.transaction_id,
        decision=reconciliation_decision,
        resolved=resolved,
    )


def resolve_recovery_accounting_adjustment(
    data_root: Path,
    *,
    transaction_id: str,
    actor_id: str,
    reason: str,
    journal_payload: Mapping[str, Any],
    created_at: str | None = None,
) -> RecoveryAccountingAdjustmentResult:
    if not transaction_id:
        raise ApplicationRecoveryError("transaction_id is required")
    if not actor_id:
        raise ApplicationRecoveryError("actor_id is required")
    if not reason:
        raise ApplicationRecoveryError("reason is required")

    store = initialize_data_root(data_root)
    _authorize_reconciliation(store, actor_id)
    pending_by_id = {transaction.transaction_id: transaction for transaction in _pending_transactions(store)}
    transaction = pending_by_id.get(transaction_id)
    if transaction is None:
        raise ApplicationRecoveryError(f"pending transaction {transaction_id} was not found")

    reconciliation = _reconciliation_record_for_transaction(store, transaction_id)
    if reconciliation is None:
        raise ApplicationRecoveryError(f"transaction {transaction_id} has no reconciliation record")
    if reconciliation.get("decision") != RecoveryReconciliationDecision.REQUIRES_ACCOUNTING_ADJUSTMENT.value:
        raise ApplicationRecoveryError(
            f"transaction {transaction_id} is not waiting for an accounting adjustment"
        )
    if reconciliation.get("resolved") is True:
        raise ApplicationRecoveryError(f"transaction {transaction_id} is already resolved")
    if _has_accounting_adjustment_resolution(store, transaction_id):
        raise ApplicationRecoveryError(f"transaction {transaction_id} already has an accounting adjustment resolution")

    command = validate_post_journal_command_payload(journal_payload)
    if command.actor_id != actor_id:
        raise ApplicationRecoveryError("journal actor_id must match the resolving actor_id")
    if command.source_module != "recovery":
        raise ApplicationRecoveryError("journal source_module must be recovery")
    if command.source_document_id != transaction_id:
        raise ApplicationRecoveryError("journal source_document_id must match transaction_id")

    journal = AccountingService(store).post_journal(command)
    created_at = created_at or _utc_now()
    reconciliation_id = f"rec_{transaction_id}_accounting_adjustment"
    payload = {
        "reconciliation_id": reconciliation_id,
        "transaction_id": transaction.transaction_id,
        "operation": transaction.operation,
        "correlation_id": transaction.correlation_id,
        "decision": RecoveryReconciliationDecision.REQUIRES_ACCOUNTING_ADJUSTMENT.value,
        "reason": reason,
        "actor_id": actor_id,
        "created_at": created_at,
        "resolved": True,
        "resolution_type": "accounting_adjustment",
        "correction_journal_id": journal.journal_id,
        "correction_debit_total_minor": journal.debit_total_minor,
        "correction_credit_total_minor": journal.credit_total_minor,
        "side_effects": list(transaction.side_effects),
        "pending_payload": transaction.payload,
    }

    store.append_record(
        store.reconciliation_records,
        "recovery.reconciliation_record",
        actor_id,
        transaction.correlation_id,
        f"recovery_accounting_adjustment_{transaction_id}",
        payload,
        record_id=reconciliation_id,
        created_at=created_at,
    )
    store.append_audit_record(
        "recovery.accounting_adjustment_resolved",
        actor_id,
        "wal_transaction",
        transaction.transaction_id,
        transaction.correlation_id,
        occurred_at=created_at,
        details={
            "operation": transaction.operation,
            "correction_journal_id": journal.journal_id,
            "reason": reason,
            "side_effects": list(transaction.side_effects),
        },
        idempotency_key=f"audit_recovery_accounting_adjustment_{transaction_id}",
    )
    store.append_business_event(
        "recovery.reconciliation_recorded.v1",
        actor_id,
        {
            "reconciliation_id": reconciliation_id,
            "transaction_id": transaction.transaction_id,
            "operation": transaction.operation,
            "decision": RecoveryReconciliationDecision.REQUIRES_ACCOUNTING_ADJUSTMENT.value,
            "resolved": True,
            "correction_journal_id": journal.journal_id,
        },
        correlation_id=transaction.correlation_id,
        occurred_at=created_at,
        idempotency_key=f"event_recovery_accounting_adjustment_{transaction_id}",
    )
    store.core.append_wal_committed(
        store.wal,
        transaction.transaction_id,
        created_at,
        actor_id,
        transaction.correlation_id,
    )
    return RecoveryAccountingAdjustmentResult(
        reconciliation_id=reconciliation_id,
        transaction_id=transaction.transaction_id,
        correction_journal_id=journal.journal_id,
        resolved=True,
    )


def _pending_transactions(store: object) -> list[PendingRecoveryTransaction]:
    pending: list[PendingRecoveryTransaction] = []
    committed_transaction_ids = _committed_transaction_ids(store)
    for wal_envelope in _read_wal_envelopes(store):
        wal_payload = wal_envelope.get("payload")
        if not isinstance(wal_payload, dict):
            pending.append(
                PendingRecoveryTransaction(
                    transaction_id="unknown",
                    operation="unknown",
                    correlation_id=_string_or_unknown(wal_envelope.get("correlation_id")),
                    side_effects=("malformed WAL payload",),
                    payload={},
                )
            )
            continue
        if wal_payload.get("state") != "pending":
            continue
        transaction_id = wal_payload.get("transaction_id")
        payload = wal_payload.get("payload")
        if isinstance(transaction_id, str) and transaction_id in committed_transaction_ids:
            continue
        if not isinstance(transaction_id, str) or not isinstance(payload, dict):
            pending.append(
                PendingRecoveryTransaction(
                    transaction_id="unknown",
                    operation="unknown",
                    correlation_id=_string_or_unknown(wal_envelope.get("correlation_id")),
                    side_effects=("malformed WAL payload",),
                    payload={},
                )
            )
            continue

        operation = _string_or_unknown(payload.get("operation"))
        pending.append(
            PendingRecoveryTransaction(
                transaction_id=transaction_id,
                operation=operation,
                correlation_id=_string_or_unknown(wal_envelope.get("correlation_id")),
                side_effects=tuple(_durable_side_effects_for_pending_operation(store, payload)),
                payload=dict(payload),
            )
        )
    return pending


def _committed_transaction_ids(store: object) -> set[str]:
    committed: set[str] = set()
    for wal_envelope in _read_wal_envelopes(store):
        wal_payload = wal_envelope.get("payload")
        if not isinstance(wal_payload, dict):
            continue
        if wal_payload.get("state") != "committed":
            continue
        transaction_id = wal_payload.get("transaction_id")
        if isinstance(transaction_id, str):
            committed.add(transaction_id)
    return committed


def _read_wal_envelopes(store: object) -> list[dict[str, object]]:
    if not store.wal.exists():
        return []

    store.core.verify_file(store.wal)
    envelopes: list[dict[str, object]] = []
    with store.wal.open("r", encoding="utf-8") as records:
        for line in records:
            line = line.strip()
            if not line:
                continue
            envelope = json.loads(line)
            if isinstance(envelope, dict):
                envelopes.append(envelope)
    return envelopes


def _durable_side_effects_for_pending_operation(store: object, payload: dict[str, object]) -> list[str]:
    operation = payload.get("operation")
    if operation == "billing.create_invoice":
        return _billing_invoice_side_effects(store, payload)
    if operation == "accounting.post_journal":
        journal_id = payload.get("journal_id")
        if isinstance(journal_id, str):
            return _record_effects(
                store,
                (
                    (store.journal_entries, "journal_id", journal_id, "journal entry exists"),
                    (store.journal_lines, "journal_id", journal_id, "journal lines exist"),
                ),
            )
    if operation == "inventory.commit_movement":
        movement_id = payload.get("movement_id")
        if isinstance(movement_id, str):
            return _record_effects(
                store,
                ((store.stock_movements, "movement_id", movement_id, "stock movement exists"),),
            )
    if operation == "inventory.register_item":
        item_id = payload.get("item_id")
        if isinstance(item_id, str):
            return _record_effects(
                store,
                ((store.items, "item_id", item_id, "item registration exists"),),
            )
    return []


def _billing_invoice_side_effects(store: object, payload: dict[str, object]) -> list[str]:
    effects: list[tuple[object, str, str, str]] = []
    invoice_id = payload.get("invoice_id")
    journal_id = payload.get("journal_id")
    movement_ids = payload.get("movement_ids")
    if isinstance(invoice_id, str):
        effects.extend(
            (
                (store.invoices, "invoice_id", invoice_id, "invoice exists"),
                (store.invoice_lines, "invoice_id", invoice_id, "invoice lines exist"),
            )
        )
    if isinstance(journal_id, str):
        effects.extend(
            (
                (store.journal_entries, "journal_id", journal_id, "journal entry exists"),
                (store.journal_lines, "journal_id", journal_id, "journal lines exist"),
            )
        )
    if isinstance(movement_ids, list):
        for movement_id in movement_ids:
            if isinstance(movement_id, str):
                effects.append((store.stock_movements, "movement_id", movement_id, "stock movement exists"))
    return _record_effects(store, tuple(effects))


def _record_effects(
    store: object,
    checks: tuple[tuple[object, str, str, str], ...],
) -> list[str]:
    reasons: list[str] = []
    for path, field_name, expected_value, reason in checks:
        if any(payload.get(field_name) == expected_value for payload in store.read_payloads(path)):
            reasons.append(reason)
    return reasons


def _string_or_unknown(value: Any) -> str:
    return value if isinstance(value, str) and value else "unknown"


def _authorize_reconciliation(store: object, actor_id: str) -> None:
    session = IdentityService(store).get_session(actor_id)
    AuthorizationPolicy().require("recovery.reconcile", session.roles)


def _parse_reconciliation_decision(decision: str) -> RecoveryReconciliationDecision:
    try:
        return RecoveryReconciliationDecision(decision)
    except ValueError as exc:
        allowed = ", ".join(decision.value for decision in RecoveryReconciliationDecision)
        raise ApplicationRecoveryError(f"unsupported reconciliation decision {decision}; expected one of: {allowed}") from exc


def _has_reconciliation_record(store: object, transaction_id: str) -> bool:
    return any(
        payload.get("transaction_id") == transaction_id
        for payload in store.read_payloads(store.reconciliation_records)
    )


def _reconciliation_record_for_transaction(store: object, transaction_id: str) -> dict[str, object] | None:
    for payload in store.read_payloads(store.reconciliation_records):
        if payload.get("transaction_id") == transaction_id and payload.get("resolution_type") != "accounting_adjustment":
            return payload
    return None


def _has_accounting_adjustment_resolution(store: object, transaction_id: str) -> bool:
    return any(
        payload.get("transaction_id") == transaction_id
        and payload.get("resolution_type") == "accounting_adjustment"
        for payload in store.read_payloads(store.reconciliation_records)
    )


def _recovery_correction_journals(
    store: object,
    reconciliation_records: list[dict[str, object]],
) -> list[dict[str, object]]:
    correction_ids = {
        payload.get("correction_journal_id")
        for payload in reconciliation_records
        if isinstance(payload.get("correction_journal_id"), str)
    }
    if not correction_ids:
        return []
    return [
        payload
        for payload in store.read_payloads(store.journal_entries)
        if payload.get("journal_id") in correction_ids
    ]


def _recovery_audit_references(store: object) -> list[dict[str, object]]:
    return [
        payload
        for payload in store.read_payloads(store.audit_records)
        if isinstance(payload.get("action"), str)
        and str(payload.get("action")).startswith("recovery.")
    ]


def _recovery_event_references(store: object) -> list[dict[str, object]]:
    return [
        payload
        for payload in store.read_payloads(store.business_events)
        if isinstance(payload.get("event_type"), str)
        and str(payload.get("event_type")).startswith("recovery.")
    ]


def _recommended_next_action(
    startup_state: object,
    pending_transactions: object,
    reconciliation_records: list[dict[str, object]],
) -> str:
    if startup_state == StartupState.PROTECTED_MODE.value:
        return "restore_from_backup_or_manual_storage_repair"
    if not isinstance(pending_transactions, list) or not pending_transactions:
        return "normal_startup_allowed"
    if all(
        isinstance(transaction, dict) and not transaction.get("side_effects")
        for transaction in pending_transactions
    ):
        return "run_bms_recovery_recover"

    reconciliation_by_transaction = {
        payload.get("transaction_id"): payload
        for payload in reconciliation_records
        if isinstance(payload.get("transaction_id"), str)
        and payload.get("resolution_type") != "accounting_adjustment"
    }
    resolution_by_transaction = {
        payload.get("transaction_id"): payload
        for payload in reconciliation_records
        if isinstance(payload.get("transaction_id"), str)
        and payload.get("resolution_type") == "accounting_adjustment"
    }
    for transaction in pending_transactions:
        if not isinstance(transaction, dict):
            return "run_bms_recovery_inspect"
        transaction_id = transaction.get("transaction_id")
        reconciliation = reconciliation_by_transaction.get(transaction_id)
        if reconciliation is None:
            return "run_bms_recovery_reconcile"
        decision = reconciliation.get("decision")
        if decision == RecoveryReconciliationDecision.REQUIRES_ACCOUNTING_ADJUSTMENT.value:
            if transaction_id not in resolution_by_transaction:
                return "run_bms_recovery_resolve_accounting_adjustment"
            return "run_bms_recovery_inspect"
        if decision == RecoveryReconciliationDecision.REQUIRES_RESTORE_FROM_BACKUP.value:
            return "restore_from_backup"
        if decision == RecoveryReconciliationDecision.VOIDED_AS_INCOMPLETE.value:
            return "manual_void_resolution_not_implemented"
    return "run_bms_recovery_inspect"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_RESOLVING_RECONCILIATION_DECISIONS = {
    RecoveryReconciliationDecision.ACCEPTED_EXISTING_RECORDS,
}
