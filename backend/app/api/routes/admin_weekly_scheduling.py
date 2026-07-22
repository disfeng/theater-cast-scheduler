from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.csv_export import csv_response
from app.services.admin_scope import AdminScope
from app.schemas.weekly_scheduling import (
    DailySchedulePublishRequest,
    MultiWeekValidationRequest,
    ScheduleMutationRequest,
    WeeklyScheduleWorkspaceRead,
)
from app.services.schedule_publications import (
    RepublishConfirmationRequired,
    publish_schedule_day,
)
from app.services.weekly_scheduling import (
    ConflictsRequireConfirmation,
    IncompletePerformancesError,
    PredesignationLockedError,
    PublishOperationConflict,
    ScheduleVersionConflict,
    UnmetDesignationsRequireConfirmation,
)
from app.services.weekly_commands import recommend_schedule
from app.services.weekly_conflicts import validate_schedule, validate_schedule_context
from app.services.weekly_publication import persist_schedule
from app.services.weekly_workspace import get_workspace

router = APIRouter(prefix="/admin/weekly-schedules", tags=["admin-weekly-scheduling"])


def _handle(operation, db: Session | None = None):
    try:
        return operation()
    except ConflictsRequireConfirmation as exc:
        summary: dict[str, int] = {}
        for item in exc.conflicts:
            summary[item["code"]] = summary.get(item["code"], 0) + 1
        raise HTTPException(
            409,
            detail={
                "code": "conflicts_require_confirmation",
                "conflicts": exc.conflicts,
                "summary": summary,
            },
        ) from exc
    except IncompletePerformancesError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "incomplete_performances",
                "performances": exc.performances,
            },
        ) from exc
    except PredesignationLockedError as exc:
        raise HTTPException(
            409, detail={"code": "predesignation_locked", "designation_ids": exc.designation_ids}
        ) from exc
    except UnmetDesignationsRequireConfirmation as exc:
        raise HTTPException(
            409,
            detail={
                "code": "unmet_designations_require_confirmation",
                "designations": exc.designations,
                "confirmation_token": exc.confirmation_token,
                "idempotency_key": exc.idempotency_key,
            },
        ) from exc
    except PublishOperationConflict as exc:
        raise HTTPException(409, detail={"code": exc.code}) from exc
    except RepublishConfirmationRequired as exc:
        raise HTTPException(
            409,
            detail={
                "code": "republish_confirmation_required",
                "added": exc.added,
                "changed": exc.changed,
                "removed": exc.removed,
            },
        ) from exc
    except ScheduleVersionConflict as exc:
        raise HTTPException(
            409,
            detail={"code": "schedule_version_conflict", "current_version": exc.current_version},
        ) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except Exception:
        if db is not None:
            db.rollback()
        raise


@router.get("/workspace", response_model=WeeklyScheduleWorkspaceRead)
def workspace(
    theater_id: int,
    week_start: date,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    return _handle(lambda: get_workspace(db, theater_id, week_start))


@router.get("/export", response_class=Response)
def export_workspace(
    theater_id: int,
    week_start: date,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    data = _handle(lambda: get_workspace(db, theater_id, week_start))
    actors = {row["id"]: row for row in data["actors"]}
    assignment_by_slot = {
        (assignment["performance_id"], assignment["role_id"]): actors[
            assignment["actor_id"]
        ]["display_name"]
        for assignment in data["assignments"]
    }
    roles = data["roles"]
    rows = [
        (
            performance["performance_date"].isoformat(),
            performance["slot_name"],
            performance["start_time"].strftime("%H:%M"),
            *(
                assignment_by_slot.get((performance["id"], role["id"]), "")
                for role in roles
            ),
            "已发布" if performance["publication_status"] == "published" else "草稿",
        )
        for performance in data["performances"]
    ]
    return csv_response(
        f"weekly-schedule-{week_start.isoformat()}.csv",
        ("日期", "场次", "时间", *(role["name"] for role in roles), "发布状态"),
        rows,
    )


@router.post("/validate")
def validate(
    payload: ScheduleMutationRequest,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(payload.theater_id)
    return _handle(lambda: validate_schedule(db, payload))


@router.post("/validate-context")
def validate_context(
    payload: MultiWeekValidationRequest,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(payload.theater_id)
    return _handle(lambda: validate_schedule_context(db, payload))


@router.post("/recommend", response_model=WeeklyScheduleWorkspaceRead)
def recommend(
    payload: ScheduleMutationRequest,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(payload.theater_id)
    return _handle(lambda: recommend_schedule(db, payload))


@router.put("/draft", response_model=WeeklyScheduleWorkspaceRead)
def save_draft(
    payload: ScheduleMutationRequest,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(payload.theater_id)
    return _handle(lambda: persist_schedule(db, payload, False))


@router.post("/publish", response_model=WeeklyScheduleWorkspaceRead)
def publish(
    payload: ScheduleMutationRequest,
    user: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user.require_theater(payload.theater_id)
    return _handle(lambda: persist_schedule(db, payload, True, user["sub"]), db)


@router.post("/publish-day")
def publish_day(
    payload: DailySchedulePublishRequest,
    user: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user.require_theater(payload.theater_id)
    return _handle(lambda: publish_schedule_day(db, payload, user["sub"]), db)
