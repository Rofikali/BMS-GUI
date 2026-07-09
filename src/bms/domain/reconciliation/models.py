from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationCheck:
    name: str
    expected_minor: int
    actual_minor: int
    difference_minor: int
    passed: bool


@dataclass(frozen=True)
class ReconciliationReport:
    period_id: str
    checks: tuple[ReconciliationCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)
