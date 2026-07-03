from __future__ import annotations

from typing import Protocol

from bms.domain.accounting.models import JournalResult, PostJournalCommand, TrialBalance


class AccountingPort(Protocol):
    def post_journal(self, command: PostJournalCommand) -> JournalResult:
        raise NotImplementedError

    def is_period_closed(self, period_id: str) -> bool:
        raise NotImplementedError

    def get_trial_balance(self, period_id: str) -> TrialBalance:
        raise NotImplementedError
