from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Iterable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from bms.storage.file_store.core_store import CoreFileStore


NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class ApplicationRole(StrEnum):
    ADMIN = "admin"
    CASHIER = "cashier"
    ACCOUNTANT = "accountant"


class AuthorizationError(Exception):
    pass


@dataclass(frozen=True)
class ActorSession:
    actor_id: str
    display_name: str
    roles: tuple[ApplicationRole, ...]


@dataclass(frozen=True)
class UserRoleProfile:
    actor_id: str
    display_name: str
    active: bool
    roles: tuple[ApplicationRole, ...]


class ActorPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    actor_id: NonEmptyStr


class UserRecordSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr
    display_name: NonEmptyStr
    active: bool = True


class UsersFileSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    users: tuple[UserRecordSchema, ...]

    @field_validator("schema_version")
    @classmethod
    def _supported_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported users schema version")
        return value

    @field_validator("users")
    @classmethod
    def _users_must_be_unique(cls, value: tuple[UserRecordSchema, ...]) -> tuple[UserRecordSchema, ...]:
        actor_ids = [user.actor_id for user in value]
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("user actor ids must be unique")
        return value


class RoleAssignmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_id: NonEmptyStr
    roles: tuple[ApplicationRole, ...]

    @field_validator("roles")
    @classmethod
    def _roles_must_be_present(cls, value: tuple[ApplicationRole, ...]) -> tuple[ApplicationRole, ...]:
        if not value:
            raise ValueError("at least one actor role is required")
        if len(set(value)) != len(value):
            raise ValueError("actor roles must be unique")
        return value


class RolesFileSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    assignments: tuple[RoleAssignmentSchema, ...]

    @field_validator("schema_version")
    @classmethod
    def _supported_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported roles schema version")
        return value

    @field_validator("assignments")
    @classmethod
    def _assignments_must_be_unique(cls, value: tuple[RoleAssignmentSchema, ...]) -> tuple[RoleAssignmentSchema, ...]:
        actor_ids = [assignment.actor_id for assignment in value]
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("role assignment actor ids must be unique")
        return value


class IdentityService:
    def __init__(self, store: CoreFileStore) -> None:
        self.store = store

    def get_session(self, actor_id: str) -> ActorSession:
        sessions = {session.actor_id: session for session in self.list_sessions()}
        session = sessions.get(actor_id)
        if session is None:
            raise AuthorizationError(f"unknown or inactive actor: {actor_id}")
        return session

    def list_sessions(self) -> tuple[ActorSession, ...]:
        users = UsersFileSchema.model_validate_json(self.store.users.read_text(encoding="utf-8"))
        roles = RolesFileSchema.model_validate_json(self.store.roles.read_text(encoding="utf-8"))
        role_by_actor_id = {assignment.actor_id: assignment.roles for assignment in roles.assignments}
        sessions: list[ActorSession] = []
        for user in users.users:
            if not user.active:
                continue
            actor_roles = role_by_actor_id.get(user.actor_id)
            if actor_roles:
                sessions.append(ActorSession(user.actor_id, user.display_name, actor_roles))
        return tuple(sessions)

    def list_user_roles(self) -> tuple[UserRoleProfile, ...]:
        users = UsersFileSchema.model_validate_json(self.store.users.read_text(encoding="utf-8"))
        roles = RolesFileSchema.model_validate_json(self.store.roles.read_text(encoding="utf-8"))
        role_by_actor_id = {assignment.actor_id: assignment.roles for assignment in roles.assignments}
        return tuple(
            UserRoleProfile(
                actor_id=user.actor_id,
                display_name=user.display_name,
                active=user.active,
                roles=role_by_actor_id.get(user.actor_id, ()),
            )
            for user in users.users
        )

    def update_user_roles(
        self,
        actor_id: str,
        roles: Iterable[ApplicationRole],
        *,
        active: bool,
        updated_by: str,
        updated_at: str,
        correlation_id: str,
    ) -> UserRoleProfile:
        users = UsersFileSchema.model_validate_json(self.store.users.read_text(encoding="utf-8"))
        roles_file = RolesFileSchema.model_validate_json(self.store.roles.read_text(encoding="utf-8"))
        requested_roles = tuple(dict.fromkeys(roles))
        if not requested_roles:
            raise AuthorizationError("at least one role is required")

        user_by_actor_id = {user.actor_id: user for user in users.users}
        target_user = user_by_actor_id.get(actor_id)
        if target_user is None:
            raise AuthorizationError(f"unknown user: {actor_id}")

        updated_users = tuple(
            UserRecordSchema(
                actor_id=user.actor_id,
                display_name=user.display_name,
                active=active if user.actor_id == actor_id else user.active,
            )
            for user in users.users
        )
        updated_assignments = _replace_role_assignment(
            roles_file.assignments,
            RoleAssignmentSchema(actor_id=actor_id, roles=requested_roles),
        )
        _ensure_active_admin_remains(updated_users, updated_assignments)

        _write_json_model(self.store.users, UsersFileSchema(users=updated_users))
        _write_json_model(self.store.roles, RolesFileSchema(assignments=updated_assignments))
        self.store.append_audit_record(
            "auth.roles_updated",
            updated_by,
            "user",
            actor_id,
            correlation_id,
            occurred_at=updated_at,
            details={
                "active": active,
                "roles": [role.value for role in requested_roles],
            },
            idempotency_key=f"auth_roles_updated_{actor_id}_{uuid4().hex}",
        )
        return UserRoleProfile(
            actor_id=actor_id,
            display_name=target_user.display_name,
            active=active,
            roles=requested_roles,
        )


