from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from typing import get_type_hints

from bms.domain.accounting.ports import AccountingPort
from bms.domain.accounting.service import AccountingService
from bms.domain.billing.service import BillingService
from bms.domain.inventory.ports import InventoryPort
from bms.domain.inventory.service import InventoryService
from bms.domain.reporting.service import ReportingService
from bms.storage.file_store.core_store import CoreFileStore
from bms.storage.ports import DurableStorePort

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src" / "bms"


class ArchitecturePortTests(unittest.TestCase):
    def test_domain_services_accept_storage_and_service_ports(self) -> None:
        billing_hints = get_type_hints(BillingService.__init__)
        accounting_hints = get_type_hints(AccountingService.__init__)
        inventory_hints = get_type_hints(InventoryService.__init__)

        self.assertIs(billing_hints["store"], DurableStorePort)
        self.assertIs(billing_hints["inventory"], InventoryPort)
        self.assertIs(billing_hints["accounting"], AccountingPort)
        self.assertIs(accounting_hints["store"], DurableStorePort)
        self.assertIs(inventory_hints["store"], DurableStorePort)
        self.assertIs(get_type_hints(ReportingService.__init__)["store"], DurableStorePort)

    def test_file_store_adapter_satisfies_domain_storage_contract_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = CoreFileStore(Path(temp_dir), core=_FakeDurabilityCore())

            required_paths = (
                "wal",
                "business_events",
                "journal_entries",
                "journal_lines",
                "items",
                "stock_movements",
                "invoices",
                "audit_records",
            )
            for attribute_name in required_paths:
                self.assertTrue(hasattr(store, attribute_name), attribute_name)

            self.assertTrue(callable(store.append_record))
            self.assertTrue(callable(store.append_business_event))
            self.assertTrue(callable(store.append_audit_record))
            self.assertTrue(callable(store.read_payloads))
            self.assertTrue(callable(store.core.append_wal_pending))
            self.assertTrue(callable(store.core.append_wal_committed))

    def test_ui_layer_does_not_import_domain_or_storage(self) -> None:
        violations = _imports_matching(
            SRC_ROOT / "ui",
            forbidden_prefixes=("bms.domain", "bms.storage"),
        )

        self.assertEqual(violations, [])

    def test_domain_layer_does_not_import_ui_app_or_concrete_storage_adapters(self) -> None:
        violations = _imports_matching(
            SRC_ROOT / "domain",
            forbidden_prefixes=(
                "bms.app",
                "bms.ui",
                "bms.storage.file_store",
            ),
        )

        self.assertEqual(violations, [])

    def test_reporting_does_not_mutate_business_state(self) -> None:
        reporting_source = (SRC_ROOT / "domain" / "reporting" / "service.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(".append_record(", reporting_source)
        self.assertNotIn(".append_business_event(", reporting_source)
        self.assertNotIn(".append_audit_record(", reporting_source)
        self.assertNotIn(".append_wal_pending(", reporting_source)
        self.assertNotIn(".append_wal_committed(", reporting_source)


class _FakeDurabilityCore:
    def append_record(self, path: Path, record: object) -> int:
        return 1

    def verify_file(self, path: Path) -> int:
        return 0

    def append_wal_pending(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
        payload: dict[str, object],
    ) -> None:
        return None

    def append_wal_committed(
        self,
        wal_path: Path,
        transaction_id: str,
        created_at: str,
        actor_id: str,
        correlation_id: str,
    ) -> None:
        return None

    def inspect_wal_startup(self, wal_path: Path, required_snapshot_path: Path | None = None) -> object:
        return object()

    def recover_wal_startup(self, wal_path: Path, required_snapshot_path: Path | None = None) -> object:
        return object()


def _imports_matching(
    root: Path,
    *,
    forbidden_prefixes: tuple[str, ...],
) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported_names = _imported_module_names(node)
            for imported_name in imported_names:
                if any(
                    imported_name == prefix or imported_name.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                ):
                    violations.append(
                        f"{path.relative_to(PROJECT_ROOT)} imports {imported_name}"
                    )
    return violations


def _imported_module_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom) and node.module:
        return (node.module,)
    return ()


if __name__ == "__main__":
    unittest.main()
