from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import require_admin
from app.models.enums import DesignationType
from app.schemas.scheduling import DesignationInput, PerformanceSlot, WishInput
from app.services.scheduler import SchedulingRuleError, generate_week_schedule

router = APIRouter(prefix="/scheduling", tags=["scheduling"])


class PerformancePayload(BaseModel):
    id: int
    date: date
    slot: str


class DesignationPayload(BaseModel):
    designation_type: DesignationType
    player_name: str
    role_id: int
    actor_id: int
    target_performance_id: int | None = None
    submitted_at: datetime


class WishPayload(BaseModel):
    player_name: str
    role_id: int
    actor_id: int
    note: str | None = None


class SchedulingPreviewRequest(BaseModel):
    performances: list[PerformancePayload]
    role_ids: list[int]
    actor_ids: list[int]
    actor_role_ids: dict[str, list[int]]
    max_consecutive: dict[str, int]
    approved_leave_dates: dict[str, list[date]]
    low_rating_caps: dict[str, int]
    monthly_counts: dict[str, int]
    designations: list[DesignationPayload]
    wishes: list[WishPayload]
    suspended_actor_ids: list[int] = []


@router.post("/preview")
def preview_schedule(payload: SchedulingPreviewRequest, _: dict[str, str] = Depends(require_admin)) -> dict[str, object]:
    try:
        result = generate_week_schedule(
            performances=[PerformanceSlot(item.id, item.date, item.slot) for item in payload.performances],
            role_ids=payload.role_ids,
            actor_ids=payload.actor_ids,
            actor_role_ids={int(key): set(value) for key, value in payload.actor_role_ids.items()},
            max_consecutive={int(key): value for key, value in payload.max_consecutive.items()},
            approved_leave_dates={int(key): set(value) for key, value in payload.approved_leave_dates.items()},
            low_rating_caps={int(key): value for key, value in payload.low_rating_caps.items()},
            monthly_counts={int(key): value for key, value in payload.monthly_counts.items()},
            existing_actor_slots={},
            locked_assignments=[],
            designations=[
                DesignationInput(
                    item.designation_type,
                    item.player_name,
                    item.role_id,
                    item.actor_id,
                    item.target_performance_id,
                    item.submitted_at,
                )
                for item in payload.designations
            ],
            wishes=[WishInput(item.player_name, item.role_id, item.actor_id, item.note) for item in payload.wishes],
            suspended_actor_ids=set(payload.suspended_actor_ids),
        )
    except SchedulingRuleError as exc:
        raise HTTPException(
            status_code=400,
            detail=[{"code": violation.code, "message": violation.message} for violation in exc.violations],
        ) from exc
    return {
        "assignments": [
            {"performance_id": performance_id, "role_id": role_id, "actor_id": assignment.actor_id}
            for (performance_id, role_id), assignment in sorted(result.assignments.items())
        ],
        "unsatisfied_designations": [
            {
                "player_name": item.player_name,
                "role_id": item.role_id,
                "actor_id": item.actor_id,
                "failure_reason": item.failure_reason,
            }
            for item in result.unsatisfied_designations
        ],
        "empty_slots": [{"performance_id": item[0], "role_id": item[1]} for item in result.empty_slots],
    }
