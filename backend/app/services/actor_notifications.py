from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    ActorNotificationTask,
    Designation,
    Performance,
    ScheduleAssignment,
    Theater,
    WeeklyBatch,
)
from app.models.enums import ActorNotificationTaskStatus, ActorNotificationType

SHANGHAI = ZoneInfo("Asia/Shanghai")


def calculate_reveal_at(
    performance_date: date, days_before: int, reveal_time: time
) -> datetime:
    return datetime.combine(
        performance_date - timedelta(days=days_before), reveal_time, tzinfo=SHANGHAI
    ).replace(tzinfo=None)


def _fingerprint(
    theater_id: int,
    assignment: ScheduleAssignment,
    schedule_version: int,
    designation: Designation | None,
) -> str:
    value = ":".join(
        str(part)
        for part in (
            theater_id,
            assignment.performance_id,
            assignment.role_id,
            assignment.actor_id,
            schedule_version,
            designation.id if designation else "none",
            designation.designation_type.value if designation else "none",
        )
    )
    return hashlib.sha256(value.encode()).hexdigest()


def reconcile_notification_tasks(
    db: Session,
    theater_id: int,
    week_start: date,
    schedule_version: int,
    now: datetime,
) -> int:
    del now
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    week_end = week_start + timedelta(days=6)
    assignments = list(
        db.scalars(
            select(ScheduleAssignment)
            .join(WeeklyBatch, WeeklyBatch.id == ScheduleAssignment.weekly_batch_id)
            .join(Performance, Performance.id == ScheduleAssignment.performance_id)
            .where(
                WeeklyBatch.theater_id == theater_id,
                WeeklyBatch.week_start == week_start,
                Performance.performance_date.between(week_start, week_end),
            )
            .order_by(
                ScheduleAssignment.performance_id,
                ScheduleAssignment.role_id,
                ScheduleAssignment.actor_id,
            )
        )
    )
    existing = list(
        db.scalars(
            select(ActorNotificationTask)
            .join(Performance, Performance.id == ActorNotificationTask.performance_id)
            .where(
                ActorNotificationTask.theater_id == theater_id,
                ActorNotificationTask.status == ActorNotificationTaskStatus.PENDING,
                Performance.performance_date.between(week_start, week_end),
            )
        )
    )
    keep: set[str] = set()
    created = 0
    for assignment in assignments:
        performance = db.get(Performance, assignment.performance_id)
        designation = db.scalar(
            select(Designation).where(
                Designation.performance_id == assignment.performance_id,
                Designation.role_id == assignment.role_id,
                Designation.actor_id == assignment.actor_id,
                Designation.lifecycle_status == "fulfilled",
            ).order_by(Designation.id.desc())
        )
        fingerprint = _fingerprint(theater_id, assignment, schedule_version, designation)
        keep.add(fingerprint)
        if any(task.assignment_fingerprint == fingerprint for task in existing):
            continue
        idempotency_key = f"actor-disclosure:{fingerprint}"
        if db.scalar(
            select(ActorNotificationTask.id).where(
                ActorNotificationTask.idempotency_key == idempotency_key
            )
        ):
            continue
        db.add(
            ActorNotificationTask(
                theater_id=theater_id,
                performance_id=assignment.performance_id,
                role_id=assignment.role_id,
                actor_id=assignment.actor_id,
                schedule_version=schedule_version,
                notification_type=ActorNotificationType.NEW_ASSIGNMENT,
                reveal_at=calculate_reveal_at(
                    performance.performance_date,
                    theater.reveal_days_before,
                    theater.reveal_time,
                ),
                status=ActorNotificationTaskStatus.PENDING,
                assignment_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )
        )
        created += 1
    for task in existing:
        if task.assignment_fingerprint not in keep:
            task.status = ActorNotificationTaskStatus.SUPERSEDED
    db.flush()
    return created


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI).replace(tzinfo=None)
