from collections import defaultdict
from datetime import date

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    LeaveRequest,
    Performance,
    PerformancePlayer,
    Theater,
    Wish,
)
from app.models.enums import LeaveStatus, PerformanceStatus
from app.schemas.scheduling import PerformanceSlot
from app.schemas.designation_workspace import (
    DesignationConflictProjection,
    DesignationMonthWorkspaceRead,
    PerformanceSummary,
    WorkspaceDay,
    WorkspaceTotals,
)
from app.services.rules import consecutive_limit_state


class DesignationWorkspaceNotFound(ValueError):
    pass


def _performance_slot(performance: Performance) -> PerformanceSlot:
    return PerformanceSlot(
        id=performance.id,
        date=performance.performance_date,
        slot=performance.slot_name_snapshot,
        start_time=performance.start_time_snapshot,
        sort_order=performance.theater_slot.sort_order if performance.theater_slot else 0,
    )


def project_designation_conflicts(
    db: Session, designation: Designation
) -> list[DesignationConflictProjection]:
    performance_id = designation.performance_id or designation.target_performance_id
    performance = db.get(Performance, performance_id) if performance_id else None
    actor = db.get(Actor, designation.actor_id)
    if performance is None or actor is None:
        return [
            DesignationConflictProjection(
                code="INVALID_DESIGNATION_TARGET",
                severity="hard",
                message="指定缺少有效的演员或演出场次",
                designation_id=designation.id,
            )
        ]

    conflicts: list[DesignationConflictProjection] = []
    has_capability = db.scalar(
        select(ActorRoleCapability.id).where(
            ActorRoleCapability.actor_id == actor.id,
            ActorRoleCapability.role_id == designation.role_id,
        )
    )
    if has_capability is None:
        conflicts.append(
            DesignationConflictProjection(
                code="ROLE_NOT_ALLOWED",
                severity="hard",
                message="演员不具备该剧场角色的出演能力",
                designation_id=designation.id,
            )
        )

    approved_leave = db.scalar(
        select(LeaveRequest.id).where(
            LeaveRequest.actor_id == actor.id,
            LeaveRequest.leave_date == performance.performance_date,
            LeaveRequest.status == LeaveStatus.APPROVED,
        )
    )
    if approved_leave is not None:
        conflicts.append(
            DesignationConflictProjection(
                code="ACTOR_ON_LEAVE",
                severity="hard",
                message="演员当天已批准请假",
                designation_id=designation.id,
            )
        )

    timeline_models = list(
        db.scalars(
            select(Performance)
            .where(Performance.status != PerformanceStatus.CANCELLED)
            .options(selectinload(Performance.theater_slot))
            .order_by(
                Performance.performance_date,
                Performance.start_time_snapshot,
                Performance.id,
            )
        )
    )
    slots_by_id = {row.id: _performance_slot(row) for row in timeline_models}
    existing_designations = list(
        db.scalars(
            select(Designation).where(
                Designation.actor_id == actor.id,
                Designation.lifecycle_status == "predesignated",
                Designation.id != designation.id,
            )
        )
    )
    existing_slots = [
        slots_by_id[item.performance_id or item.target_performance_id]
        for item in existing_designations
        if (item.performance_id or item.target_performance_id) in slots_by_id
    ]
    target_slot = slots_by_id.get(performance.id, _performance_slot(performance))
    state = consecutive_limit_state(
        actor.id,
        target_slot,
        {actor.id: existing_slots},
        actor.max_consecutive_performances,
        list(slots_by_id.values()),
    )
    if state == "reached":
        conflicts.append(
            DesignationConflictProjection(
                code="MAX_CONSECUTIVE_REACHED",
                severity="warning",
                message="已达到演员个人最大连场数",
                designation_id=designation.id,
            )
        )
    elif state == "exceeded":
        conflicts.append(
            DesignationConflictProjection(
                code="MAX_CONSECUTIVE_EXCEEDED",
                severity="hard",
                message="超过演员个人最大连场数",
                designation_id=designation.id,
            )
        )

    if any(
        (item.performance_id or item.target_performance_id) == performance.id
        for item in existing_designations
    ):
        conflicts.append(
            DesignationConflictProjection(
                code="ACTOR_ALREADY_IN_PERFORMANCE",
                severity="hard",
                message="演员同场已存在其他有效指定",
                designation_id=designation.id,
            )
        )
    return conflicts


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _add_totals(left: WorkspaceTotals, right: WorkspaceTotals) -> WorkspaceTotals:
    return WorkspaceTotals(
        players=left.players + right.players,
        designations=left.designations + right.designations,
        wishes=left.wishes + right.wishes,
        pending=left.pending + right.pending,
        conflicts=left.conflicts + right.conflicts,
    )


