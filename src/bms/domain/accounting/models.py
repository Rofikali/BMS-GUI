from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    account_type: AccountType
    active: bool = True


@dataclass(frozen=True)
class JournalLine:
    account_code: str
    debit_minor: int = 0
    credit_minor: int = 0
    currency: str = "INR"
    memo: str = ""


@dataclass(frozen=True)
class PostJournalCommand:
    journal_id: str
    period_id: str
    timestamp: str
    actor_id: str
    source_module: str
    source_document_id: str
    correlation_id: str
    description: str
    lines: tuple[JournalLine, ...]


@dataclass(frozen=True)
class JournalResult:
    journal_id: str
    debit_total_minor: int
    credit_total_minor: int
    currency: str


@dataclass(frozen=True)
class TrialBalance:
    period_id: str
    debit_total_minor: int
    credit_total_minor: int

    @property
    def is_balanced(self) -> bool:
        return self.debit_total_minor == self.credit_total_minor
