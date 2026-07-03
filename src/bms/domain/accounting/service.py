from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from bms.domain.accounting.chart import BASELINE_CHART_OF_ACCOUNTS
from bms.domain.accounting.models import (
    Account,
    AccountType,
    JournalLine,
    JournalResult,
    LedgerBalance,
    PostJournalCommand,
    TrialBalance,
)
from bms.storage.ports import DurableStorePort


class AccountingError(ValueError):
    pass


class AccountingService:
    def __init__(
        self,
        store: DurableStorePort,
        accounts: dict[str, Account] | None = None,
        closed_periods: set[str] | None = None,
    ) -> None:
        self.store = store
        self.accounts = accounts or BASELINE_CHART_OF_ACCOUNTS
        self.closed_periods = self._load_closed_periods()
        if closed_periods:
            self.closed_periods.update(closed_periods)

    def post_journal(self, command: PostJournalCommand) -> JournalResult:
        self._validate_post_command(command)
        self._reject_duplicate_journal(command.journal_id)
        debit_total = sum(line.debit_minor for line in command.lines)
        credit_total = sum(line.credit_minor for line in command.lines)
        currency = command.lines[0].currency
        transaction_id = f"txn_accounting_{command.journal_id}_{uuid4().hex}"

        self.store.core.append_wal_pending(
            self.store.wal,
            transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
            {
                "operation": "accounting.post_journal",
                "journal_id": command.journal_id,
                "period_id": command.period_id,
                "source_document_id": command.source_document_id,
            },
        )
        self.store.append_record(
            self.store.journal_entries,
            "accounting.journal_entry",
            command.actor_id,
            command.correlation_id,
            f"journal_entry_{command.journal_id}",
            {
                "journal_id": command.journal_id,
                "period_id": command.period_id,
                "timestamp": command.timestamp,
                "actor_id": command.actor_id,
                "source_module": command.source_module,
                "source_document_id": command.source_document_id,
                "correlation_id": command.correlation_id,
                "description": command.description,
                "debit_total_minor": debit_total,
                "credit_total_minor": credit_total,
                "currency": currency,
            },
            record_id=f"jrn_{command.journal_id}",
            created_at=command.timestamp,
        )
        for index, line in enumerate(command.lines, start=1):
            self.store.append_record(
                self.store.journal_lines,
                "accounting.journal_line",
                command.actor_id,
                command.correlation_id,
                f"journal_line_{command.journal_id}_{index}",
                self._line_payload(command, line, index),
                record_id=f"jln_{command.journal_id}_{index}",
                created_at=command.timestamp,
            )
        self.store.append_audit_record(
            "accounting.journal_posted",
            command.actor_id,
            "journal",
            command.journal_id,
            command.correlation_id,
            occurred_at=command.timestamp,
            details={
                "period_id": command.period_id,
                "source_module": command.source_module,
                "source_document_id": command.source_document_id,
                "debit_total_minor": debit_total,
                "credit_total_minor": credit_total,
                "currency": currency,
            },
            idempotency_key=f"audit_journal_posted_{command.journal_id}",
        )
        self.store.append_business_event(
            "accounting.journal_posted.v1",
            command.actor_id,
            {
                "journal_id": command.journal_id,
                "period_id": command.period_id,
                "source_document_id": command.source_document_id,
                "debit_total_minor": debit_total,
                "credit_total_minor": credit_total,
                "currency": currency,
            },
            correlation_id=command.correlation_id,
            occurred_at=command.timestamp,
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            transaction_id,
            command.timestamp,
            command.actor_id,
            command.correlation_id,
        )
        return JournalResult(command.journal_id, debit_total, credit_total, currency)

    def is_period_closed(self, period_id: str) -> bool:
        return period_id in self.closed_periods

    def get_trial_balance(self, period_id: str) -> TrialBalance:
        debit_total = 0
        credit_total = 0
        for payload in self.store.read_payloads(self.store.journal_entries):
            if payload.get("period_id") == period_id:
                debit_total += _int_payload(payload, "debit_total_minor")
                credit_total += _int_payload(payload, "credit_total_minor")
        return TrialBalance(period_id, debit_total, credit_total)

    def get_ledger_balances(self, period_id: str) -> dict[str, LedgerBalance]:
        totals: dict[str, dict[str, int | str]] = {}
        for payload in self.store.read_payloads(self.store.journal_lines):
            if payload.get("period_id") != period_id:
                continue

            account_code = payload.get("account_code")
            if not isinstance(account_code, str):
                raise AccountingError("stored journal line account_code is not a string")
            if account_code not in self.accounts:
                raise AccountingError(f"stored journal line has unknown account code {account_code}")

            currency = payload.get("currency")
            if not isinstance(currency, str) or not currency:
                raise AccountingError("stored journal line currency is invalid")

            account_totals = totals.setdefault(
                account_code,
                {"debit": 0, "credit": 0, "currency": currency},
            )
            if account_totals["currency"] != currency:
                raise AccountingError(f"stored journal lines for account {account_code} use multiple currencies")
            account_totals["debit"] = int(account_totals["debit"]) + _int_payload(payload, "debit_minor")
            account_totals["credit"] = int(account_totals["credit"]) + _int_payload(payload, "credit_minor")

        balances: dict[str, LedgerBalance] = {}
        for account_code in sorted(totals):
            account = self.accounts[account_code]
            account_totals = totals[account_code]
            debit_total = int(account_totals["debit"])
            credit_total = int(account_totals["credit"])
            balances[account_code] = LedgerBalance(
                period_id=period_id,
                account_code=account.code,
                account_name=account.name,
                account_type=account.account_type,
                debit_total_minor=debit_total,
                credit_total_minor=credit_total,
                balance_minor=_normal_balance(account.account_type, debit_total, credit_total),
                currency=str(account_totals["currency"]),
            )
        return balances

    def close_period(
        self,
        period_id: str,
        *,
        actor_id: str = "usr_system",
        closed_at: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if not period_id:
            raise AccountingError("period_id is required")
        if period_id in self.closed_periods:
            return

        trial_balance = self.get_trial_balance(period_id)
        if not trial_balance.is_balanced:
            raise AccountingError(f"cannot close unbalanced period {period_id}")

        closed_at = closed_at or _utc_now()
        correlation_id = correlation_id or f"corr_close_period_{period_id}"
        transaction_id = f"txn_accounting_close_period_{period_id}_{uuid4().hex}"
        self.store.core.append_wal_pending(
            self.store.wal,
            transaction_id,
            closed_at,
            actor_id,
            correlation_id,
            {"operation": "accounting.close_period", "period_id": period_id},
        )
        self.store.append_record(
            self.store.periods,
            "accounting.period_closed",
            actor_id,
            correlation_id,
            f"period_closed_{period_id}",
            {
                "period_id": period_id,
                "status": "closed",
                "closed_at": closed_at,
                "actor_id": actor_id,
                "correlation_id": correlation_id,
                "trial_balance_debit_total_minor": trial_balance.debit_total_minor,
                "trial_balance_credit_total_minor": trial_balance.credit_total_minor,
            },
            record_id=f"period_closed_{period_id}",
            created_at=closed_at,
        )
        self.store.append_audit_record(
            "accounting.period_closed",
            actor_id,
            "accounting_period",
            period_id,
            correlation_id,
            occurred_at=closed_at,
            details={
                "debit_total_minor": trial_balance.debit_total_minor,
                "credit_total_minor": trial_balance.credit_total_minor,
            },
            idempotency_key=f"audit_period_closed_{period_id}",
        )
        self.store.append_business_event(
            "accounting.period_closed.v1",
            actor_id,
            {
                "period_id": period_id,
                "debit_total_minor": trial_balance.debit_total_minor,
                "credit_total_minor": trial_balance.credit_total_minor,
            },
            correlation_id=correlation_id,
            occurred_at=closed_at,
            idempotency_key=f"event_period_closed_{period_id}",
        )
        self.store.core.append_wal_committed(
            self.store.wal,
            transaction_id,
            closed_at,
            actor_id,
            correlation_id,
        )
        self.closed_periods.add(period_id)

    def _load_closed_periods(self) -> set[str]:
        closed_periods: set[str] = set()
        for payload in self.store.read_payloads(self.store.periods):
            period_id = payload.get("period_id")
            if payload.get("status") == "closed" and isinstance(period_id, str):
                closed_periods.add(period_id)
        return closed_periods

    def _validate_post_command(self, command: PostJournalCommand) -> None:
        required = {
            "journal_id": command.journal_id,
            "period_id": command.period_id,
            "timestamp": command.timestamp,
            "actor_id": command.actor_id,
            "source_module": command.source_module,
            "source_document_id": command.source_document_id,
            "correlation_id": command.correlation_id,
            "description": command.description,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise AccountingError(f"missing required journal field(s): {', '.join(missing)}")
        if command.period_id in self.closed_periods:
            raise AccountingError(f"period {command.period_id} is closed")
        if len(command.lines) < 2:
            raise AccountingError("journal must contain at least two lines")

        currencies = {line.currency for line in command.lines}
        if len(currencies) != 1:
            raise AccountingError("journal lines must use one currency")

        debit_total = 0
        credit_total = 0
        for line in command.lines:
            self._validate_line(line)
            debit_total += line.debit_minor
            credit_total += line.credit_minor
        if debit_total != credit_total:
            raise AccountingError("journal debits must equal credits")

    def _reject_duplicate_journal(self, journal_id: str) -> None:
        for payload in self.store.read_payloads(self.store.journal_entries):
            if payload.get("journal_id") == journal_id:
                raise AccountingError(f"journal {journal_id} is already posted")

    def _validate_line(self, line: JournalLine) -> None:
        if line.account_code not in self.accounts:
            raise AccountingError(f"unknown account code {line.account_code}")
        if not self.accounts[line.account_code].active:
            raise AccountingError(f"inactive account code {line.account_code}")
        if not line.currency:
            raise AccountingError("journal line currency is required")
        if line.debit_minor < 0 or line.credit_minor < 0:
            raise AccountingError("journal line amounts cannot be negative")
        if line.debit_minor == 0 and line.credit_minor == 0:
            raise AccountingError("journal line must carry a debit or credit amount")
        if line.debit_minor > 0 and line.credit_minor > 0:
            raise AccountingError("journal line cannot have both debit and credit amounts")

    def _line_payload(self, command: PostJournalCommand, line: JournalLine, index: int) -> dict[str, object]:
        return {
            "journal_id": command.journal_id,
            "line_no": index,
            "period_id": command.period_id,
            "account_code": line.account_code,
            "debit_minor": line.debit_minor,
            "credit_minor": line.credit_minor,
            "currency": line.currency,
            "memo": line.memo,
            "source_document_id": command.source_document_id,
            "correlation_id": command.correlation_id,
        }


def _normal_balance(account_type: AccountType, debit_total: int, credit_total: int) -> int:
    if account_type in (AccountType.ASSET, AccountType.EXPENSE):
        return debit_total - credit_total
    return credit_total - debit_total


def _int_payload(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AccountingError(f"stored payload field {key} is not an integer")
    return value


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
