from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from bms.app.auth import ApplicationRole, AuthorizationPolicy, validate_actor_payload
from bms.app.errors import map_application_error
from bms.app.runtime import ApplicationRuntime, start_application
from bms.domain.accounting import validate_post_journal_command_payload
from bms.domain.billing import validate_create_invoice_command_payload, validate_create_refund_command_payload
from bms.domain.inventory import ItemSchema, validate_stock_movement_command_payload


NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class RegisterItemPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item: ItemSchema
    actor_id: NonEmptyStr
    created_at: NonEmptyStr
    correlation_id: NonEmptyStr


class BackupCommandPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr
    backup_dir: StrictStr | None = None
    created_at: StrictStr | None = None

    @field_validator("backup_dir", "created_at")
    @classmethod
    def _optional_strings_cannot_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("optional string fields cannot be empty")
        return value


class ListUserRolesPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr


class UpdateUserRolesPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr
    target_actor_id: NonEmptyStr
    roles: tuple[ApplicationRole, ...]
    active: bool = True
    updated_at: NonEmptyStr
    correlation_id: NonEmptyStr

    @field_validator("roles")
    @classmethod
    def _roles_must_be_present(cls, value: tuple[ApplicationRole, ...]) -> tuple[ApplicationRole, ...]:
        if not value:
            raise ValueError("at least one role is required")
        if len(set(value)) != len(value):
            raise ValueError("actor roles must be unique")
        return value


class ClosePeriodCommandPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    period_id: NonEmptyStr
    actor_id: NonEmptyStr
    closed_at: StrictStr | None = None
    correlation_id: StrictStr | None = None

    @field_validator("closed_at", "correlation_id")
    @classmethod
    def _optional_strings_cannot_be_empty(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("optional string fields cannot be empty")
        return value


class RestoreCommandPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr
    backup_path: NonEmptyStr
    restore_root: NonEmptyStr


class _FacadeOutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ItemOutputSchema(_FacadeOutputSchema):
    item_id: str
    sku: str
    name: str
    active: bool
    business_unit: str


class StockMovementOutputSchema(_FacadeOutputSchema):
    movement_id: str
    item_id: str
    quantity_delta: int
    quantity_on_hand: int


class InvoiceOutputSchema(_FacadeOutputSchema):
    invoice_id: str
    journal_id: str
    movement_ids: tuple[str, ...]
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)
    currency: str


class RefundOutputSchema(_FacadeOutputSchema):
    refund_id: str
    original_invoice_id: str
    journal_id: str
    movement_ids: tuple[str, ...]
    subtotal_minor: int = Field(ge=0)
    tax_minor: int = Field(ge=0)
    total_minor: int = Field(ge=0)
    currency: str


class JournalOutputSchema(_FacadeOutputSchema):
    journal_id: str
    debit_total_minor: int = Field(ge=0)
    credit_total_minor: int = Field(ge=0)
    currency: str


class ClosePeriodOutputSchema(_FacadeOutputSchema):
    period_id: str
    status: str
    actor_id: str
    closed_at: str | None = None
    correlation_id: str | None = None


class UserRoleOutputSchema(_FacadeOutputSchema):
    actor_id: str
    display_name: str
    active: bool
    roles: tuple[str, ...]


class BackupOutputSchema(_FacadeOutputSchema):
    backup_path: str
    created_at: str
    verified_record_counts: dict[str, int]


class RestoreOutputSchema(_FacadeOutputSchema):
    restored_root: str
    verified_record_counts: dict[str, int]


