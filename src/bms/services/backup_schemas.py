from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BackupManifestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = "bms.backup.v1"
    created_at: str
    verified_record_counts: dict[str, int] = Field(default_factory=dict)

    @field_validator("format")
    @classmethod
    def _format_must_be_supported(cls, value: str) -> str:
        if value != "bms.backup.v1":
            raise ValueError("unsupported backup format")
        return value

    @field_validator("created_at")
    @classmethod
    def _created_at_must_be_present(cls, value: str) -> str:
        if not value:
            raise ValueError("created_at is required")
        return value

    @field_validator("verified_record_counts")
    @classmethod
    def _record_counts_must_be_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        for name, count in value.items():
            if not name:
                raise ValueError("record count names must be non-empty")
            if count < 0:
                raise ValueError(f"record count for {name} cannot be negative")
        return value
