from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import (
    Actor,
    LeaveRequest,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    Designation,
    ScheduleAssignment,
    ImportDraftItem,
)
from app.models.enums import LeaveStatus
from app.schemas.admin import (
    ActorCreate,
    ActorRead,
    ActorUpdate,
    CapabilityUpdate,
    DashboardRead,
    LeaveRead,
    LeaveReviewInput,
    MonthlyCalendarReplace,
    MonthlyPlanRequest,
    PerformanceRead,
    PerformanceCreate,
    PerformanceUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TheaterCreate,
    TheaterRead,
    TheaterUpdate,
    TheaterSlotCreate,
    TheaterSlotRead,
    TheaterSlotUpdate,
    WeeklyTemplateUpdate,
)
from app.services.admin_data import (
    create_actor,
    create_role,
    create_theater,
    create_theater_slot,
    delete_role,
    delete_theater,
    delete_theater_slot,
    get_weekly_template,
    list_theater_slots,
    list_actors,
    list_leave_requests,
    list_roles,
    list_theaters,
    replace_actor_capabilities,
    review_leave_request,
    replace_weekly_template,
    ReferenceConflict,
    set_role_active,
    set_theater_active,
    set_theater_slot_active,
    update_actor,
    update_role,
    update_theater,
    update_theater_slot,
)
from app.services.monthly_plan import (
    MonthlyPlanConflict,
    generate_monthly_plan,
    list_month_performances,
    replace_monthly_plan,
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
    include_inactive: bool = False,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Theater]:
    return list_theaters(db, include_inactive)