class ApplicationCommandFacade:
    def __init__(self, runtime: ApplicationRuntime) -> None:
        self.runtime = runtime
        self.authorization = AuthorizationPolicy()


    def actor_sessions(self) -> list[dict[str, Any]]:
        try:
            return [
                {
                    "actor_id": session.actor_id,
                    "display_name": session.display_name,
                    "roles": [role.value for role in session.roles],
                }
                for session in self.runtime.identity.list_sessions()
            ]
        except Exception as exc:
            raise map_application_error("auth.actor_sessions", exc) from exc

    def user_roles(self, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        try:
            ListUserRolesPayloadSchema.model_validate(payload)
            self._authorize("auth.list_user_roles", payload)
            return [
                UserRoleOutputSchema(
                    actor_id=profile.actor_id,
                    display_name=profile.display_name,
                    active=profile.active,
                    roles=tuple(role.value for role in profile.roles),
                ).model_dump(mode="json")
                for profile in self.runtime.identity.list_user_roles()
            ]
        except Exception as exc:
            raise map_application_error("auth.list_user_roles", exc) from exc

    def update_user_roles(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = UpdateUserRolesPayloadSchema.model_validate(payload)
            self._authorize("auth.update_user_roles", payload)
            profile = self.runtime.identity.update_user_roles(
                request.target_actor_id,
                request.roles,
                active=request.active,
                updated_by=request.actor_id,
                updated_at=request.updated_at,
                correlation_id=request.correlation_id,
            )
            return UserRoleOutputSchema(
                actor_id=profile.actor_id,
                display_name=profile.display_name,
                active=profile.active,
                roles=tuple(role.value for role in profile.roles),
            ).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("auth.update_user_roles", exc) from exc

    def _authorize(self, operation: str, payload: Mapping[str, Any]) -> None:
        actor = validate_actor_payload(payload)
        session = self.runtime.identity.get_session(actor.actor_id)
        self.authorization.require(operation, session.roles)

    @classmethod
    def start(cls, data_root: Path) -> ApplicationCommandFacade:
        try:
            return cls(start_application(data_root))
        except Exception as exc:
            raise map_application_error("app.start", exc) from exc

    def register_item(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("inventory.register_item", payload)
            request = RegisterItemPayloadSchema.model_validate(payload)
            item = self.runtime.inventory.register_item(
                request.item.to_item(),
                actor_id=request.actor_id,
                created_at=request.created_at,
                correlation_id=request.correlation_id,
            )
            return ItemOutputSchema.model_validate(item).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("inventory.register_item", exc) from exc

    def commit_stock_movement(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("inventory.commit_stock_movement", payload)
            command = validate_stock_movement_command_payload(payload)
            result = self.runtime.inventory.commit_movement(command)
            return StockMovementOutputSchema.model_validate(result).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("inventory.commit_stock_movement", exc) from exc

    def post_journal(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("accounting.post_journal", payload)
            command = validate_post_journal_command_payload(payload)
            result = self.runtime.accounting.post_journal(command)
            return JournalOutputSchema.model_validate(result).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("accounting.post_journal", exc) from exc

    def close_period(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("accounting.close_period", payload)
            request = ClosePeriodCommandPayloadSchema.model_validate(payload)
            self.runtime.accounting.close_period(
                request.period_id,
                actor_id=request.actor_id,
                closed_at=request.closed_at,
                correlation_id=request.correlation_id,
            )
            return ClosePeriodOutputSchema(
                period_id=request.period_id,
                status="closed",
                actor_id=request.actor_id,
                closed_at=request.closed_at,
                correlation_id=request.correlation_id,
            ).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("accounting.close_period", exc) from exc

    def create_invoice(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("billing.create_invoice", payload)
            command = validate_create_invoice_command_payload(payload)
            result = self.runtime.create_invoice.execute(command)
            return InvoiceOutputSchema.model_validate(result).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("billing.create_invoice", exc) from exc

    def create_refund(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._authorize("billing.create_refund", payload)
            command = validate_create_refund_command_payload(payload)
            result = self.runtime.create_refund.execute(command)
            return RefundOutputSchema.model_validate(result).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("billing.create_refund", exc) from exc

    def invoice_report(self, period_id: str | None = None) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_invoice_report(period_id)
        except Exception as exc:
            raise map_application_error("reporting.invoice_report", exc) from exc

    def refund_report(self, period_id: str | None = None) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_refund_report(period_id)
        except Exception as exc:
            raise map_application_error("reporting.refund_report", exc) from exc

    def refund_availability_report(self, period_id: str | None = None) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_refund_availability_report(period_id)
        except Exception as exc:
            raise map_application_error("reporting.refund_availability_report", exc) from exc

    def business_unit_revenue_report(
        self,
        period_id: str | None = None,
        *,
        currency: str = "INR",
    ) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_business_unit_revenue_report(
                period_id,
                currency=currency,
            )
        except Exception as exc:
            raise map_application_error("reporting.business_unit_revenue_report", exc) from exc

    def stock_report(self, *, low_stock_threshold: int = 0) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_stock_report(low_stock_threshold=low_stock_threshold)
        except Exception as exc:
            raise map_application_error("reporting.stock_report", exc) from exc

    def ledger_report(self, period_id: str) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_ledger_report(period_id)
        except Exception as exc:
            raise map_application_error("reporting.ledger_report", exc) from exc

    def profit_and_loss_report(
        self,
        period_id: str,
        *,
        currency: str = "INR",
    ) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_profit_and_loss_report(
                period_id,
                currency=currency,
            )
        except Exception as exc:
            raise map_application_error("reporting.profit_and_loss_report", exc) from exc

    def tax_report(self, period_id: str, *, currency: str = "INR") -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_tax_report(period_id, currency=currency)
        except Exception as exc:
            raise map_application_error("reporting.tax_report", exc) from exc

    def trial_balance_report(self, period_id: str) -> dict[str, Any]:
        try:
            return self.runtime.reporting.export_trial_balance_report(period_id)
        except Exception as exc:
            raise map_application_error("reporting.trial_balance_report", exc) from exc

    def create_backup(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        try:
            request = BackupCommandPayloadSchema.model_validate(payload or {})
            self._authorize("backup.create", payload or {})
            backup = self.runtime.backup.create_backup(
                Path(request.backup_dir) if request.backup_dir is not None else None,
                created_at=request.created_at,
            )
            return BackupOutputSchema(
                backup_path=str(backup.backup_path),
                created_at=backup.created_at,
                verified_record_counts=backup.verified_record_counts,
            ).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("backup.create", exc) from exc

    def restore_backup(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = RestoreCommandPayloadSchema.model_validate(payload)
            self._authorize("backup.restore", payload)
            restore = self.runtime.backup.restore_backup(
                Path(request.backup_path),
                Path(request.restore_root),
            )
            return RestoreOutputSchema(
                restored_root=str(restore.restored_root),
                verified_record_counts=restore.verified_record_counts,
            ).model_dump(mode="json")
        except Exception as exc:
            raise map_application_error("backup.restore", exc) from exc


def start_command_facade(data_root: Path) -> ApplicationCommandFacade:
    return ApplicationCommandFacade.start(data_root)
