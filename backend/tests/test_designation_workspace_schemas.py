from datetime import date, time

import pytest
from pydantic import ValidationError

from app.schemas.designation_workspace import (
    DesignationConflictProjection,
    DesignationMonthWorkspaceRead,
    MonthWorkspaceQuery,
    PerformanceSummary,
    WorkspaceDay,
    WorkspaceTotals,
)


def test_month_workspace_schema_contract():
    performance = PerformanceSummary(
        id=62,
        performance_date=date(2026, 8, 5),
        slot_name="下午场",
        start_time=time(16, 0),
        status="DRAFT",
        totals=WorkspaceTotals(players=10, designations=3, wishes=1, pending=2, conflicts=1),
    )
    body = DesignationMonthWorkspaceRead(
        theater_id=2,
        year=2026,
        month=8,
        totals=performance.totals,
        days=[WorkspaceDay(date=date(2026, 8, 5), performances=[performance])],
    ).model_dump(mode="json")

    assert body.keys() >= {"theater_id", "year", "month", "totals", "days"}
    assert body["totals"].keys() >= {
        "players",
        "designations",
        "wishes",
        "pending",
        "conflicts",
    }
    assert body["days"][0]["performances"][0]["slot_name"] == "下午场"


@pytest.mark.parametrize("month", [0, 13])
def test_month_workspace_query_rejects_invalid_month(month: int):
    with pytest.raises(ValidationError):
        MonthWorkspaceQuery(theater_id=2, year=2026, month=month)


def test_conflict_projection_rejects_unknown_severity():
    with pytest.raises(ValidationError):
        DesignationConflictProjection(
            code="UNKNOWN",
            severity="notice",
            message="unsupported",
            designation_id=1,
        )
