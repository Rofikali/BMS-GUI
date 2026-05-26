from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bms.app.bootstrap import initialize_data_root
from bms.app.startup import StartupHealth, StartupHealthService, StartupState
from bms.core import WalRecoveryResult


class ApplicationRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApplicationRecoveryResult:
    before: StartupHealth
    recovery: WalRecoveryResult
    after: StartupHealth


def recover_application_storage(
    data_root: Path,
    required_snapshot_path: Path | None = None,
) -> ApplicationRecoveryResult:
    store = initialize_data_root(data_root)
    health_service = StartupHealthService(store)
    before = health_service.inspect(required_snapshot_path)
    if before.state == StartupState.PROTECTED_MODE:
        raise ApplicationRecoveryError(f"cannot recover protected storage automatically: {before.message}")
    if before.state == StartupState.HEALTHY:
        recovery = store.recover_wal_startup(required_snapshot_path)
        return ApplicationRecoveryResult(before=before, recovery=recovery, after=health_service.inspect(required_snapshot_path))

    recovery = store.recover_wal_startup(required_snapshot_path)
    after = health_service.inspect(required_snapshot_path)
    if after.state != StartupState.HEALTHY:
        raise ApplicationRecoveryError(
            f"automatic recovery did not produce healthy storage: {after.state.value}"
        )
    return ApplicationRecoveryResult(before=before, recovery=recovery, after=after)