class AuthorizationPolicy:
    _required_roles: dict[str, frozenset[ApplicationRole]] = {
        "inventory.register_item": frozenset({ApplicationRole.ADMIN}),
        "inventory.commit_stock_movement": frozenset({ApplicationRole.ADMIN}),
        "accounting.post_journal": frozenset({ApplicationRole.ACCOUNTANT}),
        "accounting.close_period": frozenset({ApplicationRole.ACCOUNTANT}),
        "billing.create_invoice": frozenset({ApplicationRole.CASHIER}),
        "billing.create_refund": frozenset({ApplicationRole.CASHIER}),
        "backup.create": frozenset({ApplicationRole.ADMIN}),
        "backup.restore": frozenset({ApplicationRole.ADMIN}),
        "auth.list_user_roles": frozenset({ApplicationRole.ADMIN}),
        "auth.update_user_roles": frozenset({ApplicationRole.ADMIN}),
        "recovery.reconcile": frozenset({ApplicationRole.ADMIN}),
    }

    def require(self, operation: str, roles: Iterable[ApplicationRole]) -> None:
        role_set = frozenset(roles)
        if ApplicationRole.ADMIN in role_set:
            return
        allowed_roles = self._required_roles.get(operation, frozenset())
        if allowed_roles and role_set.isdisjoint(allowed_roles):
            allowed = ", ".join(sorted(role.value for role in allowed_roles))
            raise AuthorizationError(f"{operation} requires one of these roles: {allowed}")


def default_identity_documents() -> tuple[str, str]:
    users = UsersFileSchema(
        users=(
            UserRecordSchema(actor_id="usr_admin", display_name="Admin"),
            UserRecordSchema(actor_id="usr_inventory", display_name="Inventory Admin"),
            UserRecordSchema(actor_id="usr_cashier", display_name="Cashier"),
            UserRecordSchema(actor_id="usr_accountant", display_name="Accountant"),
        )
    )
    roles = RolesFileSchema(
        assignments=(
            RoleAssignmentSchema(actor_id="usr_admin", roles=(ApplicationRole.ADMIN,)),
            RoleAssignmentSchema(actor_id="usr_inventory", roles=(ApplicationRole.ADMIN,)),
            RoleAssignmentSchema(actor_id="usr_cashier", roles=(ApplicationRole.CASHIER,)),
            RoleAssignmentSchema(actor_id="usr_accountant", roles=(ApplicationRole.ACCOUNTANT,)),
        )
    )
    return (
        json.dumps(users.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        json.dumps(roles.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )


def validate_actor_payload(payload: object) -> ActorPayloadSchema:
    return ActorPayloadSchema.model_validate(payload)


def _replace_role_assignment(
    assignments: tuple[RoleAssignmentSchema, ...],
    replacement: RoleAssignmentSchema,
) -> tuple[RoleAssignmentSchema, ...]:
    found = False
    updated: list[RoleAssignmentSchema] = []
    for assignment in assignments:
        if assignment.actor_id == replacement.actor_id:
            found = True
            updated.append(replacement)
        else:
            updated.append(assignment)
    if not found:
        updated.append(replacement)
    return tuple(updated)


def _ensure_active_admin_remains(
    users: tuple[UserRecordSchema, ...],
    assignments: tuple[RoleAssignmentSchema, ...],
) -> None:
    active_actor_ids = {user.actor_id for user in users if user.active}
    active_admins = [
        assignment.actor_id
        for assignment in assignments
        if assignment.actor_id in active_actor_ids
        and ApplicationRole.ADMIN in assignment.roles
    ]
    if not active_admins:
        raise AuthorizationError("at least one active admin must remain")


def _write_json_model(path: Path, model: BaseModel) -> None:
    temp_path = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temp_path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
