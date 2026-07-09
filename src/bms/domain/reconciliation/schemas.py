from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from bms.domain.reconciliation.models import ReconciliationReport


class _ReconciliationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ReconciliationCheckSchema(_ReconciliationSchema):
    name: str
    expected_minor: int
    actual_minor: int
    difference_minor: int
    passed: bool


class ReconciliationReportSchema(_ReconciliationSchema):
    period_id: str
    checks: tuple[ReconciliationCheckSchema, ...]
    passed: bool

    @classmethod
    def from_report(cls, report: ReconciliationReport) -> ReconciliationReportSchema:
        return cls(
            period_id=report.period_id,
            checks=report.checks,
            passed=report.passed,
        )


def dump_reconciliation_schema(schema: BaseModel) -> dict[str, Any]:
    return schema.model_dump(mode="json")
