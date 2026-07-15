from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.schemas.weekly_scheduling import ScheduleMutationRequest, WeeklyScheduleWorkspaceRead
from app.services.weekly_scheduling import (
    ConflictsRequireConfirmation,
    IncompletePerformancesError,
    ScheduleVersionConflict,
    get_workspace,
    persist_schedule,
    recommend_schedule,
    validate_schedule,
)

router = APIRouter(prefix="/admin/weekly-schedules", tags=["admin-weekly-scheduling"])


def _handle(operation):
    try:
        return operation()
    except ConflictsRequireConfirmation as exc:
        summary: dict[str, int] = {}
        for item in exc.conflicts:
            summary[item["code"]] = summary.get(item["code"], 0) + 1
        raise HTTPException(409, detail={"code": "conflicts_require_confirmation", "conflicts": exc.conflicts, "summary": summary}) from exc
    except IncompletePerformancesError as exc:
        raise HTTPException(409, detail={
            "code": "incomplete_performances",
            "performances": exc.performances,
        }) from exc
    except ScheduleVersionConflict as exc:
        raise HTTPException(409, detail={"code": "schedule_version_conflict", "current_version": exc.current_version}) from exc
    except LookupError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/workspace", response_model=WeeklyScheduleWorkspaceRead)
def workspace(theater_id: int, week_start: date, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return _handle(lambda: get_workspace(db, theater_id, week_start))


@router.post("/validate")
def validate(payload: ScheduleMutationRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return _handle(lambda: validate_schedule(db, payload))


@router.post("/recommend", response_model=WeeklyScheduleWorkspaceRead)
def recommend(payload: ScheduleMutationRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return _handle(lambda: recommend_schedule(db, payload))


@router.put("/draft", response_model=WeeklyScheduleWorkspaceRead)
def save_draft(payload: ScheduleMutationRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return _handle(lambda: persist_schedule(db, payload, False))


@router.post("/publish", response_model=WeeklyScheduleWorkspaceRead)
def publish(payload: ScheduleMutationRequest, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return _handle(lambda: persist_schedule(db, payload, True))
