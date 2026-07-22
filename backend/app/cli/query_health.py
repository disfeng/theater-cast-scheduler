from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.query_diagnostics import PlanExpectation, PlanFinding, evaluate_explain_rows


@dataclass(frozen=True)
class QueryCheck:
    name: str
    explain_sql: str
    parameters: Mapping[str, object]
    expectation: PlanExpectation

    def with_expected_indexes(self, *indexes: str) -> "QueryCheck":
        return replace(
            self,
            expectation=replace(self.expectation, expected_indexes=frozenset(indexes)),
        )


@dataclass(frozen=True)
class DiagnosticReport:
    findings: tuple[PlanFinding, ...]

    @property
    def healthy(self) -> bool:
        return all(finding.healthy for finding in self.findings)

    @property
    def exit_code(self) -> int:
        return 0 if self.healthy else 1

    def to_json(self) -> str:
        return json.dumps(
            {"healthy": self.healthy, "findings": [asdict(row) for row in self.findings]},
            ensure_ascii=False,
            default=list,
        )


_today = date.today()
QUERY_CHECKS: dict[str, QueryCheck] = {
    "performance_month": QueryCheck(
        name="performance_month",
        explain_sql=(
            "EXPLAIN SELECT id FROM performances "
            "WHERE theater_id=:theater_id AND performance_date BETWEEN :start_date AND :end_date "
            "AND status=:status ORDER BY performance_date, id"
        ),
        parameters={
            "theater_id": 1,
            "start_date": _today.replace(day=1),
            "end_date": _today + timedelta(days=31),
            "status": "scheduled",
        },
        expectation=PlanExpectation(
            expected_indexes=frozenset({"ix_performances_theater_date_status"}),
            reject_filesort=False,
        ),
    ),
    "entitlement_inventory": QueryCheck(
        name="entitlement_inventory",
        explain_sql=(
            "EXPLAIN SELECT id FROM entitlement_items "
            "WHERE theater_id=:theater_id AND owner_id=:owner_id AND status=:status "
            "ORDER BY id"
        ),
        parameters={"theater_id": 1, "owner_id": 1, "status": "available"},
        expectation=PlanExpectation(
            expected_indexes=frozenset({"ix_entitlement_items_theater_owner_status"})
        ),
    ),
    "entitlement_ledger": QueryCheck(
        name="entitlement_ledger",
        explain_sql=(
            "EXPLAIN SELECT id FROM entitlement_ledger_entries "
            "WHERE theater_id=:theater_id AND id < :cursor ORDER BY id DESC LIMIT 50"
        ),
        parameters={"theater_id": 1, "cursor": 2_147_483_647},
        expectation=PlanExpectation(
            expected_indexes=frozenset({"ix_entitlement_ledger_theater_id"})
        ),
    ),
    "leave_review": QueryCheck(
        name="leave_review",
        explain_sql=(
            "EXPLAIN SELECT id FROM leave_application_days "
            "WHERE status=:status AND leave_date BETWEEN :start_date AND :end_date "
            "ORDER BY leave_date, id"
        ),
        parameters={
            "status": "pending",
            "start_date": _today,
            "end_date": _today + timedelta(days=90),
        },
        expectation=PlanExpectation(
            expected_indexes=frozenset({"ix_leave_days_status_date"}),
            reject_filesort=False,
        ),
    ),
    "actor_assignments": QueryCheck(
        name="actor_assignments",
        explain_sql=(
            "EXPLAIN SELECT performance_id FROM schedule_assignments "
            "WHERE actor_id=:actor_id AND performance_id >= :performance_id ORDER BY performance_id"
        ),
        parameters={"actor_id": 1, "performance_id": 1},
        expectation=PlanExpectation(
            expected_indexes=frozenset({"ix_schedule_assignments_actor_performance"})
        ),
    ),
}


def run_diagnostics(
    session: Session, checks: Mapping[str, QueryCheck] = QUERY_CHECKS
) -> DiagnosticReport:
    findings: list[PlanFinding] = []
    for check in checks.values():
        rows = session.execute(text(check.explain_sql), dict(check.parameters)).mappings().all()
        findings.append(evaluate_explain_rows(check.name, rows, check.expectation))
    return DiagnosticReport(findings=tuple(findings))


def main() -> int:
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        report = run_diagnostics(session)
    print(report.to_json())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
