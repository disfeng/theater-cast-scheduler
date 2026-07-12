from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import Actor, LeaveRequest, Role, Theater
from app.models.enums import LeaveStatus
from app.schemas.admin import (
    ActorCreate,
    ActorRead,
    ActorUpdate,
    CapabilityUpdate,
    DashboardRead,
    LeaveRead,
    LeaveReviewInput,
    RoleCreate,
    RoleRead,
    TheaterCreate,
    TheaterRead,
)
from app.services.admin_data import (
    create_actor,
    create_role,
    create_theater,
    list_actors,
    list_leave_requests,
    list_roles,
    list_theaters,
    replace_actor_capabilities,
    review_leave_request,
    update_actor,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(_: dict[str, str] = Depends(require_admin)) -> DashboardRead:
    return DashboardRead(
        pending_leave_requests=0,
        pending_designations=0,
        approval_required_assignments=0,
        unpublished_performances=0,
    )


@router.get("/theaters", response_model=list[TheaterRead])
def get_theaters(
    _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
) -> list[Theater]:
    return list_theaters(db)


@router.post("/theaters", response_model=TheaterRead)
def post_theater(
    payload: TheaterCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Theater:
    return create_theater(db, payload)


@router.get("/roles", response_model=list[RoleRead])
def get_roles(
    _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
) -> list[Role]:
    return list_roles(db)


@router.post("/roles", response_model=RoleRead)
def post_role(
    payload: RoleCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Role:
    return create_role(db, payload)


@router.get("/actors", response_model=list[ActorRead])
def get_actors(
    _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
) -> list[ActorRead]:
    return [_actor_read(actor) for actor in list_actors(db)]


@router.post("/actors", response_model=ActorRead)
def post_actor(
    payload: ActorCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    return _actor_read(create_actor(db, payload))


@router.patch("/actors/{actor_id}", response_model=ActorRead)
def patch_actor(
    actor_id: int,
    payload: ActorUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    try:
        return _actor_read(update_actor(db, actor_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/actors/{actor_id}/capabilities", response_model=ActorRead)
def put_actor_capabilities(
    actor_id: int,
    payload: CapabilityUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead:
    try:
        return _actor_read(replace_actor_capabilities(db, actor_id, payload.role_ids))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/leave-requests", response_model=list[LeaveRead])
def get_leave_requests(
    status: LeaveStatus | None = None,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LeaveRead]:
    return [_leave_read(leave) for leave in list_leave_requests(db, status)]


@router.post("/leave-requests/{leave_id}/review", response_model=LeaveRead)
def post_leave_review(
    leave_id: int,
    payload: LeaveReviewInput,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LeaveRead:
    try:
        return _leave_read(review_leave_request(db, leave_id, payload.status))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _actor_read(actor: Actor) -> ActorRead:
    return ActorRead(
        id=actor.id,
        display_name=actor.display_name,
        max_consecutive_performances=actor.max_consecutive_performances,
        rating_level=actor.rating_level,
        low_rating_monthly_cap=actor.low_rating_monthly_cap,
        notes=actor.notes,
        role_ids=[capability.role_id for capability in actor.role_capabilities],
    )


def _leave_read(leave: LeaveRequest) -> LeaveRead:
    return LeaveRead(
        id=leave.id,
        actor_id=leave.actor_id,
        actor_name=leave.actor.display_name,
        leave_date=leave.leave_date,
        status=leave.status,
        note=leave.note,
    )
