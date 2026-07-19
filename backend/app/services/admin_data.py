from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Designation,
    ImportDraftItem,
    LeaveRequest,
    Performance,
    Role,
    ScheduleAssignment,
    Theater,
    TheaterSlot,
    TheaterWeeklyTemplateEntry,
    Wish,
)
from app.models.enums import LeaveStatus
from app.schemas.admin import (
    ActorCreate,
    ActorUpdate,
    RoleCreate,
    RoleUpdate,
    TheaterCreate,
    TheaterSlotCreate,
    TheaterSlotUpdate,
    TheaterUpdate,
)


class ReferenceConflict(Exception):
    pass


def create_theater(db: Session, payload: TheaterCreate) -> Theater:
    theater = Theater(name=payload.name)
    db.add(theater)
    db.commit()
    db.refresh(theater)
    return theater


def list_theaters(db: Session, include_inactive: bool = False) -> list[Theater]:
    statement = select(Theater).order_by(Theater.id)
    if not include_inactive:
        statement = statement.where(Theater.is_active.is_(True))
    return list(db.scalars(statement))


def update_theater(db: Session, theater_id: int, payload: TheaterUpdate) -> Theater:
    theater = _get_theater(db, theater_id)
    theater.name = payload.name
    db.commit()
    db.refresh(theater)
    return theater


def set_theater_active(db: Session, theater_id: int, active: bool) -> Theater:
    theater = _get_theater(db, theater_id)
    theater.is_active = active
    db.commit()
    db.refresh(theater)
    return theater


def delete_theater(db: Session, theater_id: int) -> None:
    theater = _get_theater(db, theater_id)
    if (
        theater.slots
        or db.scalar(select(Role.id).where(Role.theater_id == theater_id).limit(1))
        or db.scalar(select(Performance.id).where(Performance.theater_id == theater_id).limit(1))
    ):
        raise ReferenceConflict("theater_referenced")
    db.delete(theater)
    db.commit()


def create_theater_slot(db: Session, theater_id: int, payload: TheaterSlotCreate) -> TheaterSlot:
    theater = _get_active_theater(db, theater_id)
    slot = TheaterSlot(theater_id=theater.id, **payload.model_dump())
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def list_theater_slots(
    db: Session, theater_id: int, include_inactive: bool = False
) -> list[TheaterSlot]:
    _get_theater(db, theater_id)
    statement = select(TheaterSlot).where(TheaterSlot.theater_id == theater_id)
    if not include_inactive:
        statement = statement.where(TheaterSlot.is_active.is_(True))
    return list(
        db.scalars(
            statement.order_by(TheaterSlot.sort_order, TheaterSlot.start_time, TheaterSlot.id)
        )
    )


def update_theater_slot(db: Session, slot_id: int, payload: TheaterSlotUpdate) -> TheaterSlot:
    slot = _get_slot(db, slot_id)
    for key, value in payload.model_dump().items():
        setattr(slot, key, value)
    db.commit()
    db.refresh(slot)
    return slot


def set_theater_slot_active(db: Session, slot_id: int, active: bool) -> TheaterSlot:
    slot = _get_slot(db, slot_id)
    slot.is_active = active
    db.commit()
    db.refresh(slot)
    return slot


def delete_theater_slot(db: Session, slot_id: int) -> None:
    slot = _get_slot(db, slot_id)
    if db.scalar(
        select(TheaterWeeklyTemplateEntry.id)
        .where(TheaterWeeklyTemplateEntry.theater_slot_id == slot_id)
        .limit(1)
    ) or db.scalar(select(Performance.id).where(Performance.theater_slot_id == slot_id).limit(1)):
        raise ReferenceConflict("theater_slot_referenced")
    db.delete(slot)
    db.commit()


