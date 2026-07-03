from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import get_type_hints

from bms.domain.accounting.ports import AccountingPort
from bms.domain.accounting.service import AccountingService
from bms.domain.billing.service import BillingService
from bms.domain.inventory.ports import InventoryPort
from bms.domain.inventory.service import InventoryService
from bms.storage.file_store.core_store import CoreFileStore
from bms.storage.ports import DurableStorePort


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


if __name__ == "__main__":
    unittest.main()
