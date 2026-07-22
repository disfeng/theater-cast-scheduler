from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    ActorNotification,
    ActorNotificationTask,
    Designation,
    Performance,
    PerformancePlayer,
    PerformanceCastPublication,
    PublishedCastAssignment,
    Role,
    Theater,
)
from app.models.enums import ActorNotificationTaskStatus, ActorNotificationType

SHANGHAI = ZoneInfo("Asia/Shanghai")


def calculate_reveal_at(performance_date: date, days_before: int, reveal_time: time) -> datetime:
    return datetime.combine(
        performance_date - timedelta(days=days_before), reveal_time, tzinfo=SHANGHAI
    ).replace(tzinfo=None)


def _fingerprint(
    theater_id: int,
    assignment: PublishedCastAssignment,
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
    performance_ids: set[int] | None = None,
) -> int:
    del now
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    week_end = week_start + timedelta(days=6)
    assignment_filters = [
        PerformanceCastPublication.theater_id == theater_id,
        Performance.performance_date.between(week_start, week_end),
    ]
    if performance_ids is not None:
        assignment_filters.append(PublishedCastAssignment.performance_id.in_(performance_ids))
    assignments = list(
        db.scalars(
            select(PublishedCastAssignment)
            .join(PerformanceCastPublication)
            .join(Performance, Performance.id == PublishedCastAssignment.performance_id)
            .where(*assignment_filters)
            .order_by(
                PublishedCastAssignment.performance_id,
                PublishedCastAssignment.role_id,
                PublishedCastAssignment.actor_id,
            )
        )
    )
    task_filters = [
        ActorNotificationTask.theater_id == theater_id,
        ActorNotificationTask.status == ActorNotificationTaskStatus.PENDING,
        Performance.performance_date.between(week_start, week_end),
    ]
    if performance_ids is not None:
        task_filters.append(ActorNotificationTask.performance_id.in_(performance_ids))
    existing = list(
        db.scalars(
            select(ActorNotificationTask)
            .join(Performance, Performance.id == ActorNotificationTask.performance_id)
            .where(*task_filters)
        )
    )
    keep: set[str] = set()
    created = 0
    for assignment in assignments:
        performance = db.get(Performance, assignment.performance_id)
        designation = db.scalar(
            select(Designation)
            .where(
                Designation.performance_id == assignment.performance_id,
                Designation.role_id == assignment.role_id,
                Designation.actor_id == assignment.actor_id,
                Designation.lifecycle_status.in_(["effective", "fulfilled"]),
            )
            .order_by(Designation.id.desc())
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


def backfill_revealed_notification_players(db: Session, performance_id: int) -> int:
    """Fill player snapshots when a board is activated after actor disclosure."""
    players_by_role = {
        player.paired_role_name: player.player_name_snapshot
        for player in db.scalars(
            select(PerformancePlayer).where(
                PerformancePlayer.performance_id == performance_id,
                PerformancePlayer.is_active.is_(True),
            )
        )
        if player.paired_role_name
    }
    if not players_by_role:
        return 0
    updated = 0
    notifications = db.scalars(
        select(ActorNotification).where(
            ActorNotification.performance_id == performance_id,
            ActorNotification.player_name_snapshot.is_(None),
        )
    )
    for notification in notifications:
        player_name = players_by_role.get(notification.role_name_snapshot)
        if player_name:
            notification.player_name_snapshot = player_name
            updated += 1
    db.flush()
    return updated


def reveal_due_tasks(db: Session, now: datetime | None = None, limit: int = 200) -> int:
    """Materialize due disclosure tasks into immutable actor-facing snapshots."""
    now = now or shanghai_now()
    tasks = list(
        db.scalars(
            select(ActorNotificationTask)
            .where(
                ActorNotificationTask.status == ActorNotificationTaskStatus.PENDING,
                ActorNotificationTask.reveal_at <= now,
            )
            .order_by(ActorNotificationTask.reveal_at, ActorNotificationTask.id)
            .limit(limit)
        )
    )
    revealed = 0
    for task in tasks:
        performance = db.get(Performance, task.performance_id)
        theater = db.get(Theater, task.theater_id)
        role = db.get(Role, task.role_id)
        if performance is None or theater is None or role is None:
            task.status = ActorNotificationTaskStatus.CANCELLED
            continue

        designation = db.scalar(
            select(Designation)
            .where(
                Designation.performance_id == task.performance_id,
                Designation.role_id == task.role_id,
                Designation.actor_id == task.actor_id,
                Designation.lifecycle_status.in_(["effective", "fulfilled"]),
            )
            .order_by(Designation.id.desc())
        )
        player = db.scalar(
            select(PerformancePlayer)
            .where(
                PerformancePlayer.performance_id == task.performance_id,
                PerformancePlayer.paired_role_name == role.name,
                PerformancePlayer.is_active.is_(True),
            )
            .order_by(PerformancePlayer.id)
        )
        key = f"actor-notification:{task.id}:{task.assignment_fingerprint}"
        if db.scalar(select(ActorNotification.id).where(ActorNotification.idempotency_key == key)):
            task.status = ActorNotificationTaskStatus.REVEALED
            task.revealed_at = task.revealed_at or now
            continue
        db.add(
            ActorNotification(
                task_id=task.id,
                theater_id=task.theater_id,
                performance_id=task.performance_id,
                role_id=task.role_id,
                actor_id=task.actor_id,
                notification_type=task.notification_type,
                schedule_version=task.schedule_version,
                theater_name_snapshot=theater.name,
                performance_date_snapshot=performance.performance_date,
                slot_name_snapshot=performance.slot_name_snapshot,
                start_time_snapshot=performance.start_time_snapshot,
                role_name_snapshot=role.name,
                player_name_snapshot=(
                    player.player_name_snapshot
                    if player is not None
                    else (designation.player_name if designation is not None else None)
                ),
                designation_type_snapshot=(
                    designation.designation_type.value if designation is not None else None
                ),
                idempotency_key=key,
            )
        )
        task.status = ActorNotificationTaskStatus.REVEALED
        task.revealed_at = now
        revealed += 1
    db.flush()
    return revealed
