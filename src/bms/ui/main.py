from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from bms.app import (
    ApplicationCommandError,
    ApplicationCommandFacade,
    start_command_facade,
)


def _import_qt() -> SimpleNamespace:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
            QFormLayout,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QCheckBox,
            QComboBox,
            QSpinBox,
            QStatusBar,
            QStyle,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise SystemExit(
            "Qt/PySide6 could not start. If PySide6 is installed, check native Qt libraries. "
            f"Original import error: {exc}"
        ) from exc
    return SimpleNamespace(**locals())


def build_main_window_class():
    qt = _import_qt()

    class MainWindow(qt.QMainWindow):
        def __init__(
            self,
            facade: ApplicationCommandFacade | None = None,
            data_root: Path | None = None,
        ) -> None:
            super().__init__()
            self.facade = facade or start_command_facade(
                data_root or _default_data_root()
            )
            self.setWindowTitle("BMS-GUI")
            self.resize(1160, 760)
            self._initial_item_id = _new_business_id("ITEM")
            self._initial_invoice_id = _new_business_id("INV")

            self.status_label = qt.QLabel("Ready")
            self.status_label.setTextInteractionFlags(
                qt.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.actor_selector = qt.QComboBox()
            for session in self.facade.actor_sessions():
                roles = ", ".join(session["roles"])
                self.actor_selector.addItem(
                    f"{session['display_name']} ({roles})", session["actor_id"]
                )
            if self.actor_selector.count() == 0:
                self.actor_selector.addItem("No active operator", "")
            self.period_input = qt.QLineEdit("FY2026-05")
            self.period_input.setMaximumWidth(120)
            self.period_input.editingFinished.connect(self._refresh_reports_from_input)
            self.currency_input = qt.QLineEdit("INR")
            self.currency_input.setMaximumWidth(70)
            self.currency_input.editingFinished.connect(self._refresh_reports_from_input)

            tabs = qt.QTabWidget()
            tabs.addTab(self._build_inventory_tab(), "Inventory")
            tabs.addTab(self._build_billing_tab(), "Billing")
            tabs.addTab(self._build_reports_tab(), "Reports")
            tabs.addTab(self._build_backup_tab(), "Backup")
            self.setCentralWidget(tabs)

            status_bar = qt.QStatusBar()
            status_bar.addWidget(self.status_label, 1)
            status_bar.addPermanentWidget(qt.QLabel("Period"))
            status_bar.addPermanentWidget(self.period_input)
            status_bar.addPermanentWidget(qt.QLabel("Currency"))
            status_bar.addPermanentWidget(self.currency_input)
            status_bar.addPermanentWidget(self.actor_selector)
            self.setStatusBar(status_bar)
            self._connect_action_state_inputs()
            self._sync_action_states()
            self.refresh_reports()

        def _build_inventory_tab(self):
            page = qt.QWidget()
            layout = qt.QGridLayout(page)
            layout.setColumnStretch(1, 1)

            form_group = qt.QGroupBox("Item Setup")
            form = qt.QFormLayout(form_group)
            self.item_id_input = qt.QLineEdit(self._initial_item_id)
            self.sku_input = qt.QLineEdit(self._initial_item_id.replace("ITEM", "SKU", 1))
            self.item_name_input = qt.QLineEdit("New Item")
            self.opening_stock_input = _spin_box(qt, 0, 1_000_000, 5)
            form.addRow("Item ID", self.item_id_input)
            form.addRow("SKU", self.sku_input)
            form.addRow("Name", self.item_name_input)
            form.addRow("Opening stock", self.opening_stock_input)

            actions = qt.QHBoxLayout()
            self.register_item_button = qt.QPushButton("Register")
            self.register_item_button.setIcon(
                self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DialogApplyButton)
            )
            self.register_item_button.clicked.connect(self.register_item)
            actions.addWidget(self.register_item_button)
            actions.addStretch(1)
            form.addRow(actions)

            stock_group = qt.QGroupBox("Stock")
            stock_layout = qt.QVBoxLayout(stock_group)
            self.stock_table = _table(
                qt, ["Item", "SKU", "Name", "On hand", "Low stock"]
            )
            self.stock_table.itemSelectionChanged.connect(self._apply_stock_selection)
            stock_layout.addWidget(self.stock_table)

            layout.addWidget(form_group, 0, 0)
            layout.addWidget(stock_group, 0, 1)
            return page

        def _build_billing_tab(self):
            page = qt.QWidget()
            layout = qt.QGridLayout(page)
            layout.setColumnStretch(1, 1)

            form_group = qt.QGroupBox("Invoice")
            form = qt.QFormLayout(form_group)
            self.invoice_id_input = qt.QLineEdit(self._initial_invoice_id)
            self.customer_id_input = qt.QLineEdit("WALK-IN")
            self.invoice_item_id_input = qt.QLineEdit(self._initial_item_id)
            self.invoice_quantity_input = _spin_box(qt, 1, 1_000_000, 2)
            self.invoice_unit_price_input = _spin_box(qt, 0, 1_000_000_000, 50000)
            self.invoice_payment_method_input = qt.QComboBox()
            for payment_method in ("cash", "card", "upi", "bank_transfer"):
                self.invoice_payment_method_input.addItem(payment_method)
            form.addRow("Invoice ID", self.invoice_id_input)
            form.addRow("Customer ID", self.customer_id_input)
            form.addRow("Item ID", self.invoice_item_id_input)
            form.addRow("Quantity", self.invoice_quantity_input)
            form.addRow("Unit price minor", self.invoice_unit_price_input)
            form.addRow("Payment method", self.invoice_payment_method_input)

            actions = qt.QHBoxLayout()
            self.create_invoice_button = qt.QPushButton("Create")
            self.create_invoice_button.setIcon(
                self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DialogSaveButton)
            )
            self.create_invoice_button.clicked.connect(self.create_invoice)
            actions.addWidget(self.create_invoice_button)
            actions.addStretch(1)
            form.addRow(actions)

            totals_group = qt.QGroupBox("Invoice Result")
            totals = qt.QFormLayout(totals_group)
            self.invoice_result_label = qt.QLabel("No invoice posted")
            self.invoice_result_label.setTextInteractionFlags(
                qt.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.invoice_subtotal_label = qt.QLabel("0")
            self.invoice_tax_label = qt.QLabel("0")
            self.invoice_total_label = qt.QLabel("0")
            totals.addRow("Invoice", self.invoice_result_label)
            totals.addRow("Subtotal", self.invoice_subtotal_label)
            totals.addRow("Tax", self.invoice_tax_label)
            totals.addRow("Total", self.invoice_total_label)

            refund_group = qt.QGroupBox("Refund")
            refund_form = qt.QFormLayout(refund_group)
            self.refund_id_input = qt.QLineEdit(_new_business_id("REF"))
            self.refund_invoice_id_input = qt.QLineEdit(self._initial_invoice_id)
            self.refund_item_id_input = qt.QLineEdit(self._initial_item_id)
            self.refund_quantity_input = _spin_box(qt, 1, 1_000_000, 1)
            self.refund_unit_price_input = _spin_box(qt, 0, 1_000_000_000, 50000)
            self.refund_reason_input = qt.QLineEdit("customer return")
            self.refund_restock_input = qt.QCheckBox()
            self.refund_restock_input.setChecked(True)
            refund_form.addRow("Refund ID", self.refund_id_input)
            refund_form.addRow("Original invoice", self.refund_invoice_id_input)
            refund_form.addRow("Item ID", self.refund_item_id_input)
            refund_form.addRow("Quantity", self.refund_quantity_input)
            refund_form.addRow("Unit price minor", self.refund_unit_price_input)
            refund_form.addRow("Reason", self.refund_reason_input)
            refund_form.addRow("Restock", self.refund_restock_input)

            refund_actions = qt.QHBoxLayout()
            self.create_refund_button = qt.QPushButton("Refund")
            self.create_refund_button.setIcon(
                self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DialogResetButton)
            )
            self.create_refund_button.clicked.connect(self.create_refund)
            refund_actions.addWidget(self.create_refund_button)
            refund_actions.addStretch(1)
            refund_form.addRow(refund_actions)

            refund_totals_group = qt.QGroupBox("Refund Result")
            refund_totals = qt.QFormLayout(refund_totals_group)
            self.refund_result_label = qt.QLabel("No refund posted")
            self.refund_result_label.setTextInteractionFlags(
                qt.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.refund_subtotal_label = qt.QLabel("0")
            self.refund_tax_label = qt.QLabel("0")
            self.refund_total_label = qt.QLabel("0")
            refund_totals.addRow("Refund", self.refund_result_label)
            refund_totals.addRow("Subtotal", self.refund_subtotal_label)
            refund_totals.addRow("Tax", self.refund_tax_label)
            refund_totals.addRow("Total", self.refund_total_label)

            layout.addWidget(form_group, 0, 0)
            layout.addWidget(totals_group, 0, 1)
            layout.addWidget(refund_group, 1, 0)
            layout.addWidget(refund_totals_group, 1, 1)
            return page

        def _build_reports_tab(self):
            page = qt.QWidget()
            layout = qt.QGridLayout(page)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)

            summary_group = qt.QGroupBox("Summary")
            summary = qt.QFormLayout(summary_group)
            self.report_invoice_total_label = qt.QLabel("0")
            self.report_refund_total_label = qt.QLabel("0")
            self.report_refundable_remaining_label = qt.QLabel("0")
            self.report_tax_payable_label = qt.QLabel("0")
            self.report_trial_balance_label = qt.QLabel("Unknown")
            summary.addRow("Invoice total", self.report_invoice_total_label)
            summary.addRow("Refund total", self.report_refund_total_label)
            summary.addRow(
                "Refundable remaining", self.report_refundable_remaining_label
            )
            summary.addRow("Tax payable", self.report_tax_payable_label)
            summary.addRow("Trial balance", self.report_trial_balance_label)

            self.invoice_table = _table(
                qt, ["Invoice", "Customer", "Subtotal", "Tax", "Total"]
            )
            self.invoice_table.itemSelectionChanged.connect(self._apply_invoice_selection)
            self.refund_table = _table(
                qt, ["Refund", "Invoice", "Reason", "Subtotal", "Tax", "Total"]
            )
            self.refund_availability_table = _table(
                qt, ["Invoice", "Item", "Unit price", "Sold", "Refunded", "Remaining"]
            )
            self.refund_availability_table.itemSelectionChanged.connect(
                self._apply_refund_availability_selection
            )
            self.ledger_table = _table(
                qt, ["Account", "Name", "Debit", "Credit", "Balance"]
            )

            layout.addWidget(summary_group, 0, 0, 1, 2)
            layout.addWidget(self.invoice_table, 1, 0)
            layout.addWidget(self.refund_table, 1, 1)
            layout.addWidget(self.refund_availability_table, 2, 0, 1, 2)
            layout.addWidget(self.ledger_table, 3, 0, 1, 2)
            return page

        def _build_backup_tab(self):
            page = qt.QWidget()
            layout = qt.QVBoxLayout(page)

            actions = qt.QHBoxLayout()
            self.backup_button = qt.QPushButton("Backup")
            self.backup_button.setIcon(
                self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DriveHDIcon)
            )
            self.backup_button.clicked.connect(self.create_backup)
            actions.addWidget(self.backup_button)
            actions.addStretch(1)

            self.backup_path_label = qt.QLabel("No backup created")
            self.backup_path_label.setTextInteractionFlags(
                qt.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.backup_counts_table = _table(qt, ["File", "Records"])

            restore_group = qt.QGroupBox("Restore Validation")
            restore_form = qt.QFormLayout(restore_group)
            self.restore_backup_path_input = qt.QLineEdit()
            self.restore_target_input = qt.QLineEdit()
            self.restore_button = qt.QPushButton("Validate Restore")
            self.restore_button.setIcon(
                self.style().standardIcon(qt.QStyle.StandardPixmap.SP_BrowserReload)
            )
            self.restore_button.clicked.connect(self.restore_backup)
            restore_form.addRow("Backup path", self.restore_backup_path_input)
            restore_form.addRow("Restore target", self.restore_target_input)
            restore_form.addRow(self.restore_button)

            layout.addLayout(actions)
            layout.addWidget(self.backup_path_label)
            layout.addWidget(self.backup_counts_table)
            layout.addWidget(restore_group)
            return page

        def register_item(self) -> None:
            try:
                item_id = self._required_text("Item ID", self.item_id_input)
                self.facade.register_item(
                    {
                        "item": {
                            "item_id": item_id,
                            "sku": self._required_text("SKU", self.sku_input),
                            "name": self._required_text("Name", self.item_name_input),
                            "active": True,
                        },
                        "actor_id": self._required_actor_id(),
                        "created_at": _timestamp(),
                        "correlation_id": f"corr_item_{item_id}",
                    }
                )
                opening_stock = self.opening_stock_input.value()
                if opening_stock:
                    self.facade.commit_stock_movement(
                        {
                            "movement_id": f"MOV-OPEN-{item_id}-{uuid4().hex[:8]}",
                            "item_id": item_id,
                            "movement_type": "adjustment",
                            "quantity_delta": opening_stock,
                            "timestamp": _timestamp(),
                            "actor_id": self._required_actor_id(),
                            "reason": "opening stock",
                            "source_module": "inventory",
                            "source_document_id": f"OPEN-{item_id}",
                            "correlation_id": f"corr_open_{item_id}",
                        }
                    )
                self.invoice_item_id_input.setText(item_id)
                self.refund_item_id_input.setText(item_id)
                self._set_status(f"Registered {item_id}")
                self._sync_action_states()
                self.refresh_reports()
            except Exception as exc:
                self._show_error(exc)

        def create_invoice(self) -> None:
            try:
                invoice_id = self._required_text("Invoice ID", self.invoice_id_input)
                result = self.facade.create_invoice(
                    {
                        "invoice_id": invoice_id,
                        "customer_id": self._required_text(
                            "Customer ID", self.customer_id_input
                        ),
                        "period_id": self._current_period_id(),
                        "timestamp": _timestamp(),
                        "actor_id": self._required_actor_id(),
                        "correlation_id": f"corr_{invoice_id}",
                        "payment_method": self.invoice_payment_method_input.currentText(),
                        "currency": self._current_currency(),
                        "lines": [
                            {
                                "item_id": self._required_text(
                                    "Invoice item ID", self.invoice_item_id_input
                                ),
                                "quantity": self.invoice_quantity_input.value(),
                                "unit_price_minor": self.invoice_unit_price_input.value(),
                                "description": self._required_text(
                                    "Name", self.item_name_input
                                ),
                            }
                        ],
                    }
                )
                self.invoice_result_label.setText(str(result["invoice_id"]))
                self.invoice_subtotal_label.setText(str(result["subtotal_minor"]))
                self.invoice_tax_label.setText(str(result["tax_minor"]))
                self.invoice_total_label.setText(str(result["total_minor"]))
                self.refund_invoice_id_input.setText(str(result["invoice_id"]))
                self._set_status(f"Created invoice {invoice_id}")
                self.invoice_id_input.setText(_new_business_id("INV"))
                self.refund_id_input.setText(_new_business_id("REF"))
                self._sync_action_states()
                self.refresh_reports()
            except Exception as exc:
                self._show_error(exc)

        def create_refund(self) -> None:
            try:
                refund_id = self._required_text("Refund ID", self.refund_id_input)
                result = self.facade.create_refund(
                    {
                        "refund_id": refund_id,
                        "original_invoice_id": self._required_text(
                            "Original invoice", self.refund_invoice_id_input
                        ),
                        "period_id": self._current_period_id(),
                        "timestamp": _timestamp(),
                        "actor_id": self._required_actor_id(),
                        "correlation_id": f"corr_{refund_id}",
                        "currency": self._current_currency(),
                        "reason": self._required_text(
                            "Refund reason", self.refund_reason_input
                        ),
                        "lines": [
                            {
                                "item_id": self._required_text(
                                    "Refund item ID", self.refund_item_id_input
                                ),
                                "quantity": self.refund_quantity_input.value(),
                                "unit_price_minor": self.refund_unit_price_input.value(),
                                "description": self._required_text(
                                    "Name", self.item_name_input
                                ),
                                "restock": self.refund_restock_input.isChecked(),
                            }
                        ],
                    }
                )
                self.refund_result_label.setText(str(result["refund_id"]))
                self.refund_subtotal_label.setText(str(result["subtotal_minor"]))
                self.refund_tax_label.setText(str(result["tax_minor"]))
                self.refund_total_label.setText(str(result["total_minor"]))
                self._set_status(f"Created refund {refund_id}")
                self.refund_id_input.setText(_new_business_id("REF"))
                self._sync_action_states()
                self.refresh_reports()
            except Exception as exc:
                self._show_error(exc)

        def create_backup(self) -> None:
            try:
                result = self.facade.create_backup(
                    {
                        "actor_id": self._required_actor_id(),
                        "created_at": _timestamp(),
                    }
                )
                self.backup_path_label.setText(result["backup_path"])
                self.restore_backup_path_input.setText(result["backup_path"])
                if not self.restore_target_input.text().strip():
                    backup_path = Path(result["backup_path"])
                    restore_base = (
                        backup_path.parents[2]
                        if len(backup_path.parents) > 2
                        else backup_path.parent.parent
                    )
                    self.restore_target_input.setText(
                        str(restore_base / "restore-preview")
                    )
                _set_rows(
                    qt,
                    self.backup_counts_table,
                    [
                        [name, str(count)]
                        for name, count in sorted(
                            result["verified_record_counts"].items()
                        )
                    ],
                )
                self._set_status("Backup created")
            except Exception as exc:
                self._show_error(exc)

        def restore_backup(self) -> None:
            try:
                result = self.facade.restore_backup(
                    {
                        "actor_id": self._required_actor_id(),
                        "backup_path": self._required_text(
                            "Backup path", self.restore_backup_path_input
                        ),
                        "restore_root": self._required_text(
                            "Restore target", self.restore_target_input
                        ),
                    }
                )
                _set_rows(
                    qt,
                    self.backup_counts_table,
                    [
                        [name, str(count)]
                        for name, count in sorted(
                            result["verified_record_counts"].items()
                        )
                    ],
                )
                self._set_status(f"Restore validated at {result['restored_root']}")
            except Exception as exc:
                self._show_error(exc)

        def _connect_action_state_inputs(self) -> None:
            for widget in (
                self.item_id_input,
                self.sku_input,
                self.item_name_input,
                self.invoice_id_input,
                self.customer_id_input,
                self.invoice_item_id_input,
                self.refund_id_input,
                self.refund_invoice_id_input,
                self.refund_item_id_input,
                self.refund_reason_input,
                self.period_input,
                self.currency_input,
                self.restore_backup_path_input,
                self.restore_target_input,
            ):
                widget.textChanged.connect(self._sync_action_states)
            self.actor_selector.currentIndexChanged.connect(self._sync_action_states)

        def _sync_action_states(self, *_args) -> None:
            action_requirements = (
                (
                    self.register_item_button,
                    (
                        ("Operator", self._current_actor_id()),
                        ("Item ID", self.item_id_input.text()),
                        ("SKU", self.sku_input.text()),
                        ("Name", self.item_name_input.text()),
                    ),
                ),
                (
                    self.create_invoice_button,
                    (
                        ("Operator", self._current_actor_id()),
                        ("Invoice ID", self.invoice_id_input.text()),
                        ("Customer ID", self.customer_id_input.text()),
                        ("Item ID", self.invoice_item_id_input.text()),
                        ("Name", self.item_name_input.text()),
                        ("Period", self.period_input.text()),
                        ("Currency", self.currency_input.text()),
                    ),
                ),
                (
                    self.create_refund_button,
                    (
                        ("Operator", self._current_actor_id()),
                        ("Refund ID", self.refund_id_input.text()),
                        ("Original invoice", self.refund_invoice_id_input.text()),
                        ("Item ID", self.refund_item_id_input.text()),
                        ("Name", self.item_name_input.text()),
                        ("Reason", self.refund_reason_input.text()),
                        ("Period", self.period_input.text()),
                        ("Currency", self.currency_input.text()),
                    ),
                ),
                (
                    self.backup_button,
                    (("Operator", self._current_actor_id()),),
                ),
                (
                    self.restore_button,
                    (
                        ("Operator", self._current_actor_id()),
                        ("Backup path", self.restore_backup_path_input.text()),
                        ("Restore target", self.restore_target_input.text()),
                    ),
                ),
            )
            for button, requirements in action_requirements:
                missing = [
                    label for label, value in requirements if not str(value).strip()
                ]
                button.setEnabled(not missing)
                button.setToolTip(
                    "" if not missing else "Required: " + ", ".join(missing)
                )

        def refresh_reports(self) -> None:
            period_id = self._current_period_id()
            currency = self._current_currency()
            invoice_report = self.facade.invoice_report(period_id)
            refund_report = self.facade.refund_report(period_id)
            refund_availability = self.facade.refund_availability_report(period_id)
            stock_report = self.facade.stock_report(low_stock_threshold=3)
            ledger_report = self.facade.ledger_report(period_id)
            tax_report = self.facade.tax_report(period_id, currency=currency)
            trial_balance = self.facade.trial_balance_report(period_id)

            invoice_total = sum(
                total["total_minor"] for total in invoice_report["totals"]
            )
            refund_total = sum(
                total["total_minor"] for total in refund_report["totals"]
            )
            refundable_remaining = sum(
                row["remaining_subtotal_minor"] for row in refund_availability["rows"]
            )
            self.report_invoice_total_label.setText(str(invoice_total))
            self.report_refund_total_label.setText(str(refund_total))
            self.report_refundable_remaining_label.setText(str(refundable_remaining))
            self.report_tax_payable_label.setText(
                str(tax_report["tax_payable_balance_minor"])
            )
            self.report_trial_balance_label.setText(
                "Balanced" if trial_balance["is_balanced"] else "Unbalanced"
            )

            _set_rows(
                qt,
                self.stock_table,
                [
                    [
                        row["item_id"],
                        row["sku"],
                        row["name"],
                        str(row["quantity_on_hand"]),
                        "Yes" if row["low_stock"] else "No",
                    ]
                    for row in stock_report["rows"]
                ],
            )
            _set_rows(
                qt,
                self.invoice_table,
                [
                    [
                        row["invoice_id"],
                        row["customer_id"],
                        str(row["subtotal_minor"]),
                        str(row["tax_minor"]),
                        str(row["total_minor"]),
                    ]
                    for row in invoice_report["rows"]
                ],
            )
            _set_rows(
                qt,
                self.refund_table,
                [
                    [
                        row["refund_id"],
                        row["original_invoice_id"],
                        row["reason"],
                        str(row["subtotal_minor"]),
                        str(row["tax_minor"]),
                        str(row["total_minor"]),
                    ]
                    for row in refund_report["rows"]
                ],
            )
            _set_rows(
                qt,
                self.refund_availability_table,
                [
                    [
                        row["invoice_id"],
                        row["item_id"],
                        str(row["unit_price_minor"]),
                        str(row["original_quantity"]),
                        str(row["refunded_quantity"]),
                        str(row["remaining_quantity"]),
                    ]
                    for row in refund_availability["rows"]
                ],
            )
            _set_rows(
                qt,
                self.ledger_table,
                [
                    [
                        row["account_code"],
                        row["account_name"],
                        str(row["debit_total_minor"]),
                        str(row["credit_total_minor"]),
                        str(row["balance_minor"]),
                    ]
                    for row in ledger_report["rows"]
                ],
            )

        def _refresh_reports_from_input(self) -> None:
            try:
                self.refresh_reports()
            except Exception as exc:
                self._show_error(exc)

        def _current_actor_id(self) -> str:
            return str(self.actor_selector.currentData() or "")

        def _required_actor_id(self) -> str:
            actor_id = self._current_actor_id()
            if not actor_id:
                raise ValueError("Operator is required")
            return actor_id

        def _apply_stock_selection(self) -> None:
            selected_row = self.stock_table.currentRow()
            if selected_row < 0 or not hasattr(self, "invoice_item_id_input"):
                return
            item_id = _table_text(self.stock_table, selected_row, 0)
            item_name = _table_text(self.stock_table, selected_row, 2)
            if item_id:
                self.invoice_item_id_input.setText(item_id)
                self.refund_item_id_input.setText(item_id)
            if item_name:
                self.item_name_input.setText(item_name)

        def _apply_invoice_selection(self) -> None:
            selected_row = self.invoice_table.currentRow()
            if selected_row < 0:
                return
            invoice_id = _table_text(self.invoice_table, selected_row, 0)
            if invoice_id:
                self.refund_invoice_id_input.setText(invoice_id)

        def _apply_refund_availability_selection(self) -> None:
            selected_row = self.refund_availability_table.currentRow()
            if selected_row < 0:
                return
            invoice_id = _table_text(self.refund_availability_table, selected_row, 0)
            item_id = _table_text(self.refund_availability_table, selected_row, 1)
            unit_price = _table_text(self.refund_availability_table, selected_row, 2)
            remaining = _table_text(self.refund_availability_table, selected_row, 5)
            if invoice_id:
                self.refund_invoice_id_input.setText(invoice_id)
            if item_id:
                self.refund_item_id_input.setText(item_id)
            if unit_price.isdigit():
                self.refund_unit_price_input.setValue(int(unit_price))
            if remaining.isdigit():
                self.refund_quantity_input.setValue(max(int(remaining), 1))

        def _current_period_id(self) -> str:
            return self._required_text("Period", self.period_input)

        def _current_currency(self) -> str:
            currency = self._required_text("Currency", self.currency_input).upper()
            self.currency_input.setText(currency)
            return currency

        def _required_text(self, label: str, widget) -> str:
            value = widget.text().strip()
            if not value:
                raise ValueError(f"{label} is required")
            return value

        def _set_status(self, message: str) -> None:
            self.status_label.setText(message)

        def _show_error(self, exc: Exception) -> None:
            if isinstance(exc, ApplicationCommandError):
                message = exc.user_message
            else:
                message = str(exc)
            self._set_status(message)
            qt.QMessageBox.warning(self, "BMS-GUI", message)

    return MainWindow


def create_main_window(
    facade: ApplicationCommandFacade | None = None, data_root: Path | None = None
):
    return build_main_window_class()(facade=facade, data_root=data_root)


def _table(qt: SimpleNamespace, headers: list[str]):
    table = qt.QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(qt.QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeMode.Stretch)
    return table


def _set_rows(qt: SimpleNamespace, table, rows: list[list[str]]) -> None:
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            item = qt.QTableWidgetItem(value)
            item.setFlags(item.flags() & ~qt.Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_index, column_index, item)


def _table_text(table, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""


def _spin_box(qt: SimpleNamespace, minimum: int, maximum: int, value: int):
    spin_box = qt.QSpinBox()
    spin_box.setRange(minimum, maximum)
    spin_box.setValue(value)
    spin_box.setAlignment(qt.Qt.AlignmentFlag.AlignRight)
    return spin_box


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _new_business_id(prefix: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{timestamp}-{uuid4().hex[:6].upper()}"


def _default_data_root() -> Path:
    return Path(os.environ.get("BMS_DATA_ROOT", "data"))


def _stylesheet() -> str:
    return """
    QMainWindow { background: #f6f7f9; color: #1f2933; }
    QTabWidget::pane { border: 1px solid #d7dde5; background: #ffffff; }
    QTabBar::tab { padding: 9px 18px; border: 1px solid #d7dde5; background: #edf1f5; }
    QTabBar::tab:selected { background: #ffffff; border-bottom-color: #ffffff; }
    QGroupBox { font-weight: 650; border: 1px solid #d7dde5; margin-top: 12px; padding: 12px 10px 10px 10px; background: #ffffff; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
    QLineEdit, QSpinBox, QComboBox { padding: 6px 8px; border: 1px solid #b9c3cf; background: #ffffff; min-height: 22px; }
    QPushButton { padding: 7px 13px; border: 1px solid #9aa7b5; background: #ffffff; min-width: 86px; }
    QPushButton:hover { background: #eef3f8; }
    QHeaderView::section { background: #edf1f5; border: 0; border-bottom: 1px solid #cfd7e2; padding: 6px; font-weight: 650; }
    QTableWidget { border: 1px solid #d7dde5; gridline-color: #edf1f5; background: #ffffff; }
    QStatusBar { background: #ffffff; border-top: 1px solid #d7dde5; }
    """


def main() -> int:
    qt = _import_qt()
    app = qt.QApplication(sys.argv)
    app.setStyleSheet(_stylesheet())
    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
