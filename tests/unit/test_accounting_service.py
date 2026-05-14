from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingError, AccountingService, JournalLine, PostJournalCommand


class AccountingServiceTests(unittest.TestCase):
    def test_balanced_journal_posts_and_trial_balance_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))

            result = service.post_journal(_cash_sale_command("JRN-1"))
            trial_balance = service.get_trial_balance("FY2026-05")

            self.assertEqual(result.debit_total_minor, 118000)
            self.assertEqual(result.credit_total_minor, 118000)
            self.assertTrue(trial_balance.is_balanced)
            self.assertEqual(trial_balance.debit_total_minor, 118000)
            self.assertEqual(trial_balance.credit_total_minor, 118000)

    def test_unbalanced_journal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))
            command = _cash_sale_command(
                "JRN-2",
                lines=(
                    JournalLine("1000", debit_minor=118000),
                    JournalLine("4000", credit_minor=100000),
                ),
            )

            with self.assertRaisesRegex(AccountingError, "debits must equal credits"):
                service.post_journal(command)

            self.assertEqual(service.get_trial_balance("FY2026-05").debit_total_minor, 0)

    def test_closed_period_blocks_posting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))
            service.post_journal(_cash_sale_command("JRN-3"))
            service.close_period("FY2026-05")

            with self.assertRaisesRegex(AccountingError, "closed"):
                service.post_journal(_cash_sale_command("JRN-4"))

    def test_unknown_account_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))
            command = _cash_sale_command(
                "JRN-5",
                lines=(
                    JournalLine("9999", debit_minor=118000),
                    JournalLine("4000", credit_minor=100000),
                    JournalLine("2100", credit_minor=18000),
                ),
            )

            with self.assertRaisesRegex(AccountingError, "unknown account"):
                service.post_journal(command)

    def test_duplicate_journal_id_does_not_double_post(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AccountingService(initialize_data_root(Path(temp_dir)))
            service.post_journal(_cash_sale_command("JRN-6"))

            with self.assertRaisesRegex(AccountingError, "already posted"):
                service.post_journal(_cash_sale_command("JRN-6"))

            trial_balance = service.get_trial_balance("FY2026-05")
            self.assertEqual(trial_balance.debit_total_minor, 118000)
            self.assertEqual(trial_balance.credit_total_minor, 118000)
            self.assertEqual(service.store.core.verify_file(service.store.wal), 2)


def _cash_sale_command(
    journal_id: str,
    lines: tuple[JournalLine, ...] = (
        JournalLine("1000", debit_minor=118000),
        JournalLine("4000", credit_minor=100000),
        JournalLine("2100", credit_minor=18000),
    ),
) -> PostJournalCommand:
    return PostJournalCommand(
        journal_id=journal_id,
        period_id="FY2026-05",
        timestamp="2026-05-14T00:00:00Z",
        actor_id="usr_accountant",
        source_module="billing",
        source_document_id="INV-1001",
        correlation_id=f"corr_{journal_id}",
        description="Cash sale posting",
        lines=lines,
    )


if __name__ == "__main__":
    unittest.main()
