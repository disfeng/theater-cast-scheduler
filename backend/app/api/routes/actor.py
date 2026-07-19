from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_actor_ready, require_user
from app.models.entities import Actor, LeaveRequest, ScheduleAssignment, User, WeeklyBatch
from app.models.enums import BatchStatus, LeaveStatus, UserRole
from app.schemas.actor_workspace import (
    ActorProfileRead,
    ActorProfileTheater,
    PasswordChangeInput,
)
from app.services.actor_accounts import change_actor_password

router = APIRouter(prefix="/actor", tags=["actor"])


class LeaveRequestInput(BaseModel):
    dates: list[date]
    note: str | None = None


@router.post("/me/password")
def change_password(
    payload: PasswordChangeInput,
    user: dict[str, object] = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if user["role"] != "actor" or user.get("user_id") is None:
        raise HTTPException(status_code=403, detail="Actor role required")
    try:
        change_actor_password(
            db, int(user["user_id"]), payload.current_password, payload.new_password
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "password_changed"}


@router.get("/me/profile", response_model=ActorProfileRead)
def profile(
    user: dict[str, object] = Depends(require_user),
    db: Session = Depends(get_db),
) -> ActorProfileRead:
    if user["role"] != "actor" or user.get("actor_id") is None:
        raise HTTPException(status_code=403, detail="Actor role required")
    actor = db.get(Actor, int(user["actor_id"]))
    if actor is None or actor.phone_number is None:
        raise HTTPException(status_code=404, detail="actor_account_not_found")
    return ActorProfileRead(
        id=actor.id,
        display_name=actor.display_name,
        phone_number=actor.phone_number,
        must_change_password=bool(user.get("must_change_password")),
        theaters=[
            ActorProfileTheater(
                id=membership.theater.id,
                name=membership.theater.name,
                is_entry_theater=membership.is_entry_theater,
            )
            for membership in actor.theater_memberships
        ],
    )


@router.get("/me/schedule")
def my_schedule(
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> list[dict[str, str]]:
    actor = _get_or_create_actor_user(db, str(user["sub"]))
    assignments = db.scalars(
        select(ScheduleAssignment)
        .join(WeeklyBatch, ScheduleAssignment.weekly_batch_id == WeeklyBatch.id)
        .where(
            ScheduleAssignment.actor_id == actor.id,
            WeeklyBatch.status == BatchStatus.SCHEDULED,
        )
        .order_by(
            ScheduleAssignment.performance_id,
            ScheduleAssignment.role_id,
        )
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
