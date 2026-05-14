from __future__ import annotations

import sys
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.core import BmsCoreError


def main() -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QPushButton,
            QStatusBar,
            QTabWidget,
            QTableWidget,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise SystemExit(
            "Qt/PySide6 could not start. If PySide6 is installed, check native Qt libraries. "
            f"Original import error: {exc}"
        ) from exc

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Business Management System")
            self.resize(1120, 720)
            self.store = initialize_data_root(Path("data"))

            tabs = QTabWidget()
            tabs.addTab(self._dashboard(), "Operations")
            tabs.addTab(self._placeholder_table("Invoices"), "Billing")
            tabs.addTab(self._placeholder_table("Stock movements"), "Inventory")
            tabs.addTab(self._placeholder_table("Journal entries"), "Accounting")
            tabs.addTab(self._placeholder_table("Audit records"), "Audit")
            self.setCentralWidget(tabs)
            self.setStatusBar(QStatusBar())
            self.statusBar().showMessage("C core loaded; file storage ready")

        def _dashboard(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel("Business Management System")
            title.setObjectName("title")
            subtitle = QLabel("Native C11 durability core with Python application orchestration")
            subtitle.setObjectName("subtitle")

            actions = QHBoxLayout()
            append_button = QPushButton("Append audit event")
            verify_button = QPushButton("Verify event log")
            wal_button = QPushButton("WAL smoke commit")
            append_button.clicked.connect(self._append_event)
            verify_button.clicked.connect(self._verify_events)
            wal_button.clicked.connect(self._wal_smoke)
            actions.addWidget(append_button)
            actions.addWidget(verify_button)
            actions.addWidget(wal_button)
            actions.addStretch(1)

            self.result = QLabel("Ready")
            self.result.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(title)
            layout.addWidget(subtitle)
            layout.addLayout(actions)
            layout.addWidget(self.result)
            layout.addStretch(1)
            return page

        def _placeholder_table(self, title: str) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            label = QLabel(title)
            label.setObjectName("section")
            table = QTableWidget(0, 4)
            table.setHorizontalHeaderLabels(["ID", "Type", "Status", "Updated"])
            layout.addWidget(label)
            layout.addWidget(table)
            return page

        def _append_event(self) -> None:
            try:
                seq = self.store.append_business_event(
                    "audit.record_created.v1",
                    "usr_admin",
                    {"action": "ui.audit_event", "target_type": "system", "target_id": "desktop"},
                )
                self.result.setText(f"Appended durable business event at sequence {seq}.")
            except (BmsCoreError, OSError) as exc:
                self.result.setText(str(exc))

        def _verify_events(self) -> None:
            try:
                count = self.store.verify_business_events()
                self.result.setText(f"Checksum verification passed for {count} event record(s).")
            except (BmsCoreError, OSError) as exc:
                self.result.setText(str(exc))

        def _wal_smoke(self) -> None:
            try:
                self.store.wal_smoke_commit()
                self.result.setText("WAL pending and committed records appended.")
            except (BmsCoreError, OSError) as exc:
                self.result.setText(str(exc))

    app = QApplication(sys.argv)
    app.setStyleSheet(
        """
        QMainWindow { background: #f7f8fa; }
        QLabel#title { font-size: 26px; font-weight: 700; color: #18202a; }
        QLabel#subtitle { font-size: 14px; color: #52606d; margin-bottom: 18px; }
        QLabel#section { font-size: 18px; font-weight: 650; color: #18202a; }
        QPushButton { padding: 8px 14px; border: 1px solid #b8c0cc; border-radius: 6px; background: #ffffff; }
        QPushButton:hover { background: #edf2f7; }
        QTabWidget::pane { border: 1px solid #d8dee8; background: #ffffff; }
        QTabBar::tab { padding: 9px 16px; }
        QTabBar::tab:selected { background: #ffffff; border-bottom: 2px solid #1f7a5c; }
        """
    )
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
