from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from bms.app.commands import ApplicationCommandFacade, start_command_facade


class DemoDataError(ValueError):
    pass


@dataclass(frozen=True)
class DemoDataResult:
    data_root: Path
    invoice_total_minor: int
    refund_total_minor: int
    stock_rows: int
    trial_balance_balanced: bool


def seed_demo_data(data_root: Path) -> DemoDataResult:
    if data_root.exists() and any(data_root.iterdir()):
        raise DemoDataError(f"demo data root {data_root} is not empty")

    facade = start_command_facade(data_root)
    _register_items(facade)
    _stock_items(facade)
    invoice = facade.create_invoice(_invoice_payload())
    refund = facade.create_refund(_refund_payload())
    facade.close_period(_close_period_payload())
    stock_report = facade.stock_report(low_stock_threshold=5)
    trial_balance = facade.trial_balance_report("FY2026-05")

    return DemoDataResult(
        data_root=data_root,
        invoice_total_minor=int(invoice["total_minor"]),
        refund_total_minor=int(refund["total_minor"]),
        stock_rows=len(stock_report["rows"]),
        trial_balance_balanced=bool(trial_balance["is_balanced"]),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic BMS-GUI demo data root.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data") / "demo",
        help="Empty directory where demo data should be created.",
    )
    args = parser.parse_args(argv)
    result = seed_demo_data(args.data_root)
    print(
        "Demo data created: "
        f"data_root={result.data_root} "
        f"invoice_total_minor={result.invoice_total_minor} "
        f"refund_total_minor={result.refund_total_minor} "
        f"stock_rows={result.stock_rows} "
        f"trial_balance_balanced={result.trial_balance_balanced}"
    )


def _register_items(facade: ApplicationCommandFacade) -> None:
    for item in (
        {
            "item_id": "ITEM-DEMO-RICE",
            "sku": "SKU-RICE-5KG",
            "name": "Rice 5kg",
            "active": True,
            "business_unit": "grocery",
        },
        {
            "item_id": "ITEM-DEMO-OIL",
            "sku": "SKU-OIL-1L",
            "name": "Cooking Oil 1L",
            "active": True,
            "business_unit": "grocery",
        },
    ):
        facade.register_item(
            {
                "item": item,
                "actor_id": "usr_inventory",
                "created_at": "2026-05-14T09:00:00Z",
                "correlation_id": f"corr_demo_register_{item['item_id']}",
            }
        )


def _stock_items(facade: ApplicationCommandFacade) -> None:
    for movement_id, item_id, quantity in (
        ("MOV-DEMO-RICE-IN", "ITEM-DEMO-RICE", 40),
        ("MOV-DEMO-OIL-IN", "ITEM-DEMO-OIL", 25),
    ):
        facade.commit_stock_movement(
            {
                "movement_id": movement_id,
                "item_id": item_id,
                "movement_type": "adjustment",
                "quantity_delta": quantity,
                "timestamp": "2026-05-14T09:05:00Z",
                "actor_id": "usr_inventory",
                "reason": "demo opening stock",
                "source_module": "inventory",
                "source_document_id": "DEMO-STOCK-OPENING",
                "correlation_id": f"corr_{movement_id}",
            }
        )


def _invoice_payload() -> dict[str, object]:
    return {
        "invoice_id": "INV-DEMO-1001",
        "customer_id": "CUS-DEMO-WALK-IN",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T10:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_INV_DEMO_1001",
        "payment_method": "cash",
        "currency": "INR",
        "lines": [
            {
                "item_id": "ITEM-DEMO-RICE",
                "quantity": 2,
                "unit_price_minor": 65000,
                "description": "Rice 5kg",
            },
            {
                "item_id": "ITEM-DEMO-OIL",
                "quantity": 1,
                "unit_price_minor": 18000,
                "description": "Cooking Oil 1L",
            },
        ],
    }


def _refund_payload() -> dict[str, object]:
    return {
        "refund_id": "REF-DEMO-1001",
        "original_invoice_id": "INV-DEMO-1001",
        "period_id": "FY2026-05",
        "timestamp": "2026-05-14T11:00:00Z",
        "actor_id": "usr_cashier",
        "correlation_id": "corr_REF_DEMO_1001",
        "currency": "INR",
        "reason": "demo customer return",
        "lines": [
            {
                "item_id": "ITEM-DEMO-OIL",
                "quantity": 1,
                "unit_price_minor": 18000,
                "description": "Cooking Oil 1L",
                "restock": True,
            }
        ],
    }


def _close_period_payload() -> dict[str, object]:
    return {
        "period_id": "FY2026-05",
        "actor_id": "usr_accountant",
        "closed_at": "2026-05-14T18:00:00Z",
        "correlation_id": "corr_demo_close_FY2026_05",
    }


if __name__ == "__main__":
    main()
