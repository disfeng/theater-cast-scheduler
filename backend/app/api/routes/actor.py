from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import require_user

router = APIRouter(prefix="/actor", tags=["actor"])


class LeaveRequestInput(BaseModel):
    dates: list[date]
    note: str | None = None


@router.get("/me/schedule")
def my_schedule(_: dict[str, str] = Depends(require_user)) -> list[dict[str, str]]:
    return []


@router.post("/me/leave-requests")
def submit_leave(payload: LeaveRequestInput, _: dict[str, str] = Depends(require_user)) -> dict[str, object]:
    return {"status": "submitted", "dates": [item.isoformat() for item in payload.dates]}
