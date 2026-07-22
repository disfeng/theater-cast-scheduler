"""Publication orchestration for weekly scheduling."""

from collections import defaultdict
import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

from app.core.time import utc_now

from app.models.entities import (
    Role,
    ScheduleAssignment,
    User,
    WeeklyBatch,
    WeeklyPublishOperation,
)
from app.models.enums import (
    BatchStatus,
)
from app.schemas.weekly_scheduling import (
    ScheduleMutationRequest,
)


from app.services.weekly_scheduling import (
    ConflictsRequireConfirmation,
    IncompletePerformancesError,
    PublishOperationConflict,
    ScheduleVersionConflict,
    UnmetDesignationsRequireConfirmation,
    _assert_locked_unchanged,
    _canonical_publish_hash,
    _get_or_create_locked_batch,
    _performances,
    _reconcile_designations,
    _reconcile_wishes,
    _scope_hash,
    _unmet_scope,
    _week_end,
    _week_performance_ids_including_cancelled,
    get_workspace,
    validate_schedule,
)


def _publication_checkpoint(stage: str) -> None:
    """Keep the legacy test/extension hook observable through the facade."""
    from app.services import weekly_scheduling

    weekly_scheduling._publish_checkpoint(stage)


def persist_schedule(
    db: Session, payload: ScheduleMutationRequest, publish: bool, operator_email: str | None = None
) -> dict[str, object]:
    week_performances = _performances(
        db, payload.theater_id, payload.week_start, _week_end(payload.week_start)
    )
    _assert_locked_unchanged(db, [row.id for row in week_performances], payload.assignments)
    validation = validate_schedule(db, payload)
    if publish:
        active_role_ids = set(
            db.scalars(
                select(Role.id).where(
                    Role.theater_id == payload.theater_id,
                    Role.is_active.is_(True),
                )
            )
        )
        assigned_roles: dict[int, set[int]] = defaultdict(set)
        for assignment in payload.assignments:
            assigned_roles[assignment.performance_id].add(assignment.role_id)
        incomplete = [
            {
                "performance_id": performance.id,
                "missing_role_ids": sorted(
                    active_role_ids - assigned_roles.get(performance.id, set())
                ),
            }
            for performance in week_performances
            if assigned_roles.get(performance.id, set()) != active_role_ids
        ]
        if incomplete:
            raise IncompletePerformancesError(incomplete)
    if validation["conflicts"] and not payload.confirm_conflicts:
        raise ConflictsRequireConfirmation(validation["conflicts"])
    batch = db.scalar(
        select(WeeklyBatch)
        .where(
            WeeklyBatch.theater_id == payload.theater_id,
            WeeklyBatch.week_start == payload.week_start,
        )
        .with_for_update()
    )
    current_version = batch.version if batch else 0
    operator = None
    operation = None
    request_hash = None
    unmet: list[dict[str, object]] = []
    if publish:
        if not payload.idempotency_key:
            payload = payload.model_copy(update={"idempotency_key": secrets.token_urlsafe(24)})
        operator = (
            db.scalar(select(User).where(User.email == operator_email))
            if operator_email
            else db.scalar(select(User).order_by(User.id))
        )
        if operator is None:
            raise LookupError("operator_user_not_found")
        request_hash = _canonical_publish_hash(payload)
        operation = db.scalar(
            select(WeeklyPublishOperation)
            .where(WeeklyPublishOperation.idempotency_key == payload.idempotency_key)
            .with_for_update()
        )
        if operation:
            if (
                operation.theater_id != payload.theater_id
                or operation.week_start != payload.week_start
            ):
                raise PublishOperationConflict("publish_idempotency_scope_conflict")
            if operation.operator_user_id != operator.id:
                raise PublishOperationConflict("publish_idempotency_operator_conflict")
            if operation.request_hash != request_hash:
                raise PublishOperationConflict("publish_idempotency_hash_conflict")
            if operation.status == "completed":
                return operation.response_snapshot
    if payload.expected_version is not None and payload.expected_version != current_version:
        raise ScheduleVersionConflict(current_version)
    if publish:
        unmet = _unmet_scope(db, payload, validation)
        if unmet:
            current_scope_hash = _scope_hash(unmet)
            if operation is None:
                operation = WeeklyPublishOperation(
                    idempotency_key=payload.idempotency_key,
                    theater_id=payload.theater_id,
                    week_start=payload.week_start,
                    weekly_batch_id=batch.id if batch else None,
                    operator_user_id=operator.id,
                    request_hash=request_hash,
                    status="pending_confirmation",
                    confirmation_token=secrets.token_urlsafe(32),
                    unmet_scope_hash=current_scope_hash,
                    unmet_scope=unmet,
                )
                db.add(operation)
                db.commit()
                raise UnmetDesignationsRequireConfirmation(
                    unmet, operation.confirmation_token, payload.idempotency_key
                )
            if (
                operation.status != "pending_confirmation"
                or payload.confirmation_token != operation.confirmation_token
            ):
                raise PublishOperationConflict("publish_confirmation_token_required")
            if operation.unmet_scope_hash != current_scope_hash or operation.unmet_scope != unmet:
                raise PublishOperationConflict("stale_confirmation")
        elif operation and operation.status == "pending_confirmation":
            raise PublishOperationConflict("stale_confirmation")
    if batch is None:
        batch = _get_or_create_locked_batch(db, payload.theater_id, payload.week_start)
        current_version = batch.version
        if payload.expected_version is not None and payload.expected_version != current_version:
            raise ScheduleVersionConflict(current_version)
    if publish and operation is None:
        operation = WeeklyPublishOperation(
            idempotency_key=payload.idempotency_key,
            theater_id=payload.theater_id,
            week_start=payload.week_start,
            weekly_batch_id=batch.id,
            operator_user_id=operator.id,
            request_hash=request_hash,
            status="processing",
        )
        db.add(operation)
        db.flush()
    elif publish:
        operation.weekly_batch_id = batch.id
        operation.status = "processing"
    db.execute(delete(ScheduleAssignment).where(ScheduleAssignment.weekly_batch_id == batch.id))
    conflict_codes: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for conflict in validation["conflicts"]:
        conflict_codes[
            (conflict["performance_id"], conflict["role_id"], conflict["actor_id"])
        ].append(conflict["code"])
    for row in payload.assignments:
        codes = conflict_codes[(row.performance_id, row.role_id, row.actor_id)]
        db.add(
            ScheduleAssignment(
                weekly_batch_id=batch.id,
                performance_id=row.performance_id,
                role_id=row.role_id,
                actor_id=row.actor_id,
                source=row.source,
                conflict_codes=codes,
                requires_approval=bool(codes),
                approved=bool(codes and payload.confirm_conflicts),
            )
        )
    db.flush()
    _publication_checkpoint("assignments")
    batch.version = current_version + 1
    batch.updated_at = utc_now()
    batch.status = BatchStatus.SCHEDULED if publish else BatchStatus.READY
    batch.published_at = utc_now() if publish else None
    if publish:
        from app.services.schedule_publications import snapshot_published_week

        snapshot_published_week(db, batch, operator.id)
        from app.services.performance_fulfillment import reconcile_effective_business

        performance_ids = _week_performance_ids_including_cancelled(
            db, payload.theater_id, payload.week_start
        )
        reconcile_effective_business(
            db,
            performance_ids,
            {(row.performance_id, row.role_id, row.actor_id) for row in payload.assignments},
            operator.id,
            idempotency_key=payload.idempotency_key or f"publish:{payload.week_start}",
        )
        _reconcile_designations(db, payload, validation, operator.id)
        _reconcile_wishes(db, payload, operator.id)
        from app.services.actor_notifications import reconcile_notification_tasks, shanghai_now

        reconcile_notification_tasks(
            db,
            payload.theater_id,
            payload.week_start,
            batch.version,
            shanghai_now(),
        )
        db.flush()
        result = get_workspace(db, payload.theater_id, payload.week_start)
        operation.status = "completed"
        operation.response_snapshot = jsonable_encoder(result)
        operation.completed_at = utc_now()
        db.flush()
        _publication_checkpoint("operation_snapshot")
    db.commit()
    return (
        operation.response_snapshot
        if publish
        else get_workspace(db, payload.theater_id, payload.week_start)
    )


__all__ = ["persist_schedule"]
