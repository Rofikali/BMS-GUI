from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bms.app import ApplicationRecoveryError, recover_application_storage
from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingService
from bms.domain.billing import (
    BillingError,
    BillingService,
    CreateInvoiceCommand,
    CreateRefundCommand,
    InvoiceLineCommand,
    RefundLineCommand,
)
from bms.domain.inventory import InventoryService, Item, StockMovementCommand


class BillingServiceTests(unittest.TestCase):
    def test_create_invoice_completes_inventory_accounting_and_audit_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)

            result = billing.create_invoice(_invoice("INV-1", quantity=2, unit_price_minor=50000))

            self.assertEqual(result.subtotal_minor, 100000)
            self.assertEqual(result.tax_minor, 18000)
            self.assertEqual(result.total_minor, 118000)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertTrue(accounting.get_trial_balance("FY2026-05").is_balanced)
            balances = accounting.get_ledger_balances("FY2026-05")
            self.assertEqual(balances["1000"].balance_minor, 118000)
            self.assertEqual(balances["4000"].balance_minor, 100000)
            self.assertEqual(balances["2100"].balance_minor, 18000)
            self.assertEqual(store.core.verify_file(store.invoices), 1)
            self.assertEqual(store.core.verify_file(store.invoice_lines), 1)
            self.assertEqual(store.core.verify_file(store.stock_movements), 2)
            self.assertEqual(store.core.verify_file(store.journal_entries), 1)

    def test_create_invoice_writes_parent_wal_pending_and_committed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=3)

            billing.create_invoice(_invoice("INV-WAL", quantity=1, unit_price_minor=50000))

            wal_payloads = store.read_payloads(store.wal)
            parent_pending = [
                payload
                for payload in wal_payloads
                if payload["state"] == "pending"
                and payload["payload"].get("operation") == "billing.create_invoice"
                and payload["payload"].get("invoice_id") == "INV-WAL"
            ]
            self.assertEqual(len(parent_pending), 1)
            transaction_id = parent_pending[0]["transaction_id"]
            parent_committed = [
                payload
                for payload in wal_payloads
                if payload["state"] == "committed" and payload["transaction_id"] == transaction_id
            ]
            self.assertEqual(len(parent_committed), 1)
            self.assertEqual(parent_pending[0]["payload"]["journal_id"], "jrn_INV-WAL")
            self.assertEqual(parent_pending[0]["payload"]["movement_ids"], ["mov_INV-WAL_1"])
            self.assertEqual(parent_pending[0]["payload"]["expected_records"]["billing.invoices"], 1)
            self.assertEqual(parent_pending[0]["payload"]["expected_records"]["accounting.journal_lines"], 3)

    def test_accounting_failure_leaves_recovery_visible_parent_pending_without_invoice_or_stock_sale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            inventory = InventoryService(store)
            _register_and_stock_item(inventory, quantity=3)
            billing = BillingService(store, inventory, _FailingAccountingService(store))

            with self.assertRaisesRegex(RuntimeError, "accounting unavailable"):
                billing.create_invoice(_invoice("INV-FAIL-ACCT", quantity=1, unit_price_minor=50000))

            wal_payloads = store.read_payloads(store.wal)
            parent_pending = [
                payload
                for payload in wal_payloads
                if payload["state"] == "pending"
                and payload["payload"].get("operation") == "billing.create_invoice"
                and payload["payload"].get("invoice_id") == "INV-FAIL-ACCT"
            ]
            self.assertEqual(len(parent_pending), 1)
            transaction_id = parent_pending[0]["transaction_id"]
            self.assertFalse(
                any(payload["state"] == "committed" and payload["transaction_id"] == transaction_id for payload in wal_payloads)
            )
            self.assertEqual(store.core.verify_file(store.invoices), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 0)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)

    def test_inventory_failure_after_journal_blocks_automatic_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            setup_inventory = InventoryService(store)
            _register_and_stock_item(setup_inventory, quantity=3)
            accounting = AccountingService(store)
            billing = BillingService(store, _FailingInventoryService(store), accounting)

            with self.assertRaisesRegex(RuntimeError, "inventory unavailable"):
                billing.create_invoice(_invoice("INV-FAIL-STOCK", quantity=1, unit_price_minor=50000))

            self.assertEqual(store.core.verify_file(store.invoices), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 1)
            self.assertTrue(accounting.get_trial_balance("FY2026-05").is_balanced)
            with self.assertRaisesRegex(ApplicationRecoveryError, "durable side effects"):
                recover_application_storage(root)

    def test_invoice_survives_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store, billing, inventory, _accounting = _services(root)
            _register_and_stock_item(inventory, quantity=4)
            billing.create_invoice(_invoice("INV-2", quantity=1, unit_price_minor=25000))

            restarted_store, _billing, restarted_inventory, restarted_accounting = _services(root)
            invoice_payloads = restarted_store.read_payloads(restarted_store.invoices)

            self.assertEqual(invoice_payloads[0]["invoice_id"], "INV-2")
            self.assertEqual(invoice_payloads[0]["total_minor"], 29500)
            self.assertEqual(restarted_inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertTrue(restarted_accounting.get_trial_balance("FY2026-05").is_balanced)

    def test_duplicate_invoice_does_not_double_post(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-3", quantity=2, unit_price_minor=50000))

            with self.assertRaisesRegex(BillingError, "already completed"):
                billing.create_invoice(_invoice("INV-3", quantity=2, unit_price_minor=50000))

            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertEqual(store.core.verify_file(store.invoices), 1)
            self.assertEqual(store.core.verify_file(store.journal_entries), 1)
            self.assertEqual(accounting.get_trial_balance("FY2026-05").debit_total_minor, 118000)

    def test_insufficient_stock_blocks_invoice_before_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=1)

            with self.assertRaisesRegex(BillingError, "insufficient stock"):
                billing.create_invoice(_invoice("INV-4", quantity=2, unit_price_minor=50000))

            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 1)
            self.assertEqual(store.core.verify_file(store.stock_movements), 1)
            self.assertEqual(store.core.verify_file(store.invoices), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 0)

    def test_closed_period_blocks_invoice_before_stock_moves(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=2)
            accounting.close_period(
                "FY2026-05",
                actor_id="usr_accountant",
                closed_at="2026-05-14T01:00:00Z",
                correlation_id="corr_close_FY2026_05",
            )

            with self.assertRaisesRegex(BillingError, "closed"):
                billing.create_invoice(_invoice("INV-5", quantity=1, unit_price_minor=50000))

            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 2)
            self.assertEqual(store.core.verify_file(store.invoices), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 0)

    def test_inactive_item_blocks_invoice_before_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            inventory.register_item(
                Item("ITEM-1", "SKU-1", "Test Item", active=False),
                actor_id="usr_inventory",
                created_at="2026-05-14T00:00:00Z",
                correlation_id="corr_item_inactive",
            )

            with self.assertRaisesRegex(BillingError, "inactive item"):
                billing.create_invoice(_invoice("INV-INACTIVE", quantity=1, unit_price_minor=50000))

            self.assertEqual(store.core.verify_file(store.invoices), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 0)
            self.assertEqual(store.core.verify_file(store.stock_movements), 0)

    def test_invoice_writes_billing_audit_and_sale_completed_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=3)

            billing.create_invoice(_invoice("INV-6", quantity=1, unit_price_minor=100000))

            audit_payloads = store.read_payloads(store.audit_records)
            event_payloads = store.read_payloads(store.business_events)
            self.assertIn("billing.invoice_created", [payload["action"] for payload in audit_payloads])
            self.assertIn("billing.sale_completed.v1", [payload["event_type"] for payload in event_payloads])

    def test_create_refund_posts_reversal_journal_restock_and_audit_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-REFUND-1", quantity=2, unit_price_minor=50000))

            refund = billing.create_refund(_refund("REF-1", original_invoice_id="INV-REFUND-1", restock=True))

            self.assertEqual(refund.subtotal_minor, 100000)
            self.assertEqual(refund.tax_minor, 18000)
            self.assertEqual(refund.total_minor, 118000)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 5)
            self.assertTrue(accounting.get_trial_balance("FY2026-05").is_balanced)
            balances = accounting.get_ledger_balances("FY2026-05")
            self.assertEqual(balances["1000"].balance_minor, 0)
            self.assertEqual(balances["4000"].balance_minor, 0)
            self.assertEqual(balances["2100"].balance_minor, 0)
            self.assertEqual(store.core.verify_file(store.refunds), 1)
            self.assertEqual(store.core.verify_file(store.refund_lines), 1)
            self.assertEqual(store.core.verify_file(store.stock_movements), 3)
            audit_actions = [payload["action"] for payload in store.read_payloads(store.audit_records)]
            event_types = [payload["event_type"] for payload in store.read_payloads(store.business_events)]
            self.assertIn("billing.refund_created", audit_actions)
            self.assertIn("billing.refund_completed.v1", event_types)

    def test_refund_without_restock_does_not_move_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-REFUND-NORESTOCK", quantity=2, unit_price_minor=50000))

            refund = billing.create_refund(_refund("REF-NORESTOCK", original_invoice_id="INV-REFUND-NORESTOCK", restock=False))

            self.assertEqual(refund.movement_ids, ())
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 3)
            self.assertEqual(store.core.verify_file(store.stock_movements), 2)

    def test_refund_unknown_invoice_is_rejected_before_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, _inventory, _accounting = _services(Path(temp_dir))

            with self.assertRaisesRegex(BillingError, "original invoice"):
                billing.create_refund(_refund("REF-UNKNOWN", original_invoice_id="INV-MISSING"))

            self.assertEqual(store.core.verify_file(store.refunds), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 0)

    def test_duplicate_refund_does_not_double_post(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, _accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-REFUND-DUP", quantity=2, unit_price_minor=50000))
            billing.create_refund(_refund("REF-DUP", original_invoice_id="INV-REFUND-DUP"))

            with self.assertRaisesRegex(BillingError, "already completed"):
                billing.create_refund(_refund("REF-DUP", original_invoice_id="INV-REFUND-DUP"))

            self.assertEqual(store.core.verify_file(store.refunds), 1)
            self.assertEqual(store.core.verify_file(store.journal_entries), 2)
            self.assertEqual(inventory.get_stock_on_hand("ITEM-1"), 5)

    def test_closed_period_blocks_refund_before_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store, billing, inventory, accounting = _services(Path(temp_dir))
            _register_and_stock_item(inventory, quantity=5)
            billing.create_invoice(_invoice("INV-REFUND-CLOSED", quantity=2, unit_price_minor=50000))
            accounting.close_period(
                "FY2026-05",
                actor_id="usr_accountant",
                closed_at="2026-05-14T04:00:00Z",
                correlation_id="corr_close_FY2026_05",
            )

            with self.assertRaisesRegex(BillingError, "closed"):
                billing.create_refund(_refund("REF-CLOSED", original_invoice_id="INV-REFUND-CLOSED"))

            self.assertEqual(store.core.verify_file(store.refunds), 0)
            self.assertEqual(store.core.verify_file(store.journal_entries), 1)


class _FailingAccountingService:
    def __init__(self, store: object) -> None:
        self.store = store

    def is_period_closed(self, period_id: str) -> bool:
        return False

    def post_journal(self, command: object) -> object:
        raise RuntimeError("accounting unavailable")


class _FailingInventoryService(InventoryService):
    def commit_movement(self, command: StockMovementCommand) -> object:
        raise RuntimeError("inventory unavailable")


def _services(root: Path) -> tuple[object, BillingService, InventoryService, AccountingService]:
    store = initialize_data_root(root)
    inventory = InventoryService(store)
    accounting = AccountingService(store)
    billing = BillingService(store, inventory, accounting)
    return store, billing, inventory, accounting


def _register_and_stock_item(inventory: InventoryService, *, quantity: int) -> None:
    inventory.register_item(
        Item("ITEM-1", "SKU-1", "Test Item"),
        actor_id="usr_inventory",
        created_at="2026-05-14T00:00:00Z",
        correlation_id="corr_item_ITEM-1",
    )
    inventory.adjust_stock(
        movement_id="MOV-STOCK-IN",
        item_id="ITEM-1",
        quantity_delta=quantity,
        timestamp="2026-05-14T00:00:00Z",
        actor_id="usr_inventory",
        reason="opening stock",
        source_document_id="STK-1001",
        correlation_id="corr_stock_in",
    )


def _invoice(invoice_id: str, *, quantity: int, unit_price_minor: int) -> CreateInvoiceCommand:
    return CreateInvoiceCommand(
        invoice_id=invoice_id,
        customer_id="CUS-1",
        period_id="FY2026-05",
        timestamp="2026-05-14T02:00:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{invoice_id}",
        payment_method="cash",
        currency="INR",
        lines=(InvoiceLineCommand("ITEM-1", quantity, unit_price_minor, "Test Item"),),
    )


def _refund(refund_id: str, *, original_invoice_id: str, restock: bool = True) -> CreateRefundCommand:
    return CreateRefundCommand(
        refund_id=refund_id,
        original_invoice_id=original_invoice_id,
        period_id="FY2026-05",
        timestamp="2026-05-14T03:00:00Z",
        actor_id="usr_cashier",
        correlation_id=f"corr_{refund_id}",
        currency="INR",
        reason="customer return",
        lines=(RefundLineCommand("ITEM-1", 2, 50000, "Test Item", restock=restock),),
    )


if __name__ == "__main__":
    unittest.main()