def get_weekly_template(db: Session, theater_id: int) -> dict[str, list[int]]:
    _get_theater(db, theater_id)
    result: dict[str, list[int]] = {}
    entries = db.scalars(
        select(TheaterWeeklyTemplateEntry)
        .where(TheaterWeeklyTemplateEntry.theater_id == theater_id)
        .order_by(TheaterWeeklyTemplateEntry.id)
    )
    for entry in entries:
        result.setdefault(entry.weekday, []).append(entry.theater_slot_id)
    return result


def replace_weekly_template(
    db: Session, theater_id: int, template: dict[str, list[int]]
) -> dict[str, list[int]]:
    _get_active_theater(db, theater_id)
    ids = {slot_id for slot_ids in template.values() for slot_id in slot_ids}
    slots = list(db.scalars(select(TheaterSlot).where(TheaterSlot.id.in_(ids)))) if ids else []
    if len(slots) != len(ids):
        raise LookupError("theater_slot_not_found")
    if any(slot.theater_id != theater_id for slot in slots):
        raise ValueError("slot_belongs_to_other_theater")
    if any(not slot.is_active for slot in slots):
        raise ValueError("theater_slot_inactive")
    db.execute(
        delete(TheaterWeeklyTemplateEntry).where(
            TheaterWeeklyTemplateEntry.theater_id == theater_id
        )
    )
    for weekday, slot_ids in template.items():
        for slot_id in slot_ids:
            db.add(
                TheaterWeeklyTemplateEntry(
                    theater_id=theater_id, weekday=weekday, theater_slot_id=slot_id
                )
            )
    db.commit()
    return get_weekly_template(db, theater_id)


def create_role(db: Session, payload: RoleCreate) -> Role:
    _get_active_theater(db, payload.theater_id)
    role = Role(**payload.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def list_roles(
    db: Session, theater_id: int | None = None, include_inactive: bool = False
) -> list[Role]:
    statement = select(Role).order_by(Role.id)
    if theater_id is not None:
        statement = statement.where(Role.theater_id == theater_id)
    if not include_inactive:
        statement = statement.where(Role.is_active.is_(True))
    return list(db.scalars(statement))


def update_role(db: Session, role_id: int, payload: RoleUpdate) -> Role:
    role = _get_role(db, role_id)
    role.name = payload.name
    role.group_name = payload.group_name
    db.commit()
    db.refresh(role)
    return role


def set_role_active(db: Session, role_id: int, active: bool) -> Role:
    role = _get_role(db, role_id)
    role.is_active = active
    db.commit()
    db.refresh(role)
    return role


def delete_role(db: Session, role_id: int) -> None:
    role = _get_role(db, role_id)
    checks = (ActorRoleCapability, Designation, Wish, ImportDraftItem, ScheduleAssignment)
    if any(
        db.scalar(select(model.id).where(model.role_id == role_id).limit(1)) for model in checks
    ):
        raise ReferenceConflict("role_referenced")
    db.delete(role)
    db.commit()


def _get_theater(db: Session, theater_id: int) -> Theater:
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise LookupError("theater_not_found")
    return theater


def _get_active_theater(db: Session, theater_id: int) -> Theater:
    theater = _get_theater(db, theater_id)
    if not theater.is_active:
        raise ValueError("theater_inactive")
    return theater


def _get_slot(db: Session, slot_id: int) -> TheaterSlot:
    slot = db.get(TheaterSlot, slot_id)
    if slot is None:
        raise LookupError("theater_slot_not_found")
    return slot


def _get_role(db: Session, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise LookupError("role_not_found")
    return role


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
    statement = (
        select(Actor)
        .options(selectinload(Actor.role_capabilities), selectinload(Actor.theater_memberships))
        .order_by(Actor.id)
    )
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
    unique_role_ids = sorted(set(role_ids))
    roles = [db.get(Role, role_id) for role_id in unique_role_ids]
    if any(role is None for role in roles):
        raise LookupError("role_not_found")
    if any(not role.is_active for role in roles if role is not None):
        raise ValueError("role_inactive")
    for capability in list(actor.role_capabilities):
        db.delete(capability)
    db.flush()
    for role_id in unique_role_ids:
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
