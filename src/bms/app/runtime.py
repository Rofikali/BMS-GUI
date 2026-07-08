from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bms.app.auth import IdentityService
from bms.app.bootstrap import initialize_data_root
from bms.app.startup import StartupHealth, StartupHealthService, StartupState
from bms.app.use_cases import CommitStockMovementUseCase, CreateInvoiceUseCase, CreateRefundUseCase
from bms.domain.accounting import AccountingService
from bms.domain.billing import BillingService
from bms.domain.inventory import InventoryService
from bms.domain.reporting import ReportingService
from bms.services import BackupService
from bms.storage.file_store.core_store import CoreFileStore


class ApplicationRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApplicationRuntime:
    store: CoreFileStore
    startup_health: StartupHealth
    inventory: InventoryService
    accounting: AccountingService
    commit_stock_movement: CommitStockMovementUseCase
    billing: BillingService
    create_invoice: CreateInvoiceUseCase
    create_refund: CreateRefundUseCase
    reporting: ReportingService
    backup: BackupService
    identity: IdentityService


def start_application(data_root: Path) -> ApplicationRuntime:
    store = initialize_data_root(data_root)
    startup_health = StartupHealthService(store).inspect()
    if startup_health.state != StartupState.HEALTHY:
        raise ApplicationRuntimeError(
            f"cannot start application while storage is {startup_health.state.value}: {startup_health.message}"
        )

    inventory = InventoryService(store)
    accounting = AccountingService(store)
    billing = BillingService(store, inventory, accounting)
    return ApplicationRuntime(
        store=store,
        startup_health=startup_health,
        inventory=inventory,
        accounting=accounting,
        commit_stock_movement=CommitStockMovementUseCase(inventory, accounting),
        billing=billing,
        create_invoice=CreateInvoiceUseCase(billing),
        create_refund=CreateRefundUseCase(billing),
        reporting=ReportingService(store),
        backup=BackupService(store),
        identity=IdentityService(store),
    )