@router.post("/theaters", response_model=TheaterRead)
def post_theater(
    payload: TheaterCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Theater:
    return _write(lambda: create_theater(db, payload), db)


@router.patch("/theaters/{theater_id}", response_model=TheaterRead)
def patch_theater(
    theater_id: int,
    payload: TheaterUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: update_theater(db, theater_id, payload), db)


@router.delete("/theaters/{theater_id}", status_code=204)
def remove_theater(
    theater_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    _write(lambda: delete_theater(db, theater_id), db)
    return Response(status_code=204)


@router.post("/theaters/{theater_id}/archive", response_model=TheaterRead)
def archive_theater(
    theater_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_theater_active(db, theater_id, False), db)


@router.post("/theaters/{theater_id}/restore", response_model=TheaterRead)
def restore_theater(
    theater_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_theater_active(db, theater_id, True), db)


@router.get("/theaters/{theater_id}/slots", response_model=list[TheaterSlotRead])
def get_slots(
    theater_id: int,
    include_inactive: bool = False,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: list_theater_slots(db, theater_id, include_inactive), db)


@router.post("/theaters/{theater_id}/slots", response_model=TheaterSlotRead)
def post_slot(
    theater_id: int,
    payload: TheaterSlotCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: create_theater_slot(db, theater_id, payload), db)


@router.patch("/theater-slots/{slot_id}", response_model=TheaterSlotRead)
def patch_slot(
    slot_id: int,
    payload: TheaterSlotUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: update_theater_slot(db, slot_id, payload), db)


@router.delete("/theater-slots/{slot_id}", status_code=204)
def remove_slot(
    slot_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    _write(lambda: delete_theater_slot(db, slot_id), db)
    return Response(status_code=204)


@router.post("/theater-slots/{slot_id}/archive", response_model=TheaterSlotRead)
def archive_slot(
    slot_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_theater_slot_active(db, slot_id, False), db)


@router.post("/theater-slots/{slot_id}/restore", response_model=TheaterSlotRead)
def restore_slot(
    slot_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_theater_slot_active(db, slot_id, True), db)


@router.get("/theaters/{theater_id}/weekly-template")
def get_template(
    theater_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: get_weekly_template(db, theater_id), db)


@router.put("/theaters/{theater_id}/weekly-template")
def put_template(
    theater_id: int,
    payload: WeeklyTemplateUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: replace_weekly_template(db, theater_id, payload.template), db)


@router.get("/roles", response_model=list[RoleRead])
def get_roles(
    theater_id: int | None = None,
    include_inactive: bool = False,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Role]:
    return list_roles(db, theater_id, include_inactive)


@router.post("/roles", response_model=RoleRead)
def post_role(
    payload: RoleCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Role:
    return _write(lambda: create_role(db, payload), db)


@router.patch("/roles/{role_id}", response_model=RoleRead)
def patch_role(
    role_id: int,
    payload: RoleUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _write(lambda: update_role(db, role_id, payload), db)


@router.delete("/roles/{role_id}", status_code=204)
def remove_role(
    role_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    _write(lambda: delete_role(db, role_id), db)
    return Response(status_code=204)


@router.post("/roles/{role_id}/archive", response_model=RoleRead)
def archive_role(
    role_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_role_active(db, role_id, False), db)


@router.post("/roles/{role_id}/restore", response_model=RoleRead)
def restore_role(
    role_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    return _write(lambda: set_role_active(db, role_id, True), db)


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


@router.post("/monthly-plan/generate", response_model=list[PerformanceRead])
def post_monthly_plan_generate(
    payload: MonthlyPlanRequest,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    try:
        return generate_monthly_plan(
            db, payload.theater_id, payload.year, payload.month, set(payload.closed_dates)
        )
    except MonthlyPlanConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/monthly-plan", response_model=list[PerformanceRead])
def put_monthly_plan(
    payload: MonthlyCalendarReplace,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    try:
        days = {item.performance_date: item.theater_slot_ids for item in payload.days}
        return replace_monthly_plan(db, payload.theater_id, payload.year, payload.month, days)
    except MonthlyPlanConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/performances", response_model=list[PerformanceRead])
def get_performances(
    theater_id: int,
    year: int,
    month: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    return list_month_performances(db, theater_id, year, month)


@router.post("/performances", response_model=PerformanceRead)
def create_performance(
    payload: PerformanceCreate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Performance:
    slot = db.get(TheaterSlot, payload.theater_slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="theater_slot_not_found")
    if slot.theater_id != payload.theater_id or not slot.is_active:
        raise HTTPException(status_code=400, detail="invalid_theater_slot")
    existing = (
        db.query(Performance)
        .filter(
            Performance.theater_id == payload.theater_id,
            Performance.performance_date == payload.performance_date,
            Performance.theater_slot_id == payload.theater_slot_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="performance_already_exists")

    perf = Performance(
        theater_id=payload.theater_id,
        theater_slot_id=slot.id,
        performance_date=payload.performance_date,
        slot_name_snapshot=slot.name,
        start_time_snapshot=slot.start_time,
        status="draft",
    )
    db.add(perf)
    db.commit()
    db.refresh(perf)
    return perf


@router.patch("/performances/{performance_id}", response_model=PerformanceRead)
def update_performance(
    performance_id: int,
    payload: PerformanceUpdate,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    performance = db.get(Performance, performance_id)
    if performance is None:
        raise HTTPException(status_code=404, detail="performance_not_found")
    slot = db.get(TheaterSlot, payload.theater_slot_id or performance.theater_slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="theater_slot_not_found")
    if slot.theater_id != performance.theater_id or not slot.is_active:
        raise HTTPException(status_code=400, detail="invalid_theater_slot")
    performance.theater_slot_id = slot.id
    if payload.performance_date is not None:
        performance.performance_date = payload.performance_date
    performance.slot_name_snapshot = slot.name
    performance.start_time_snapshot = slot.start_time
    try:
        db.commit()
        db.refresh(performance)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="performance_already_exists") from exc
    return performance


@router.delete("/performances/{performance_id}")
def delete_performance(
    performance_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    perf = db.query(Performance).filter(Performance.id == performance_id).first()
    if not perf:
        raise HTTPException(status_code=404, detail="performance_not_found")

    has_designation = (
        db.query(Designation).filter(Designation.target_performance_id == performance_id).first()
    )
    has_assignment = (
        db.query(ScheduleAssignment)
        .filter(ScheduleAssignment.performance_id == performance_id)
        .first()
    )
    has_draft = (
        db.query(ImportDraftItem)
        .filter(ImportDraftItem.target_performance_id == performance_id)
        .first()
    )
    if has_designation or has_assignment or has_draft:
        raise HTTPException(status_code=409, detail="performance_has_referenced_records")

    db.delete(perf)
    db.commit()
    return {"status": "ok"}


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


def _write(operation, db: Session):
    try:
        return operation()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReferenceConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate_configuration") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
