from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path

from bms.app.commands import start_command_facade


class ReleaseCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseCheckResult:
    data_root: Path
    restore_root: Path
    invoice_total_minor: int
    refund_total_minor: int
    refundable_remaining_minor: int
    stock_on_hand: int
    tax_payable_minor: int
    trial_balance_balanced: bool
    restored_trial_balance_balanced: bool


def run_release_check(data_root: Path, restore_root: Path) -> ReleaseCheckResult:
    _require_empty_or_missing(data_root, "data root")
    _require_empty_or_missing(restore_root, "restore root")

    facade = start_command_facade(data_root)
    facade.register_item(_register_item_payload())
    facade.commit_stock_movement(_stock_movement_payload())
    invoice = facade.create_invoice(_invoice_payload())
    refund = facade.create_refund(_refund_payload())

    invoice_report = facade.invoice_report("FY2026-05")
    refund_report = facade.refund_report("FY2026-05")
    refund_availability = facade.refund_availability_report("FY2026-05")
    stock_report = facade.stock_report(low_stock_threshold=3)
    tax_report = facade.tax_report("FY2026-05")
    trial_balance = facade.trial_balance_report("FY2026-05")

    facade.close_period(_close_period_payload())
    _assert_closed_period_blocks_invoice(facade)

    backup = facade.create_backup(_backup_payload())
    restore = facade.restore_backup(
        {
            "actor_id": "usr_admin",
            "backup_path": backup["backup_path"],
            "restore_root": str(restore_root),
        }
    )
    if restore["verified_record_counts"] != backup["verified_record_counts"]:
        raise ReleaseCheckError("restored record counts do not match backup manifest")

    restored = start_command_facade(restore_root)
    restored_trial_balance = restored.trial_balance_report("FY2026-05")

    invoice_total = _first_total(invoice_report)
    refund_total = _first_total(refund_report)
    refundable_remaining = sum(row["remaining_subtotal_minor"] for row in refund_availability["rows"])
    stock_on_hand = stock_report["rows"][0]["quantity_on_hand"] if stock_report["rows"] else 0

    _assert_equal(invoice["total_minor"], 118000, "invoice command total")
    _assert_equal(refund["total_minor"], 59000, "refund command total")
    _assert_equal(invoice_total, 118000, "invoice report total")
    _assert_equal(refund_total, 59000, "refund report total")
    _assert_equal(refundable_remaining, 50000, "refundable remaining")
    _assert_equal(stock_on_hand, 4, "stock on hand")
    _assert_equal(tax_report["tax_payable_balance_minor"], 9000, "tax payable")
    if not trial_balance["is_balanced"]:
        raise ReleaseCheckError("trial balance is not balanced")
    if not restored_trial_balance["is_balanced"]:
        raise ReleaseCheckError("restored trial balance is not balanced")

    return ReleaseCheckResult(
        data_root=data_root,
        restore_root=restore_root,
        invoice_total_minor=invoice_total,
        refund_total_minor=refund_total,
        refundable_remaining_minor=refundable_remaining,
        stock_on_hand=stock_on_hand,
        tax_payable_minor=int(tax_report["tax_payable_balance_minor"]),
        trial_balance_balanced=bool(trial_balance["is_balanced"]),
        restored_trial_balance_balanced=bool(restored_trial_balance["is_balanced"]),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the BMS-GUI MVP release acceptance check.")
    parser.add_argument("--data-root", type=Path, help="Empty data root for the check.")
    parser.add_argument("--restore-root", type=Path, help="Empty restore root for backup validation.")
    args = parser.parse_args(argv)

    if args.data_root is None or args.restore_root is None:
        with tempfile.TemporaryDirectory(prefix="bms-release-check-") as temp_dir:
            base = Path(temp_dir)
            result = run_release_check(
                args.data_root or base / "live",
                args.restore_root or base / "restored",
            )
            _print_result(result)
        return

    _print_result(run_release_check(args.data_root, args.restore_root))


def _print_result(result: ReleaseCheckResult) -> None:
    print(
        "Release check passed: "
        f"invoice_total_minor={result.invoice_total_minor} "
        f"refund_total_minor={result.refund_total_minor} "
        f"refundable_remaining_minor={result.refundable_remaining_minor} "
        f"stock_on_hand={result.stock_on_hand} "
        f"tax_payable_minor={result.tax_payable_minor} "
        f"trial_balance_balanced={result.trial_balance_balanced} "
        f"restored_trial_balance_balanced={result.restored_trial_balance_balanced}"
    )


def _require_empty_or_missing(path: Path, label: str) -> None:
    if path.exists() and any(path.iterdir()):
        raise ReleaseCheckError(f"{label} {path} is not empty")


def _assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise ReleaseCheckError(f"{label} expected {expected}, got {actual}")


def _assert_closed_period_blocks_invoice(facade: object) -> None:
    try:
        facade.create_invoice(
            {
                **_invoice_payload(),
                "invoice_id": "INV-RELEASE-CLOSED",
                "correlation_id": "corr_INV_RELEASE_CLOSED",
            }
        )
    except Exception as exc:
        if "closed" in str(exc):
            return
        raise
    raise ReleaseCheckError("closed-period invoice was accepted")


def _first_total(report: dict[str, object]) -> int:
    totals = report.get("totals")
    if not isinstance(totals, list) or not totals:
        raise ReleaseCheckError("report has no totals")
    total = totals[0]
    if not isinstance(total, dict):
        raise ReleaseCheckError("report total row is invalid")
    value = total.get("total_minor")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReleaseCheckError("report total is invalid")
    return value


def _backup_payload() -> dict[str, object]:
    return {
        "actor_id": "usr_admin",
        "created_at": "2026-05-14T12:00:00Z",
    }


def _close_period_payload() -> dict[str, object]:
    return {
        "period_id": "FY2026-05",
        "actor_id": "usr_accountant",
        "closed_at": "2026-05-14T11:00:00Z",
        "correlation_id": "corr_release_close_FY2026_05",
    }


def _register_item_payload() -> dict[str, object]:
    return {
        "item": {"item_id": "ITEM-RELEASE-1", "sku": "SKU-RELEASE-1", "name": "Release Test Item", "active": True},
        "actor_id": "usr_inventory",
        "created_at": "2026-05-14T08:00:00Z",
        "correlation_id": "corr_release_item",
    }


def _stock_movement_payload() -> dict[str, object]:
    return {
        "movement_id": "MOV-RELEASE-IN",
        "item_id": "ITEM-RELEASE-1",
        "movement_type": "adjustment",
        "quantity_delta": 5,
        "timestamp": "2026-05-14T08:05:00Z",
        "actor_id": "usr_inventory",
        "reason": "release check opening stock",
        "source_module": "inventory",
        "source_document_id": "REL-STOCK-1",
        "correlation_id": "corr_release_stock",
    }


def _invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-RELEASE-1",
        "customer_id": "CUS-RELEASE",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T09:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_RELEASE_1",
        "payment_method": "cash",
        "currency": "INR",
        "lines": [
            {
                "item_id": "ITEM-RELEASE-1",
                "quantity": 2,
                "unit_price_minor": 50000,
                "description": "Release Test Item",
            }
        ],
    }


def _refund_payload() -> dict[str, object]:
    return {
        "refund_id": "REF-RELEASE-1",
        "original_invoice_id": "INV-RELEASE-1",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T10:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_REF_RELEASE_1",
        "currency": "INR",
        "reason": "release check partial return",
        "lines": [
            {
                "item_id": "ITEM-RELEASE-1",
                "quantity": 1,
                "unit_price_minor": 50000,
                "description": "Release Test Item",
                "restock": True,
            }
        ],
    }


if __name__ == "__main__":
    main()
