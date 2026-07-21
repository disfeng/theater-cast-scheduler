from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Actor,
    LeaveApplication,
    LeaveApplicationDay,
    Performance,
    PublishedCastAssignment,
    PerformanceCastPublication,
    ScheduleAssignment,
    Theater,
    WeeklyBatch,
)
from app.models.enums import BatchStatus, LeaveStatus


def submit_leave_application(
    db: Session,
    actor_id: int,
    theater_id: int,
    dates: list[date],
    note: str | None,
    *,
    today: date | None = None,
) -> LeaveApplication:
    today = today or date.today()
    unique_dates = sorted(set(dates))
    if not unique_dates:
        raise ValueError("请至少选择一个请假日期")
    if any(day < today for day in unique_dates):
        raise ValueError("不能申请过去日期")
    if db.get(Actor, actor_id) is None:
        raise LookupError("演员不存在")
    if db.get(Theater, theater_id) is None:
        raise LookupError("剧场不存在")
    duplicates = db.scalar(
        select(LeaveApplicationDay.id)
        .join(LeaveApplication, LeaveApplication.id == LeaveApplicationDay.application_id)
        .where(
            LeaveApplication.actor_id == actor_id,
            LeaveApplication.theater_id == theater_id,
            LeaveApplicationDay.leave_date.in_(unique_dates),
            LeaveApplicationDay.withdrawn_at.is_(None),
            LeaveApplicationDay.status.in_((LeaveStatus.PENDING, LeaveStatus.APPROVED)),
        )
        .limit(1)
    )
    if duplicates:
        raise ValueError("所选日期已有待审批或已批准的请假")

    application = LeaveApplication(actor_id=actor_id, theater_id=theater_id, note=note or None)
    db.add(application)
    db.flush()
    for leave_date in unique_dates:
        performance_ids = list(
            db.scalars(
                select(Performance.id)
                .join(PublishedCastAssignment, PublishedCastAssignment.performance_id == Performance.id)
                .join(PerformanceCastPublication, PerformanceCastPublication.id == PublishedCastAssignment.publication_id)
                .where(
                    PublishedCastAssignment.actor_id == actor_id,
                    Performance.theater_id == theater_id,
                    Performance.performance_date == leave_date,
                )
                .distinct()
            )
        )
        if not performance_ids:
            # Backward compatibility for schedules published before snapshot migration.
            performance_ids = list(
                db.scalars(
                    select(Performance.id)
                    .join(ScheduleAssignment, ScheduleAssignment.performance_id == Performance.id)
                    .join(WeeklyBatch, WeeklyBatch.id == ScheduleAssignment.weekly_batch_id)
                    .where(
                        ScheduleAssignment.actor_id == actor_id,
                        Performance.theater_id == theater_id,
                        Performance.performance_date == leave_date,
                        WeeklyBatch.status == BatchStatus.SCHEDULED,
                    )
                    .distinct()
                )
            )
        application.days.append(
            LeaveApplicationDay(
                leave_date=leave_date,
                status=LeaveStatus.PENDING,
                has_schedule_conflict=bool(performance_ids),
                conflict_performance_ids=performance_ids or None,
            )
        )
    db.flush()
    return application


def list_actor_leave_applications(db: Session, actor_id: int) -> list[LeaveApplication]:
    return list(
        db.scalars(
            select(LeaveApplication)
            .options(selectinload(LeaveApplication.days), selectinload(LeaveApplication.theater))
            .where(LeaveApplication.actor_id == actor_id)
            .order_by(LeaveApplication.created_at.desc(), LeaveApplication.id.desc())
        )
    )


def list_leave_applications(
    db: Session, theater_id: int | None = None, status: LeaveStatus | None = None
) -> list[LeaveApplication]:
    statement = select(LeaveApplication).options(
        selectinload(LeaveApplication.days),
        selectinload(LeaveApplication.actor),
        selectinload(LeaveApplication.theater),
    )
    if theater_id is not None:
        statement = statement.where(LeaveApplication.theater_id == theater_id)
    if status is not None:
        statement = statement.join(LeaveApplicationDay).where(
            LeaveApplicationDay.status == status,
            LeaveApplicationDay.withdrawn_at.is_(None),
        ).distinct()
    return list(db.scalars(statement.order_by(LeaveApplication.created_at.desc())))


def withdraw_leave_day(db: Session, actor_id: int, day_id: int) -> LeaveApplicationDay:
    day = db.scalar(
        select(LeaveApplicationDay)
        .join(LeaveApplication)
        .where(LeaveApplicationDay.id == day_id, LeaveApplication.actor_id == actor_id)
    )
    if day is None:
        raise LookupError("请假日期不存在")
    if day.status != LeaveStatus.PENDING or day.withdrawn_at is not None:
        raise ValueError("只有待审批日期可以撤回")
    day.withdrawn_at = datetime.now()
    db.flush()
    return day


def review_leave_day(
    db: Session,
    day_id: int,
    status: LeaveStatus,
    reason: str | None,
    operator_id: int,
) -> LeaveApplicationDay:
    if status not in (LeaveStatus.APPROVED, LeaveStatus.REJECTED):
        raise ValueError("审批状态无效")
    if status == LeaveStatus.REJECTED and not (reason or "").strip():
        raise ValueError("驳回请填写理由")
    day = db.get(LeaveApplicationDay, day_id)
    if day is None:
        raise LookupError("请假日期不存在")
    if day.withdrawn_at is not None or day.status != LeaveStatus.PENDING:
        raise ValueError("该日期已处理")
    day.status = status
    day.review_reason = (reason or "").strip() or None
    day.reviewed_by = operator_id
    day.reviewed_at = datetime.now()
    db.flush()
    return day


def review_pending_days(
    db: Session,
    application_id: int,
    status: LeaveStatus,
    reason: str | None,
    operator_id: int,
) -> LeaveApplication:
    application = db.get(LeaveApplication, application_id)
    if application is None:
        raise LookupError("请假申请不存在")
    for day in application.days:
        if day.status == LeaveStatus.PENDING and day.withdrawn_at is None:
            review_leave_day(db, day.id, status, reason, operator_id)
    return application
