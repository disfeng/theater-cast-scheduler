from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_user
from app.models.entities import Actor, LeaveRequest, ScheduleAssignment, User
from app.models.enums import LeaveStatus, UserRole

router = APIRouter(prefix="/actor", tags=["actor"])


class LeaveRequestInput(BaseModel):
    dates: list[date]
    note: str | None = None


@router.get("/me/schedule")
def my_schedule(
    user: dict[str, str] = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    actor = _get_or_create_actor_user(db, user["sub"])
    assignments = db.scalars(
        select(ScheduleAssignment).where(ScheduleAssignment.actor_id == actor.id)
    ).all()
    return [
        {
            "date": assignment.performance.performance_date.isoformat(),
            "slot": assignment.performance.slot_name_snapshot,
            "role": assignment.role.name,
            "status": assignment.performance.status.value,
        }
        for assignment in assignments
    ]


@router.post("/me/leave-requests")
def submit_leave(
    payload: LeaveRequestInput,
    user: dict[str, str] = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    actor = _get_or_create_actor_user(db, user["sub"])
    submitted_dates: list[str] = []
    for leave_date in payload.dates:
        existing = db.scalar(
            select(LeaveRequest).where(
                LeaveRequest.actor_id == actor.id,
                LeaveRequest.leave_date == leave_date,
            )
        )
        if existing is None:
            db.add(
                LeaveRequest(
                    actor_id=actor.id,
                    leave_date=leave_date,
                    status=LeaveStatus.PENDING,
                    note=payload.note,
                )
            )
        elif existing.status not in {LeaveStatus.LOCKED, LeaveStatus.APPROVED}:
            existing.status = LeaveStatus.PENDING
            existing.note = payload.note
        submitted_dates.append(leave_date.isoformat())
    db.commit()
    return {"status": "submitted", "dates": submitted_dates}


def _get_or_create_actor_user(db: Session, email: str) -> Actor:
    db_user = db.scalar(select(User).where(User.email == email))
    if db_user and db_user.actor:
        return db_user.actor

    actor = Actor(display_name=email, max_consecutive_performances=3)
    db.add(actor)
    db.flush()

    if db_user is None:
        db_user = User(
            email=email,
            password_hash="external-demo-auth",
            role=UserRole.ACTOR,
            actor_id=actor.id,
        )
        db.add(db_user)
    else:
        db_user.actor_id = actor.id
    db.commit()
    db.refresh(actor)
    return actor