def get_month_workspace(
    db: Session, theater_id: int, year: int, month: int
) -> DesignationMonthWorkspaceRead:
    if db.get(Theater, theater_id) is None:
        raise DesignationWorkspaceNotFound("剧场不存在")

    month_start, next_month_start = _month_bounds(year, month)
    performances = db.scalars(
        select(Performance)
        .where(
            Performance.theater_id == theater_id,
            Performance.performance_date >= month_start,
            Performance.performance_date < next_month_start,
        )
        .order_by(
            Performance.performance_date,
            Performance.start_time_snapshot,
            Performance.id,
        )
    ).all()
    performance_ids = [performance.id for performance in performances]
    totals_by_performance: dict[int, WorkspaceTotals] = {
        performance_id: WorkspaceTotals() for performance_id in performance_ids
    }

    if performance_ids:
        player_counts = db.execute(
            select(PerformancePlayer.performance_id, func.count(PerformancePlayer.id))
            .where(
                PerformancePlayer.performance_id.in_(performance_ids),
                PerformancePlayer.is_active.is_(True),
            )
            .group_by(PerformancePlayer.performance_id)
        ).all()
        for performance_id, count in player_counts:
            totals_by_performance[performance_id].players = count

        designation_performance_id = func.coalesce(
            Designation.performance_id, Designation.target_performance_id
        )
        designation_counts = db.execute(
            select(
                designation_performance_id.label("performance_id"),
                func.count(Designation.id),
                func.sum(
                    case(
                        (
                            Designation.lifecycle_status.in_(
                                ["predesignated", "cancelled", "replaced", "fulfilled"]
                            ),
                            0,
                        ),
                        else_=1,
                    )
                ),
                func.sum(case((Designation.failure_reason.is_not(None), 1), else_=0)),
            )
            .where(designation_performance_id.in_(performance_ids))
            .group_by(designation_performance_id)
        ).all()
        for performance_id, count, pending, conflicts in designation_counts:
            totals = totals_by_performance[performance_id]
            totals.designations = count
            totals.pending += pending or 0
            totals.conflicts += conflicts or 0

        wish_counts = db.execute(
            select(
                Wish.performance_id,
                func.count(Wish.id),
                func.sum(case((Wish.status == "active", 1), else_=0)),
                func.sum(case((Wish.failure_reason.is_not(None), 1), else_=0)),
            )
            .where(Wish.performance_id.in_(performance_ids))
            .group_by(Wish.performance_id)
        ).all()
        for performance_id, count, pending, conflicts in wish_counts:
            totals = totals_by_performance[performance_id]
            totals.wishes = count
            totals.pending += pending or 0
            totals.conflicts += conflicts or 0

    days: dict[date, list[PerformanceSummary]] = defaultdict(list)
    month_totals = WorkspaceTotals()
    for performance in performances:
        totals = totals_by_performance[performance.id]
        month_totals = _add_totals(month_totals, totals)
        days[performance.performance_date].append(
            PerformanceSummary(
                id=performance.id,
                performance_date=performance.performance_date,
                slot_name=performance.slot_name_snapshot,
                start_time=performance.start_time_snapshot,
                status=performance.status.value,
                totals=totals,
            )
        )

    return DesignationMonthWorkspaceRead(
        theater_id=theater_id,
        year=year,
        month=month,
        totals=month_totals,
        days=[WorkspaceDay(date=day, performances=items) for day, items in days.items()],
    )
