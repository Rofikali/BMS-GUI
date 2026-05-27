from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from bms.ui import main as ui_main


class UiMainTests(unittest.TestCase):
    def test_main_window_runs_facade_backed_flow_when_qt_is_available(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        app.setStyleSheet(ui_main._stylesheet())
        with tempfile.TemporaryDirectory() as temp_dir:
            window = ui_main.create_main_window(data_root=Path(temp_dir))
            window.register_item()
            window.create_invoice()
            window.create_refund()
            window.create_backup()
            window.restore_target_input.setText(str(Path(temp_dir) / "restored"))
            window.restore_backup()

            self.assertEqual(window.invoice_total_label.text(), "118000")
            self.assertEqual(window.refund_total_label.text(), "59000")
            self.assertEqual(window.report_invoice_total_label.text(), "118000")
            self.assertEqual(window.report_refund_total_label.text(), "59000")
            self.assertEqual(window.report_tax_payable_label.text(), "9000")
            self.assertEqual(window.stock_table.rowCount(), 1)
            self.assertEqual(window.stock_table.item(0, 3).text(), "4")
            self.assertEqual(window.invoice_table.rowCount(), 1)
            self.assertEqual(window.refund_table.rowCount(), 1)
            self.assertTrue(Path(window.backup_path_label.text()).exists())
            self.assertEqual(window.status_label.text(), f"Restore validated at {Path(temp_dir) / 'restored'}")
            window.close()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
