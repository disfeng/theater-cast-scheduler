from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.api.routes.admin_performance_boards import designation_review_read, wish_review_read
from app.models.entities import Designation, Performance, PerformancePlayer, Theater, Wish
from app.schemas.designation_workspace import (
    DesignationMonthWorkspaceRead,
    MonthWorkspaceQuery,
    PerformancePlayerWorkspaceRead,
    PerformanceWorkspaceHeader,
    PerformanceWorkspaceRead,
    WorkspaceTotals,
)
from app.services.designation_workspace import (
    DesignationWorkspaceNotFound,
    get_month_workspace,
    project_designation_conflicts,
)
from app.services.performance_boards import ensure_active_board_designations

router = APIRouter(prefix="/admin/designation-workspace", tags=["admin_designation_workspace"])


@router.get("/month", response_model=DesignationMonthWorkspaceRead)
def month_workspace(
    query: MonthWorkspaceQuery = Depends(),
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DesignationMonthWorkspaceRead:
    try:
        return get_month_workspace(db, query.theater_id, query.year, query.month)
    except DesignationWorkspaceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/performances/{performance_id}", response_model=PerformanceWorkspaceRead)
def performance_workspace(
    performance_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PerformanceWorkspaceRead:
    performance = db.get(Performance, performance_id)
    if performance is None:
        raise HTTPException(status_code=404, detail="演出场次不存在")
    ensure_active_board_designations(db, performance_id)
    db.commit()
    theater = db.get(Theater, performance.theater_id)
    player_rows = list(
        db.scalars(
            select(PerformancePlayer)
            .where(
                PerformancePlayer.performance_id == performance_id,
                PerformancePlayer.is_active.is_(True),
            )
            .order_by(PerformancePlayer.id)
        )
    )
    designation_rows = list(
        db.scalars(
            select(Designation)
            .where(
                func.coalesce(Designation.performance_id, Designation.target_performance_id)
                == performance_id
            )
            .order_by(Designation.submitted_at, Designation.id)
        )
    )
    wish_rows = list(
        db.scalars(
            select(Wish).where(Wish.performance_id == performance_id).order_by(Wish.id)
        )
    )
    conflicts = [
        conflict
        for designation in designation_rows
        for conflict in project_designation_conflicts(db, designation)
    ]
    totals = WorkspaceTotals(
        players=len(player_rows),
        designations=len(designation_rows),
        wishes=len(wish_rows),
        pending=sum(
            row.lifecycle_status not in {"predesignated", "cancelled", "replaced", "fulfilled"}
            for row in designation_rows
        )
        + sum(row.status == "active" for row in wish_rows),
        conflicts=len(conflicts),
    )
    return PerformanceWorkspaceRead(
        performance=PerformanceWorkspaceHeader(
            id=performance.id,
            theater_id=performance.theater_id,
            theater_name=theater.name if theater else str(performance.theater_id),
            performance_date=performance.performance_date,
            slot_name=performance.slot_name_snapshot,
            start_time=performance.start_time_snapshot,
            status=performance.status.value,
            totals=totals,
        ),
        players=[
            PerformancePlayerWorkspaceRead(
                id=row.id,
                player_id=row.player_profile_id,
                player_name=row.player_name_snapshot,
                theater_visit_count=row.theater_visit_ordinal,
                role_visit_count=row.character_visit_ordinal,
                role_name=row.paired_role_name,
                status="active",
            )
            for row in player_rows
        ],
        designations=[designation_review_read(db, row) for row in designation_rows],
        wishes=[wish_review_read(db, row) for row in wish_rows],
        conflicts=conflicts,
    )
