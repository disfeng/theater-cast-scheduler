from __future__ import annotations

import hashlib
import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.time import utc_now

from app.models.entities import (
    DailyPublishOperation,
    Performance,
    PerformanceCastPublication,
    PublishedCastAssignment,
    Role,
    ScheduleAssignment,
    User,
    WeeklyBatch,
)
from app.schemas.weekly_scheduling import DailySchedulePublishRequest


class RepublishConfirmationRequired(RuntimeError):
    def __init__(self, *, added: int, changed: int, removed: int) -> None:
        self.added = added
        self.changed = changed
        self.removed = removed


def assignment_hash(rows: list[object]) -> str:
    payload = sorted(
        (
            int(getattr(row, "performance_id")),
            int(getattr(row, "role_id")),
            int(getattr(row, "actor_id")),
            str(getattr(row, "source", "manual")),
        )
        for row in rows
    )
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def publish_schedule_day(
    db: Session, payload: DailySchedulePublishRequest, operator_email: str
) -> dict[str, object]:
    batch = db.scalar(
        select(WeeklyBatch)
        .where(
            WeeklyBatch.theater_id == payload.theater_id,
            WeeklyBatch.week_start == payload.week_start,
        )
        .options(selectinload(WeeklyBatch.assignments))
    )
    if batch is None:
        raise LookupError("weekly_batch_not_found")
    if batch.version != payload.expected_version:
        from app.services.weekly_scheduling import ScheduleVersionConflict

        raise ScheduleVersionConflict(batch.version)
    if (
        not payload.week_start
        <= payload.performance_date
        <= payload.week_start.fromordinal(payload.week_start.toordinal() + 6)
    ):
        raise ValueError("performance_date_outside_week")

    operator = db.scalar(select(User).where(User.email == operator_email))
    if operator is None:
        raise LookupError("operator_not_found")

    operation = db.scalar(
        select(DailyPublishOperation).where(
            DailyPublishOperation.idempotency_key == payload.idempotency_key
        )
    )
    request_hash = hashlib.sha256(
        json.dumps(
            {
                "theater_id": payload.theater_id,
                "performance_date": payload.performance_date.isoformat(),
                "batch_version": batch.version,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if operation is not None:
        if operation.request_hash != request_hash:
            raise ValueError("idempotency_key_reused")
        from app.services.weekly_scheduling import get_workspace

        snapshot = operation.response_snapshot or {}
        return {
            **snapshot,
            "workspace": get_workspace(db, payload.theater_id, payload.week_start),
        }

    performances = list(
        db.scalars(
            select(Performance).where(
                Performance.theater_id == payload.theater_id,
                Performance.performance_date == payload.performance_date,
            )
        )
    )
    if not performances:
        raise LookupError("performances_not_found")
    performance_ids = {row.id for row in performances}
    rows = [row for row in batch.assignments if row.performance_id in performance_ids]
    role_ids = set(
        db.scalars(
            select(Role.id).where(Role.theater_id == payload.theater_id, Role.is_active.is_(True))
        )
    )
    by_performance = {
        performance.id: [row for row in rows if row.performance_id == performance.id]
        for performance in performances
    }
    incomplete = [
        performance_id
        for performance_id, assignments in by_performance.items()
        if assignments and {row.role_id for row in assignments} != role_ids
    ]
    if incomplete:
        from app.services.weekly_scheduling import IncompletePerformancesError

        raise IncompletePerformancesError([{"performance_id": item} for item in incomplete])

    existing = {
        row.performance_id: row
        for row in db.scalars(
            select(PerformanceCastPublication)
            .where(PerformanceCastPublication.performance_id.in_(performance_ids))
            .options(selectinload(PerformanceCastPublication.assignments))
        )
    }
    differences = {"added": 0, "changed": 0, "removed": 0}
    for performance_id, draft_rows in by_performance.items():
        publication = existing.get(performance_id)
        if publication is None:
            differences["added"] += len(draft_rows)
            continue
        old = {row.role_id: row.actor_id for row in publication.assignments}
        new = {row.role_id: row.actor_id for row in draft_rows}
        differences["added"] += len(new.keys() - old.keys())
        differences["removed"] += len(old.keys() - new.keys())
        differences["changed"] += sum(old[key] != new[key] for key in old.keys() & new.keys())
    has_changes = any(differences.values())
    if existing and has_changes and not payload.confirm_republish:
        raise RepublishConfirmationRequired(**differences)

    now = utc_now()
    max_version = 1
    for performance_id, draft_rows in by_performance.items():
        publication = existing.get(performance_id)
        digest = assignment_hash(draft_rows)
        if publication is not None and publication.assignment_hash == digest:
            max_version = max(max_version, publication.version)
            continue
        if publication is None:
            publication = PerformanceCastPublication(
                performance_id=performance_id,
                theater_id=payload.theater_id,
                weekly_batch_id=batch.id,
                version=1,
                source_batch_version=batch.version,
                assignment_hash=digest,
                published_at=now,
                operator_user_id=operator.id,
            )
            db.add(publication)
            db.flush()
        else:
            publication.version += 1
            publication.weekly_batch_id = batch.id
            publication.source_batch_version = batch.version
            publication.assignment_hash = digest
            publication.published_at = now
            publication.operator_user_id = operator.id
            db.execute(
                delete(PublishedCastAssignment).where(
                    PublishedCastAssignment.publication_id == publication.id
                )
            )
        for row in draft_rows:
            db.add(
                PublishedCastAssignment(
                    publication_id=publication.id,
                    performance_id=row.performance_id,
                    role_id=row.role_id,
                    actor_id=row.actor_id,
                    source=row.source,
                )
            )
        max_version = max(max_version, publication.version)

    from app.services.weekly_scheduling import get_workspace

    db.flush()
    from app.services.actor_notifications import reconcile_notification_tasks, shanghai_now

    reconcile_notification_tasks(
        db,
        payload.theater_id,
        payload.week_start,
        max_version,
        shanghai_now(),
        performance_ids=performance_ids,
    )
    from app.schemas.weekly_scheduling import AssignmentInput, ScheduleMutationRequest
    from app.services.performance_fulfillment import reconcile_effective_business
    from app.services.weekly_scheduling import (
        _reconcile_designations,
        _reconcile_wishes,
        validate_schedule,
    )

    day_payload = ScheduleMutationRequest(
        theater_id=payload.theater_id,
        week_start=payload.week_start,
        expected_version=batch.version,
        assignments=[
            AssignmentInput(
                performance_id=row.performance_id,
                role_id=row.role_id,
                actor_id=row.actor_id,
                source=row.source,
            )
            for row in rows
        ],
        confirm_conflicts=True,
        idempotency_key=payload.idempotency_key,
    )
    validation = validate_schedule(db, day_payload)
    target_ids = sorted(performance_ids)
    reconcile_effective_business(
        db,
        target_ids,
        {(row.performance_id, row.role_id, row.actor_id) for row in day_payload.assignments},
        operator.id,
        idempotency_key=payload.idempotency_key,
    )
    _reconcile_designations(db, day_payload, validation, operator.id, target_ids)
    _reconcile_wishes(db, day_payload, operator.id, target_ids)
    response = {
        "published_performance_ids": sorted(performance_ids),
        "publication_version": max_version,
        "workspace": get_workspace(db, payload.theater_id, payload.week_start),
    }
    db.add(
        DailyPublishOperation(
            idempotency_key=payload.idempotency_key,
            theater_id=payload.theater_id,
            performance_date=payload.performance_date,
            weekly_batch_id=batch.id,
            operator_user_id=operator.id,
            request_hash=request_hash,
            response_snapshot={
                "published_performance_ids": sorted(performance_ids),
                "publication_version": max_version,
            },
        )
    )
    db.commit()
    return response


def snapshot_published_week(db: Session, batch: WeeklyBatch, operator_user_id: int) -> None:
    grouped: dict[int, list[ScheduleAssignment]] = {}
    for row in db.scalars(
        select(ScheduleAssignment).where(ScheduleAssignment.weekly_batch_id == batch.id)
    ):
        grouped.setdefault(row.performance_id, []).append(row)
    existing = (
        {
            row.performance_id: row
            for row in db.scalars(
                select(PerformanceCastPublication)
                .where(PerformanceCastPublication.performance_id.in_(grouped))
                .options(selectinload(PerformanceCastPublication.assignments))
            )
        }
        if grouped
        else {}
    )
    now = utc_now()
    for performance_id, rows in grouped.items():
        digest = assignment_hash(rows)
        publication = existing.get(performance_id)
        if publication is not None and publication.assignment_hash == digest:
            continue
        if publication is None:
            publication = PerformanceCastPublication(
                performance_id=performance_id,
                theater_id=batch.theater_id,
                weekly_batch_id=batch.id,
                version=1,
                source_batch_version=batch.version,
                assignment_hash=digest,
                published_at=now,
                operator_user_id=operator_user_id,
            )
            db.add(publication)
            db.flush()
        else:
            publication.version += 1
            publication.source_batch_version = batch.version
            publication.assignment_hash = digest
            publication.published_at = now
            publication.operator_user_id = operator_user_id
            db.execute(
                delete(PublishedCastAssignment).where(
                    PublishedCastAssignment.publication_id == publication.id
                )
            )
        db.add_all(
            [
                PublishedCastAssignment(
                    publication_id=publication.id,
                    performance_id=row.performance_id,
                    role_id=row.role_id,
                    actor_id=row.actor_id,
                    source=row.source,
                )
                for row in rows
            ]
        )
    db.flush()
