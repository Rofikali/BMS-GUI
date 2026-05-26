from __future__ import annotations

from typing import Annotated, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from bms.domain.accounting.models import JournalLine, PostJournalCommand


NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]


class JournalLineSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_code: NonEmptyStr
    debit_minor: StrictInt = 0
    credit_minor: StrictInt = 0
    currency: NonEmptyStr = "INR"
    memo: StrictStr = ""

    def to_line(self) -> JournalLine:
        return JournalLine(
            account_code=self.account_code,
            debit_minor=self.debit_minor,
            credit_minor=self.credit_minor,
            currency=self.currency,
            memo=self.memo,
        )


class PostJournalCommandSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    journal_id: NonEmptyStr
    period_id: NonEmptyStr
    timestamp: NonEmptyStr
    actor_id: NonEmptyStr
    source_module: NonEmptyStr
    source_document_id: NonEmptyStr
    correlation_id: NonEmptyStr
    description: NonEmptyStr
    lines: tuple[JournalLineSchema, ...] = Field(min_length=1)

    def to_command(self) -> PostJournalCommand:
        return PostJournalCommand(
            journal_id=self.journal_id,
            period_id=self.period_id,
            timestamp=self.timestamp,
            actor_id=self.actor_id,
            source_module=self.source_module,
            source_document_id=self.source_document_id,
            correlation_id=self.correlation_id,
            description=self.description,
            lines=tuple(line.to_line() for line in self.lines),
        )


def validate_post_journal_command_payload(payload: Mapping[str, Any]) -> PostJournalCommand:
    return PostJournalCommandSchema.model_validate(payload).to_command()
