"""Read-side implementation for the weekly scheduling workspace."""

from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload


from app.models.entities import (
    Designation,
    Role,
    Theater,
    WeeklyBatch,
)
from app.schemas.weekly_scheduling import (
    AssignmentInput,
    ScheduleMutationRequest,
)


from app.services.weekly_scheduling import (
    _actors,
    _designation_parties,
    _inject_locked,
    _performances,
    _week_end,
    validate_schedule,
)


def get_workspace(db: Session, theater_id: int, week_start: date) -> dict[str, object]:
    from app.services.schedule_publications import assignment_hash

    end = _week_end(week_start)
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    performances = _performances(db, theater_id, week_start, end)
    roles = list(
        db.scalars(
            select(Role)
            .where(Role.theater_id == theater_id, Role.is_active.is_(True))
            .order_by(Role.id)
        )
    )
    actors = _actors(db)
    batch = db.scalar(
        select(WeeklyBatch)
        .where(WeeklyBatch.theater_id == theater_id, WeeklyBatch.week_start == week_start)
        .options(selectinload(WeeklyBatch.assignments))
    )
    assignments = list(batch.assignments) if batch else []
    request = ScheduleMutationRequest(
        theater_id=theater_id,
        week_start=week_start,
        expected_version=batch.version if batch else 0,
        assignments=[
            AssignmentInput(
                performance_id=row.performance_id,
                role_id=row.role_id,
                actor_id=row.actor_id,
                source=row.source,
            )
            for row in assignments
        ],
        confirm_conflicts=True,
    )
    validation = validate_schedule(db, request)
    summary = dict(Counter(item["code"] for item in validation["conflicts"]))
    warning_summary = dict(Counter(item["code"] for item in validation["warnings"]))
    week_counts = Counter(row.actor_id for row in assignments)
    role_ids = {role.id for role in roles}
    performance_ids = [row.id for row in performances]
    from app.models.entities import PerformanceCastPublication

    publications = (
        {
            row.performance_id: row
            for row in db.scalars(
                select(PerformanceCastPublication)
                .where(PerformanceCastPublication.performance_id.in_(performance_ids))
                .options(selectinload(PerformanceCastPublication.assignments))
            )
        }
        if performance_ids
        else {}
    )
    unmet_rows = (
        list(
            db.scalars(
                select(Designation).where(
                    Designation.performance_id.in_(performance_ids),
                    Designation.lifecycle_status == "unsatisfied",
                )
            )
        )
        if performance_ids
        else []
    )
    serialized_assignments = _inject_locked(
        db,
        [row.id for row in performances],
        [
            {
                "performance_id": row.performance_id,
                "role_id": row.role_id,
                "actor_id": row.actor_id,
                "source": row.source,
                "conflict_codes": row.conflict_codes,
            }
            for row in assignments
        ],
    )
    return {
        "theater_id": theater_id,
        "week_start": week_start,
        "week_end": end,
        "batch_id": batch.id if batch else None,
        "status": (
            "scheduled"
            if performance_ids and len(publications) == len(performance_ids)
            else "partial"
            if publications
            else batch.status.value
            if batch
            else "uncreated"
        ),
        "version": batch.version if batch else 0,
        "updated_at": batch.updated_at if batch else None,
        "published_at": (
            max((row.published_at for row in publications.values()), default=None)
            or (batch.published_at if batch else None)
        ),
        "performances": [
            {
                "id": row.id,
                "performance_date": row.performance_date,
                "slot_name": row.slot_name_snapshot,
                "start_time": row.start_time_snapshot,
                "sort_order": row.theater_slot.sort_order if row.theater_slot else 0,
                "publication_status": "published" if row.id in publications else "draft",
                "publication_version": publications[row.id].version
                if row.id in publications
                else None,
                "has_unpublished_changes": (
                    assignment_hash([item for item in assignments if item.performance_id == row.id])
                    != publications[row.id].assignment_hash
                    if row.id in publications
                    else False
                ),
            }
            for row in performances
        ],
        "roles": [{"id": row.id, "name": row.name, "group_name": row.group_name} for row in roles],
        "actors": [
            {
                "id": row.id,
                "display_name": row.display_name,
                "rating_level": row.rating_level.value,
                "max_consecutive_performances": row.max_consecutive_performances,
                "low_rating_monthly_cap": row.low_rating_monthly_cap,
                "role_ids": [
                    cap.role_id for cap in row.role_capabilities if cap.role_id in role_ids
                ],
                "weekly_count": week_counts[row.id],
                "monthly_count": 0,
            }
            for row in actors
        ],
        "assignments": serialized_assignments,
        "conflicts": validation["conflicts"],
        "conflict_summary": summary,
        "warnings": validation["warnings"],
        "warning_summary": warning_summary,
        "empty_slots": validation["empty_slots"],
        "unsatisfied_designations": [
            {
                "id": row.id,
                "player_name": row.player_name,
                "role_id": row.role_id,
                "actor_id": row.actor_id,
                "performance_id": row.performance_id,
                "failure_reason": row.failure_reason,
                "refund_status": "released",
                "refund_target": _designation_parties(db, row)[0],
                "legacy_identity_fallback": _designation_parties(db, row)[2],
            }
            for row in unmet_rows
        ],
        "unsatisfied_wishes": [],
    }


__all__ = ["get_workspace"]
