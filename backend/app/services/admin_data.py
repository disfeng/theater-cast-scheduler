from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Actor, ActorRoleCapability, LeaveRequest, Role, Theater
from app.models.enums import LeaveStatus
from app.schemas.admin import ActorCreate, ActorUpdate, RoleCreate, TheaterCreate


def create_theater(db: Session, payload: TheaterCreate) -> Theater:
    theater = Theater(name=payload.name, default_weekly_template=payload.default_weekly_template)
    db.add(theater)
    db.commit()
    db.refresh(theater)
    return theater


def list_theaters(db: Session) -> list[Theater]:
    return list(db.scalars(select(Theater).order_by(Theater.id)))


def create_role(db: Session, payload: RoleCreate) -> Role:
    role = Role(name=payload.name, group_name=payload.group_name)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.id)))


def create_actor(db: Session, payload: ActorCreate) -> Actor:
    actor = Actor(
        display_name=payload.display_name,
        max_consecutive_performances=payload.max_consecutive_performances,
        rating_level=payload.rating_level,
        low_rating_monthly_cap=payload.low_rating_monthly_cap,
        notes=payload.notes,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def list_actors(db: Session) -> list[Actor]:
    statement = select(Actor).options(selectinload(Actor.role_capabilities)).order_by(Actor.id)
    return list(db.scalars(statement))


def update_actor(db: Session, actor_id: int, payload: ActorUpdate) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise LookupError("actor_not_found")
    actor.max_consecutive_performances = payload.max_consecutive_performances
    actor.rating_level = payload.rating_level
    actor.low_rating_monthly_cap = payload.low_rating_monthly_cap
    actor.notes = payload.notes
    db.commit()
    db.refresh(actor)
    return actor


def replace_actor_capabilities(db: Session, actor_id: int, role_ids: list[int]) -> Actor:
    actor = db.get(Actor, actor_id)
    if actor is None:
        raise LookupError("actor_not_found")
    for capability in list(actor.role_capabilities):
        db.delete(capability)
    db.flush()
    for role_id in sorted(set(role_ids)):
        if db.get(Role, role_id) is None:
            raise LookupError("role_not_found")
        db.add(ActorRoleCapability(actor_id=actor_id, role_id=role_id))
    db.commit()
    db.refresh(actor)
    return actor


def list_leave_requests(db: Session, status: LeaveStatus | None = None) -> list[LeaveRequest]:
    statement = (
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.actor))
        .order_by(LeaveRequest.leave_date)
    )
    if status is not None:
        statement = statement.where(LeaveRequest.status == status)
    return list(db.scalars(statement))


def review_leave_request(db: Session, leave_id: int, status: LeaveStatus) -> LeaveRequest:
    if status not in {LeaveStatus.APPROVED, LeaveStatus.REJECTED, LeaveStatus.LOCKED}:
        raise ValueError("review_status_must_be_final")
    leave = db.get(LeaveRequest, leave_id)
    if leave is None:
        raise LookupError("leave_not_found")
    leave.status = status
    db.commit()
    db.refresh(leave)
    return leave
