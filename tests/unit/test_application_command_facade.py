from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bms.app import ApplicationCommandError, ApplicationErrorCode, start_command_facade
from bms.app.bootstrap import initialize_data_root
from bms.domain.accounting import AccountingError
from bms.domain.billing import BillingError


class ApplicationCommandFacadeTests(unittest.TestCase):
    def test_facade_runs_billing_slice_from_raw_payloads_and_exports_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            item = facade.register_item(_register_item_payload())
            stock_in = facade.commit_stock_movement(_stock_movement_payload("MOV-FACADE-IN", 5, "adjustment"))
            invoice = facade.create_invoice(_invoice_payload())
            refund = facade.create_refund(_refund_payload())

            invoice_report = facade.invoice_report("FY2026-05")
            refund_report = facade.refund_report("FY2026-05")
            refund_availability = facade.refund_availability_report("FY2026-05")
            business_unit_revenue = facade.business_unit_revenue_report("FY2026-05")
            stock_report = facade.stock_report(low_stock_threshold=3)
            ledger_report = facade.ledger_report("FY2026-05")
            profit_and_loss = facade.profit_and_loss_report("FY2026-05")
            tax_report = facade.tax_report("FY2026-05")
            trial_balance = facade.trial_balance_report("FY2026-05")
            backup = facade.create_backup(_backup_payload())
            restore = facade.restore_backup(
                {
                    "actor_id": "usr_admin",
                    "backup_path": backup["backup_path"],
                    "restore_root": str(Path(temp_dir) / "restored"),
                }
            )
            restored = start_command_facade(Path(temp_dir) / "restored")
            restored_invoice_report = restored.invoice_report("FY2026-05")
            restored_refund_report = restored.refund_report("FY2026-05")
            restored_availability = restored.refund_availability_report("FY2026-05")
            restored_stock_report = restored.stock_report(low_stock_threshold=3)
            restored_tax_report = restored.tax_report("FY2026-05")
            restored_trial_balance = restored.trial_balance_report("FY2026-05")

            self.assertEqual(item["item_id"], "ITEM-1")
            self.assertEqual(stock_in["quantity_on_hand"], 5)
            self.assertEqual(invoice["invoice_id"], "INV-FACADE-1")
            self.assertEqual(invoice["total_minor"], 118000)
            self.assertEqual(refund["refund_id"], "REF-FACADE-1")
            self.assertEqual(refund["original_invoice_id"], "INV-FACADE-1")
            self.assertEqual(refund["total_minor"], 59000)
            self.assertEqual(len(refund["movement_ids"]), 1)
            self.assertEqual(invoice_report["totals"][0]["total_minor"], 118000)
            self.assertEqual(refund_report["rows"][0]["refund_id"], "REF-FACADE-1")
            self.assertEqual(refund_report["totals"][0]["total_minor"], 59000)
            self.assertEqual(refund_availability["rows"][0]["refunded_quantity"], 1)
            self.assertEqual(refund_availability["rows"][0]["remaining_quantity"], 1)
            self.assertEqual(business_unit_revenue["rows"][0]["business_unit"], "retail")
            self.assertEqual(business_unit_revenue["rows"][0]["net_revenue_minor"], 50000)
            self.assertEqual(stock_report["rows"][0]["quantity_on_hand"], 4)
            self.assertEqual({row["account_code"] for row in ledger_report["rows"]}, {"1000", "2100", "4000"})
            self.assertEqual(profit_and_loss["net_revenue_minor"], 50000)
            self.assertEqual(profit_and_loss["net_income_minor"], 50000)
            self.assertEqual(tax_report["invoice_tax_collected_minor"], 18000)
            self.assertTrue(trial_balance["is_balanced"])
            self.assertTrue(Path(backup["backup_path"]).exists())
            self.assertEqual(backup["verified_record_counts"]["invoices"], 1)
            self.assertEqual(backup["verified_record_counts"]["refunds"], 1)
            self.assertEqual(restore["verified_record_counts"], backup["verified_record_counts"])
            self.assertEqual(restored_invoice_report["totals"][0]["total_minor"], 118000)
            self.assertEqual(restored_refund_report["totals"][0]["total_minor"], 59000)
            self.assertEqual(restored_availability["rows"][0]["remaining_quantity"], 1)
            self.assertEqual(restored_stock_report["rows"][0]["quantity_on_hand"], 4)
            self.assertEqual(restored_tax_report["tax_payable_balance_minor"], 9000)
            self.assertTrue(restored_trial_balance["is_balanced"])

    def test_facade_maps_restore_non_empty_target_to_business_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "live"
            restore_root = Path(temp_dir) / "restored"
            facade = start_command_facade(root)
            backup = facade.create_backup(_backup_payload())
            restore_root.mkdir()
            (restore_root / "existing.txt").write_text("existing", encoding="utf-8")

            with self.assertRaises(ApplicationCommandError) as context:
                facade.restore_backup(
                    {
                        "actor_id": "usr_admin",
                        "backup_path": backup["backup_path"],
                        "restore_root": str(restore_root),
                    }
                )

            self.assertEqual(context.exception.code, ApplicationErrorCode.BUSINESS_RULE)
            self.assertEqual(context.exception.operation, "backup.restore")

    def test_facade_lists_actor_sessions_from_identity_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            sessions = {session["actor_id"]: session["roles"] for session in facade.actor_sessions()}

            self.assertEqual(sessions["usr_admin"], ["admin"])
            self.assertEqual(sessions["usr_cashier"], ["cashier"])
            self.assertEqual(sessions["usr_accountant"], ["accountant"])

    def test_facade_lists_and_updates_user_roles_from_admin_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            initial_roles = {
                row["actor_id"]: row for row in facade.user_roles({"actor_id": "usr_admin"})
            }
            updated = facade.update_user_roles(
                {
                    "actor_id": "usr_admin",
                    "target_actor_id": "usr_cashier",
                    "roles": ["cashier", "accountant"],
                    "active": True,
                    "updated_at": "2026-05-14T04:30:00Z",
                    "correlation_id": "corr_roles_usr_cashier",
                }
            )
            reloaded = start_command_facade(Path(temp_dir))
            sessions = {
                session["actor_id"]: session["roles"]
                for session in reloaded.actor_sessions()
            }

            self.assertEqual(initial_roles["usr_cashier"]["roles"], ["cashier"])
            self.assertEqual(updated["actor_id"], "usr_cashier")
            self.assertEqual(updated["roles"], ["cashier", "accountant"])
            self.assertEqual(sessions["usr_cashier"], ["cashier", "accountant"])

    def test_facade_rejects_unauthorized_user_role_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            with self.assertRaises(ApplicationCommandError) as context:
                facade.update_user_roles(
                    {
                        "actor_id": "usr_cashier",
                        "target_actor_id": "usr_accountant",
                        "roles": ["admin"],
                        "active": True,
                        "updated_at": "2026-05-14T04:30:00Z",
                        "correlation_id": "corr_roles_blocked",
                    }
                )

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "auth.update_user_roles")

    def test_facade_rejects_removing_last_active_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            facade.update_user_roles(
                {
                    "actor_id": "usr_admin",
                    "target_actor_id": "usr_inventory",
                    "roles": ["cashier"],
                    "active": False,
                    "updated_at": "2026-05-14T04:25:00Z",
                    "correlation_id": "corr_roles_inventory_no_admin",
                }
            )

            with self.assertRaises(ApplicationCommandError) as context:
                facade.update_user_roles(
                    {
                        "actor_id": "usr_admin",
                        "target_actor_id": "usr_admin",
                        "roles": ["cashier"],
                        "active": True,
                        "updated_at": "2026-05-14T04:30:00Z",
                        "correlation_id": "corr_roles_no_admin",
                    }
                )

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "auth.update_user_roles")

    def test_facade_authorizes_from_roles_file_not_payload_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            initialize_data_root(root)
            (root / "users" / "roles.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "assignments": [
                            {"actor_id": "usr_admin", "roles": ["admin"]},
                            {"actor_id": "usr_cashier", "roles": ["accountant"]},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            facade = start_command_facade(root)

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_invoice(_invoice_payload())

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "billing.create_invoice")

    def test_facade_rejects_unauthorized_command_before_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            payload = _invoice_payload()
            payload["actor_id"] = "usr_accountant"

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_invoice(payload)

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "billing.create_invoice")
            self.assertEqual(context.exception.cause_type, "AuthorizationError")

    def test_facade_rejects_unauthorized_refund_before_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            payload = _refund_payload()
            payload["actor_id"] = "usr_accountant"

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_refund(payload)

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "billing.create_refund")
            self.assertEqual(context.exception.cause_type, "AuthorizationError")

    def test_facade_rejects_malformed_boundary_payload_before_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            payload = _invoice_payload()
            payload["lines"] = [
                {
                    "item_id": "ITEM-1",
                    "quantity": "2",
                    "unit_price_minor": 50000,
                    "description": "Test Item",
                }
            ]

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_invoice(payload)

            self.assertEqual(context.exception.code, ApplicationErrorCode.VALIDATION)
            self.assertEqual(context.exception.operation, "billing.create_invoice")
            self.assertEqual(context.exception.cause_type, "ValidationError")

    def test_facade_rejects_malformed_refund_payload_before_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            payload = _refund_payload()
            payload["lines"] = [
                {
                    "item_id": "ITEM-1",
                    "quantity": "1",
                    "unit_price_minor": 50000,
                    "description": "Test Item",
                    "restock": True,
                }
            ]

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_refund(payload)

            self.assertEqual(context.exception.code, ApplicationErrorCode.VALIDATION)
            self.assertEqual(context.exception.operation, "billing.create_refund")
            self.assertEqual(context.exception.cause_type, "ValidationError")

    def test_facade_still_leaves_accounting_invariants_to_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            with self.assertRaises(ApplicationCommandError) as context:
                facade.post_journal(
                    {
                        "journal_id": "JRN-FACADE-BAD",
                        "period_id": "FY2026-05",
                        "timestamp": "2026-05-14T02:00:00Z",
                        "actor_id": "usr_accountant",
                        "source_module": "billing",
                        "source_document_id": "INV-FACADE-BAD",
                        "correlation_id": "corr_JRN_FACADE_BAD",
                        "description": "Unbalanced facade payload",
                        "lines": [
                            {"account_code": "1000", "debit_minor": 118000, "currency": "INR"},
                            {"account_code": "4000", "credit_minor": 100000, "currency": "INR"},
                        ],
                    }
                )

            self.assertEqual(context.exception.code, ApplicationErrorCode.BUSINESS_RULE)
            self.assertEqual(context.exception.operation, "accounting.post_journal")
            self.assertIsInstance(context.exception.__cause__, AccountingError)

    def test_facade_closes_period_and_blocks_later_financial_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            facade.register_item(_register_item_payload())
            facade.commit_stock_movement(_stock_movement_payload("MOV-CLOSE-FACADE-IN", 5, "adjustment"))
            facade.create_invoice(_invoice_payload())

            closed = facade.close_period(_close_period_payload())
            blocked_invoice = _invoice_payload()
            blocked_invoice["invoice_id"] = "INV-FACADE-CLOSED"
            blocked_invoice["correlation_id"] = "corr_INV_FACADE_CLOSED"

            self.assertEqual(closed["period_id"], "FY2026-05")
            self.assertEqual(closed["status"], "closed")
            self.assertEqual(closed["actor_id"], "usr_accountant")
            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_invoice(blocked_invoice)

            self.assertEqual(context.exception.code, ApplicationErrorCode.BUSINESS_RULE)
            self.assertEqual(context.exception.operation, "billing.create_invoice")
            self.assertIsInstance(context.exception.__cause__, BillingError)

    def test_facade_rejects_unauthorized_period_close_before_service_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            payload = _close_period_payload()
            payload["actor_id"] = "usr_cashier"

            with self.assertRaises(ApplicationCommandError) as context:
                facade.close_period(payload)

            self.assertEqual(context.exception.code, ApplicationErrorCode.UNAUTHORIZED)
            self.assertEqual(context.exception.operation, "accounting.close_period")

    def test_facade_maps_insufficient_stock_to_business_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))
            facade.register_item(_register_item_payload())

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_invoice(_invoice_payload())

            self.assertEqual(context.exception.code, ApplicationErrorCode.BUSINESS_RULE)
            self.assertEqual(context.exception.operation, "billing.create_invoice")
            self.assertIsInstance(context.exception.__cause__, BillingError)

    def test_facade_maps_unknown_invoice_refund_to_business_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            facade = start_command_facade(Path(temp_dir))

            with self.assertRaises(ApplicationCommandError) as context:
                facade.create_refund(_refund_payload())

            self.assertEqual(context.exception.code, ApplicationErrorCode.BUSINESS_RULE)
            self.assertEqual(context.exception.operation, "billing.create_refund")
            self.assertIsInstance(context.exception.__cause__, BillingError)

    def test_start_command_facade_maps_protected_storage_to_app_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = initialize_data_root(root)
            store.wal.write_text(
                '{"schema_version":1,"sequence":1,"record_id":"wal_bad","record_type":"wal.transaction","created_at":"2026-05-14T00:00:00Z","actor_id":"usr_test","correlation_id":"corr_bad","idempotency_key":"wal_bad","payload":{"transaction_id":"txn_bad","state":"pending","payload":{}},"checksum":"sha256:bad"}\n',
                encoding="utf-8",
            )

            with self.assertRaises(ApplicationCommandError) as context:
                start_command_facade(root)

            self.assertEqual(context.exception.code, ApplicationErrorCode.PROTECTED_MODE)
            self.assertEqual(context.exception.operation, "app.start")


