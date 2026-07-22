"""Conflict validation implementation for weekly scheduling."""

from sqlalchemy.orm import Session


from app.models.entities import (
    Performance,
)
from app.schemas.weekly_scheduling import (
    AssignmentInput,
    MultiWeekValidationRequest,
    ScheduleMutationRequest,
)


from app.services.weekly_scheduling import (
    _performances,
    _validate_assignments,
    _week_end,
)


def validate_schedule(db: Session, payload: ScheduleMutationRequest) -> dict[str, object]:
    end = _week_end(payload.week_start)
    week_performances = _performances(db, payload.theater_id, payload.week_start, end)
    context_week_starts = {week.week_start for week in payload.context_weeks}
    if payload.week_start in context_week_starts or len(context_week_starts) != len(
        payload.context_weeks
    ):
        raise ValueError("duplicate_week_context")
    return _validate_assignments(
        db,
        payload.theater_id,
        payload.assignments,
        week_performances,
        {payload.week_start, *context_week_starts},
        [assignment for week in payload.context_weeks for assignment in week.assignments],
    )


def validate_schedule_context(
    db: Session, payload: MultiWeekValidationRequest
) -> dict[str, object]:
    week_starts = [week.week_start for week in payload.weeks]
    if len(week_starts) != len(set(week_starts)):
        raise ValueError("duplicate_week_context")
    scope_performances: list[Performance] = []
    assignments: list[AssignmentInput] = []
    for week in payload.weeks:
        scope_performances.extend(
            _performances(
                db,
                payload.theater_id,
                week.week_start,
                _week_end(week.week_start),
            )
        )
        assignments.extend(week.assignments)
    return _validate_assignments(
        db,
        payload.theater_id,
        assignments,
        scope_performances,
        set(week_starts),
    )


__all__ = ["validate_schedule", "validate_schedule_context"]
