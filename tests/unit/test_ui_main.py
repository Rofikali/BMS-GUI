from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from bms.ui import main as ui_main


class UiMainTests(unittest.TestCase):
    def test_new_business_id_uses_prefix_timestamp_and_short_suffix(self) -> None:
        business_id = ui_main._new_business_id("INV")

        self.assertRegex(business_id, r"^INV-\d{14}-[0-9A-F]{6}$")

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
            self.assertEqual(window.report_refundable_remaining_label.text(), "50000")
            self.assertEqual(window.report_tax_payable_label.text(), "9000")
            self.assertEqual(window.stock_table.rowCount(), 1)
            self.assertEqual(window.stock_table.item(0, 3).text(), "4")
            self.assertEqual(window.invoice_table.rowCount(), 1)
            self.assertEqual(window.refund_table.rowCount(), 1)
            self.assertEqual(window.refund_availability_table.rowCount(), 1)
            self.assertEqual(window.refund_availability_table.item(0, 5).text(), "1")
            self.assertTrue(Path(window.backup_path_label.text()).exists())
            self.assertEqual(window.status_label.text(), f"Restore validated at {Path(temp_dir) / 'restored'}")
            window.close()
            app.processEvents()

    def test_main_window_uses_operator_period_currency_payment_and_refund_reason(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        facade = _CapturingFacade()
        window = ui_main.create_main_window(facade=facade)

        window.period_input.setText("FY2026-06")
        window.currency_input.setText("usd")
        window.invoice_payment_method_input.setCurrentText("card")
        window.refund_reason_input.setText("damaged box")

        window.create_invoice()
        window.create_refund()
        window.close_period()
        window.refresh_reports()

        self.assertEqual(facade.created_invoice["period_id"], "FY2026-06")
        self.assertEqual(facade.created_invoice["currency"], "USD")
        self.assertEqual(facade.created_invoice["payment_method"], "card")
        self.assertEqual(facade.created_refund["period_id"], "FY2026-06")
        self.assertEqual(facade.created_refund["currency"], "USD")
        self.assertEqual(facade.created_refund["reason"], "damaged box")
        self.assertEqual(facade.closed_period["period_id"], "FY2026-06")
        self.assertEqual(facade.closed_period["actor_id"], "usr_admin")
        self.assertEqual(facade.tax_report_calls[-1], ("FY2026-06", "USD"))
        self.assertEqual(window.currency_input.text(), "USD")
        self.assertEqual(window.status_label.text(), "Closed period FY2026-06")
        window.close()
        app.processEvents()

    def test_main_window_table_selections_fill_related_inputs(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        facade = _CapturingFacade(
            invoice_rows=[
                {
                    "invoice_id": "INV-SEL",
                    "customer_id": "WALK-IN",
                    "subtotal_minor": 25000,
                    "tax_minor": 4500,
                    "total_minor": 29500,
                }
            ],
            refund_availability_rows=[
                {
                    "invoice_id": "INV-SEL",
                    "item_id": "ITEM-SEL",
                    "unit_price_minor": 25000,
                    "original_quantity": 3,
                    "refunded_quantity": 1,
                    "remaining_quantity": 2,
                    "remaining_subtotal_minor": 50000,
                }
            ],
            stock_rows=[
                {
                    "item_id": "ITEM-SEL",
                    "sku": "SKU-SEL",
                    "name": "Selected Item",
                    "quantity_on_hand": 3,
                    "low_stock": False,
                }
            ],
        )
        window = ui_main.create_main_window(facade=facade)

        window.stock_table.setCurrentCell(0, 0)
        self.assertEqual(window.invoice_item_id_input.text(), "ITEM-SEL")
        self.assertEqual(window.refund_item_id_input.text(), "ITEM-SEL")
        self.assertEqual(window.item_name_input.text(), "Selected Item")

        window.invoice_table.setCurrentCell(0, 0)
        self.assertEqual(window.refund_invoice_id_input.text(), "INV-SEL")

        window.refund_availability_table.setCurrentCell(0, 0)
        self.assertEqual(window.refund_invoice_id_input.text(), "INV-SEL")
        self.assertEqual(window.refund_item_id_input.text(), "ITEM-SEL")
        self.assertEqual(window.refund_unit_price_input.value(), 25000)
        self.assertEqual(window.refund_quantity_input.value(), 2)
        window.close()
        app.processEvents()

    def test_main_window_disables_actions_when_required_inputs_are_missing(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        window = ui_main.create_main_window(facade=_CapturingFacade())

        self.assertTrue(window.register_item_button.isEnabled())
        self.assertTrue(window.create_invoice_button.isEnabled())
        self.assertTrue(window.create_refund_button.isEnabled())
        self.assertTrue(window.backup_button.isEnabled())
        self.assertTrue(window.close_period_button.isEnabled())
        self.assertFalse(window.restore_button.isEnabled())
        self.assertIn("Backup path", window.restore_button.toolTip())
        self.assertIn("Restore target", window.restore_button.toolTip())

        window.invoice_item_id_input.clear()

        self.assertFalse(window.create_invoice_button.isEnabled())
        self.assertIn("Item ID", window.create_invoice_button.toolTip())
        self.assertTrue(window.register_item_button.isEnabled())

        window.invoice_item_id_input.setText("ITEM-READY")

        self.assertTrue(window.create_invoice_button.isEnabled())
        self.assertEqual(window.create_invoice_button.toolTip(), "")

        window.period_input.clear()

        self.assertFalse(window.create_invoice_button.isEnabled())
        self.assertFalse(window.create_refund_button.isEnabled())
        self.assertFalse(window.close_period_button.isEnabled())
        self.assertIn("Period", window.close_period_button.toolTip())
        window.close()
        app.processEvents()

    def test_main_window_disables_operator_actions_without_active_operator(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        window = ui_main.create_main_window(
            facade=_CapturingFacade(actor_sessions=[])
        )

        self.assertFalse(window.register_item_button.isEnabled())
        self.assertFalse(window.create_invoice_button.isEnabled())
        self.assertFalse(window.create_refund_button.isEnabled())
        self.assertFalse(window.backup_button.isEnabled())
        self.assertFalse(window.close_period_button.isEnabled())
        self.assertIn("Operator", window.backup_button.toolTip())
        window.close()
        app.processEvents()

    def test_main_window_user_role_selection_and_update_flow(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            qt = ui_main._import_qt()
        except SystemExit as exc:
            self.skipTest(str(exc))

        app = qt.QApplication.instance() or qt.QApplication([])
        facade = _CapturingFacade(
            user_role_rows=[
                {
                    "actor_id": "usr_cashier",
                    "display_name": "Cashier",
                    "roles": ["cashier"],
                    "active": True,
                }
            ]
        )
        window = ui_main.create_main_window(facade=facade)

        self.assertEqual(window.users_table.rowCount(), 1)
        window.users_table.setCurrentCell(0, 0)

        self.assertEqual(window.user_actor_id_input.text(), "usr_cashier")
        self.assertTrue(window.user_cashier_input.isChecked())
        self.assertFalse(window.user_accountant_input.isChecked())
        self.assertTrue(window.update_user_roles_button.isEnabled())

        window.user_accountant_input.setChecked(True)
        window.update_user_roles()

        self.assertEqual(facade.updated_user_roles["actor_id"], "usr_admin")
        self.assertEqual(facade.updated_user_roles["target_actor_id"], "usr_cashier")
        self.assertEqual(
            facade.updated_user_roles["roles"], ["cashier", "accountant"]
        )
        self.assertTrue(facade.updated_user_roles["active"])
        self.assertEqual(window.status_label.text(), "Updated roles for usr_cashier")
        window.close()
        app.processEvents()


class _CapturingFacade:
    def __init__(
        self,
        *,
        actor_sessions: list[dict[str, object]] | None = None,
        user_role_rows: list[dict[str, object]] | None = None,
        invoice_rows: list[dict[str, object]] | None = None,
        refund_availability_rows: list[dict[str, object]] | None = None,
        stock_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.created_invoice: dict[str, object] = {}
        self.created_refund: dict[str, object] = {}
        self.closed_period: dict[str, object] = {}
        self.updated_user_roles: dict[str, object] = {}
        self.tax_report_calls: list[tuple[str, str]] = []
        self.actor_session_rows = actor_sessions
        self.user_role_rows = user_role_rows
        self.invoice_rows = invoice_rows or []
        self.refund_availability_rows = refund_availability_rows or []
        self.stock_rows = stock_rows or []

    def actor_sessions(self) -> list[dict[str, object]]:
        if self.actor_session_rows is not None:
            return self.actor_session_rows
        return [
            {
                "actor_id": "usr_admin",
                "display_name": "Admin",
                "roles": ["admin"],
            }
        ]

    def user_roles(self, payload):
        if self.user_role_rows is not None:
            return self.user_role_rows
        return [
            {
                "actor_id": "usr_admin",
                "display_name": "Admin",
                "roles": ["admin"],
                "active": True,
            }
        ]

    def update_user_roles(self, payload):
        self.updated_user_roles = dict(payload)
        return {
            "actor_id": payload["target_actor_id"],
            "display_name": "Updated User",
            "roles": payload["roles"],
            "active": payload["active"],
        }

    def create_invoice(self, payload):
        self.created_invoice = dict(payload)
        return {
            "invoice_id": payload["invoice_id"],
            "subtotal_minor": 100000,
            "tax_minor": 18000,
            "total_minor": 118000,
        }

    def create_refund(self, payload):
        self.created_refund = dict(payload)
        return {
            "refund_id": payload["refund_id"],
            "subtotal_minor": 50000,
            "tax_minor": 9000,
            "total_minor": 59000,
        }

    def close_period(self, payload):
        self.closed_period = dict(payload)
        return {
            "period_id": payload["period_id"],
            "status": "closed",
            "actor_id": payload["actor_id"],
        }

    def invoice_report(self, period_id):
        return {
            "rows": self.invoice_rows,
            "totals": [],
        }

    def refund_report(self, period_id):
        return {
            "rows": [],
            "totals": [],
        }

    def refund_availability_report(self, period_id):
        return {"rows": self.refund_availability_rows}

    def stock_report(self, *, low_stock_threshold: int = 0):
        return {"rows": self.stock_rows}

    def ledger_report(self, period_id):
        return {"rows": []}

    def tax_report(self, period_id, *, currency: str = "INR"):
        self.tax_report_calls.append((period_id, currency))
        return {"tax_payable_balance_minor": 0}

    def trial_balance_report(self, period_id):
        return {"is_balanced": True}


if __name__ == "__main__":
    unittest.main()
