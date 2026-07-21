from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_actor_ready, require_user
from app.models.entities import Actor, ActorNotification, LeaveApplication, LeaveRequest, User
from app.models.enums import LeaveStatus, UserRole
from app.schemas.actor_workspace import (
    ActorProfileRead,
    ActorProfileTheater,
    ActorCalendarRead,
    ActorDashboardRead,
    ActorPerformanceRead,
    LeaveApplicationCreate,
    LeaveApplicationDayRead,
    LeaveApplicationRead,
    PasswordChangeInput,
)
from app.schemas.auth import TokenResponse
from app.services.actor_accounts import change_actor_password
from app.services.auth import create_access_token
from app.services.actor_notifications import reveal_due_tasks, shanghai_now
from app.services.actor_leaves import list_actor_leave_applications, submit_leave_application, withdraw_leave_day

router = APIRouter(prefix="/actor", tags=["actor"])


class LeaveRequestInput(BaseModel):
    dates: list[date]
    note: str | None = None


def _leave_application_read(row: LeaveApplication) -> LeaveApplicationRead:
    return LeaveApplicationRead(
        id=row.id,
        actor_id=row.actor_id,
        actor_name=row.actor.display_name,
        theater_id=row.theater_id,
        theater_name=row.theater.name,
        note=row.note,
        created_at=row.created_at,
        days=[
            LeaveApplicationDayRead(
                id=day.id,
                leave_date=day.leave_date,
                status="withdrawn" if day.withdrawn_at else day.status.value,
                has_schedule_conflict=day.has_schedule_conflict,
                review_reason=day.review_reason,
                reviewed_at=day.reviewed_at,
                withdrawn_at=day.withdrawn_at,
            ) for day in row.days
        ],
    )


@router.post("/me/password", response_model=TokenResponse)
def change_password(
    payload: PasswordChangeInput,
    user: dict[str, object] = Depends(require_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
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
    return TokenResponse(
        access_token=create_access_token(
            str(user["sub"]),
            "actor",
            user_id=int(user["user_id"]),
            actor_id=int(user["actor_id"]) if user.get("actor_id") is not None else None,
            must_change_password=False,
        ),
        role="actor",
        must_change_password=False,
    )


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


DESIGNATION_LABELS = {
    "universal": "万能指定",
    "top_three": "榜三指定",
    "paired": "对位指定",
}


def _notification_read(row: ActorNotification) -> ActorPerformanceRead:
    return ActorPerformanceRead(
        notification_id=row.id,
        theater_id=row.theater_id,
        theater_name=row.theater_name_snapshot,
        performance_id=row.performance_id,
        performance_date=row.performance_date_snapshot,
        slot_name=row.slot_name_snapshot,
        start_time=row.start_time_snapshot,
        role_name=row.role_name_snapshot,
        player_name=row.player_name_snapshot,
        designation_type=row.designation_type_snapshot,
        designation_label=DESIGNATION_LABELS.get(row.designation_type_snapshot or ""),
        read_at=row.read_at,
    )


@router.get("/me/calendar", response_model=ActorCalendarRead)
def calendar(
    month: str,
    theater_id: int | None = None,
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> ActorCalendarRead:
    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid_month") from exc
    next_month = (
        month_start.replace(year=month_start.year + 1, month=1)
        if month_start.month == 12
        else month_start.replace(month=month_start.month + 1)
    )
    reveal_due_tasks(db, now=shanghai_now())
    filters = [
        ActorNotification.actor_id == int(user["actor_id"]),
        ActorNotification.performance_date_snapshot >= month_start,
        ActorNotification.performance_date_snapshot < next_month,
    ]
    if theater_id is not None:
        filters.append(ActorNotification.theater_id == theater_id)
    rows = list(
        db.scalars(
            select(ActorNotification)
            .where(*filters)
            .order_by(
                ActorNotification.performance_date_snapshot,
                ActorNotification.start_time_snapshot,
                ActorNotification.id,
            )
        )
    )
    db.commit()
    return ActorCalendarRead(month=month, performances=[_notification_read(row) for row in rows])


@router.get("/me/dashboard", response_model=ActorDashboardRead)
def dashboard(
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> ActorDashboardRead:
    reveal_due_tasks(db, now=shanghai_now())
    rows = list(
        db.scalars(
            select(ActorNotification)
            .where(
                ActorNotification.actor_id == int(user["actor_id"]),
                ActorNotification.performance_date_snapshot >= date.today(),
            )
            .order_by(
                ActorNotification.performance_date_snapshot,
                ActorNotification.start_time_snapshot,
            )
            .limit(20)
        )
    )
    db.commit()
    return ActorDashboardRead(
        unread_count=sum(row.read_at is None for row in rows),
        upcoming=[_notification_read(row) for row in rows],
    )


@router.get("/me/notifications", response_model=list[ActorPerformanceRead])
def notifications(
    unread_only: bool = False,
    limit: int = 50,
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> list[ActorPerformanceRead]:
    reveal_due_tasks(db, now=shanghai_now())
    filters = [ActorNotification.actor_id == int(user["actor_id"])]
    if unread_only:
        filters.append(ActorNotification.read_at.is_(None))
    rows = list(
        db.scalars(
            select(ActorNotification)
            .where(*filters)
            .order_by(ActorNotification.created_at.desc(), ActorNotification.id.desc())
            .limit(max(1, min(limit, 100)))
        )
    )
    db.commit()
    return [_notification_read(row) for row in rows]


@router.post("/me/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = db.scalar(
        select(ActorNotification).where(
            ActorNotification.id == notification_id,
            ActorNotification.actor_id == int(user["actor_id"]),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="notification_not_found")
    row.read_at = row.read_at or shanghai_now()
    db.commit()
    return {"status": "read"}


@router.get("/me/schedule")
def my_schedule(
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    """Compatibility endpoint backed exclusively by disclosed snapshots."""
    current_month = shanghai_now().strftime("%Y-%m")
    result = calendar(current_month, None, user, db)
    return [row.model_dump() for row in result.performances]


@router.post("/me/leave-applications", response_model=LeaveApplicationRead)
def create_leave_application(
    payload: LeaveApplicationCreate,
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> LeaveApplicationRead:
    try:
        row = submit_leave_application(
            db, int(user["actor_id"]), payload.theater_id, payload.dates, payload.note
        )
        db.commit(); db.refresh(row)
        return _leave_application_read(row)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/me/leave-applications", response_model=list[LeaveApplicationRead])
def get_leave_applications(
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> list[LeaveApplicationRead]:
    return [_leave_application_read(row) for row in list_actor_leave_applications(db, int(user["actor_id"]))]


@router.post("/me/leave-application-days/{day_id}/withdraw", response_model=LeaveApplicationDayRead)
def withdraw_leave_application_day(
    day_id: int,
    user: dict[str, object] = Depends(require_actor_ready),
    db: Session = Depends(get_db),
) -> LeaveApplicationDayRead:
    try:
        day = withdraw_leave_day(db, int(user["actor_id"]), day_id); db.commit()
        return LeaveApplicationDayRead(
            id=day.id, leave_date=day.leave_date, status="withdrawn",
            has_schedule_conflict=day.has_schedule_conflict, review_reason=day.review_reason,
            reviewed_at=day.reviewed_at, withdrawn_at=day.withdrawn_at,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