def _backup_payload() -> dict[str, object]:
    return {
        "actor_id": "usr_admin",
        "created_at": "2026-05-14T03:00:00Z",
    }


def _close_period_payload() -> dict[str, object]:
    return {
        "period_id": "FY2026-05",
        "actor_id": "usr_accountant",
        "closed_at": "2026-05-14T04:00:00Z",
        "correlation_id": "corr_close_FY2026_05",
    }


def _register_item_payload() -> dict[str, object]:
    return {
        "item": {"item_id": "ITEM-1", "sku": "SKU-1", "name": "Test Item", "active": True},
        "actor_id": "usr_inventory",
        "created_at": "2026-05-14T00:00:00Z",
        "correlation_id": "corr_item_ITEM-1",
    }


def _stock_movement_payload(movement_id: str, quantity_delta: int, movement_type: str) -> dict[str, object]:
    return {
        "movement_id": movement_id,
        "item_id": "ITEM-1",
        "movement_type": movement_type,
        "quantity_delta": quantity_delta,
        "timestamp": "2026-05-14T00:05:00Z",
        "actor_id": "usr_inventory",
        "reason": "opening stock",
        "source_module": "inventory",
        "source_document_id": "STK-1001",
        "correlation_id": f"corr_{movement_id}",
    }


def _invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-FACADE-1",
        "customer_id": "CUS-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T02:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_FACADE_1",
        "payment_method": "cash",
        "currency": "INR",
        "lines": [
            {
                "item_id": "ITEM-1",
                "quantity": 2,
                "unit_price_minor": 50000,
                "description": "Test Item",
            }
        ],
    }


def _refund_payload() -> dict[str, object]:
    return {
        "refund_id": "REF-FACADE-1",
        "original_invoice_id": "INV-FACADE-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T02:30:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_REF_FACADE_1",
        "currency": "INR",
        "reason": "customer return",
        "lines": [
            {
                "item_id": "ITEM-1",
                "quantity": 1,
                "unit_price_minor": 50000,
                "description": "Test Item",
                "restock": True,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
