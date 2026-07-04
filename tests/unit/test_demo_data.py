from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app.demo_data import DemoDataError, seed_demo_data
from bms.app import start_command_facade


class DemoDataTests(unittest.TestCase):
    def test_seed_demo_data_creates_complete_closed_period_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "demo"

            result = seed_demo_data(root)
            facade = start_command_facade(root)

            self.assertEqual(result.invoice_total_minor, 174640)
            self.assertEqual(result.refund_total_minor, 21240)
            self.assertEqual(result.stock_rows, 2)
            self.assertTrue(result.trial_balance_balanced)
            self.assertEqual(facade.invoice_report("FY2026-05")["totals"][0]["total_minor"], 174640)
            self.assertEqual(facade.refund_report("FY2026-05")["totals"][0]["total_minor"], 21240)
            self.assertTrue(facade.trial_balance_report("FY2026-05")["is_balanced"])

    def test_seed_demo_data_refuses_non_empty_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "demo"
            root.mkdir()
            (root / "existing.txt").write_text("existing", encoding="utf-8")

            with self.assertRaisesRegex(DemoDataError, "not empty"):
                seed_demo_data(root)


if __name__ == "__main__":
    unittest.main()
