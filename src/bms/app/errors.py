from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError

from bms.app.auth import AuthorizationError
from bms.app.recovery import ApplicationRecoveryError
from bms.app.runtime import ApplicationRuntimeError
from bms.core import BmsCoreError
from bms.domain.accounting import AccountingError
from bms.domain.billing import BillingError
from bms.domain.events import EventSchemaError
from bms.domain.inventory import InventoryError
from bms.domain.reporting import ReportingError
from bms.services import BackupError


class ApplicationErrorCode(StrEnum):
    VALIDATION = "validation_error"
    UNAUTHORIZED = "unauthorized"
    BUSINESS_RULE = "business_rule_violation"
    STORAGE = "storage_error"
    RECOVERY_REQUIRED = "recovery_required"
    PROTECTED_MODE = "protected_mode"
    UNEXPECTED = "unexpected_error"


@dataclass(frozen=True)
class ApplicationCommandError(Exception):
    code: ApplicationErrorCode
    user_message: str
    operation: str
    cause_type: str

    def __str__(self) -> str:
        return f"{self.code.value}: {self.user_message}"


def map_application_error(operation: str, exc: Exception) -> ApplicationCommandError:
    if isinstance(exc, ApplicationCommandError):
        return exc
    if isinstance(exc, ValidationError):
        return ApplicationCommandError(
            code=ApplicationErrorCode.VALIDATION,
            user_message="Please check the entered fields.",
            operation=operation,
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, AuthorizationError):
        return ApplicationCommandError(
            code=ApplicationErrorCode.UNAUTHORIZED,
            user_message=str(exc),
            operation=operation,
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, (AccountingError, BillingError, InventoryError, ReportingError, BackupError, EventSchemaError)):
        return ApplicationCommandError(
            code=ApplicationErrorCode.BUSINESS_RULE,
            user_message=str(exc),
            operation=operation,
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, ApplicationRuntimeError):
        message = str(exc)
        code = ApplicationErrorCode.PROTECTED_MODE if "protected_mode" in message else ApplicationErrorCode.RECOVERY_REQUIRED
        return ApplicationCommandError(
            code=code,
            user_message=message,
            operation=operation,
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, ApplicationRecoveryError):
        return ApplicationCommandError(
            code=ApplicationErrorCode.RECOVERY_REQUIRED,
            user_message=str(exc),
            operation=operation,
            cause_type=type(exc).__name__,
        )
    if isinstance(exc, (BmsCoreError, OSError)):
        return ApplicationCommandError(
            code=ApplicationErrorCode.STORAGE,
            user_message="Storage is unavailable or failed integrity checks.",
            operation=operation,
            cause_type=type(exc).__name__,
        )
    return ApplicationCommandError(
        code=ApplicationErrorCode.UNEXPECTED,
        user_message="Unexpected application error. Please retry or inspect logs.",
        operation=operation,
        cause_type=type(exc).__name__,
    )
