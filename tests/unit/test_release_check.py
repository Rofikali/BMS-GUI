from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.release_check import ReleaseCheckError, run_release_check


class ReleaseCheckTests(unittest.TestCase):
    def test_release_check_runs_mvp_acceptance_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_release_check(
                Path(temp_dir) / "live",
                Path(temp_dir) / "restored",
            )

            self.assertEqual(result.invoice_total_minor, 118000)
            self.assertEqual(result.refund_total_minor, 59000)
            self.assertEqual(result.refundable_remaining_minor, 50000)
            self.assertEqual(result.stock_on_hand, 4)
            self.assertEqual(result.tax_payable_minor, 9000)
            self.assertEqual(result.business_unit_net_revenue_minor, 50000)
            self.assertTrue(result.trial_balance_balanced)
            self.assertTrue(result.restored_trial_balance_balanced)

    def test_release_check_refuses_non_empty_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            live = Path(temp_dir) / "live"
            restored = Path(temp_dir) / "restored"
            live.mkdir()
            (live / "existing.txt").write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(ReleaseCheckError, "not empty"):
                run_release_check(live, restored)


if __name__ == "__main__":
    unittest.main()
