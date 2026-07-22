from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, require_super_admin
from app.services.admin_scope import AdminScope
from app.models.entities import (
    Actor,
    LeaveRequest,
    LeaveApplication,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    Designation,
    ScheduleAssignment,
    ImportDraftItem,
    SmsDelivery,
)
from app.models.enums import LeaveStatus
from app.schemas.admin import (
    ActorCreate,
    ActorCreateResult,
    ActorCredentialDelivery,
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
    ActorNotificationSettingsRead,
    ActorNotificationSettingsUpdate,
    TheaterActorNotificationSettings,
    SmsTestInput,
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
from app.services.actor_accounts import create_actor_account
from app.services.actor_accounts import reset_actor_password
from app.schemas.actor_workspace import ActorPasswordResetInput
from app.schemas.actor_workspace import (
    LeaveApplicationDayRead,
    LeaveApplicationRead,
    LeaveDayReviewInput,
    LeavePendingReviewInput,
)
from app.services.actor_leaves import list_leave_applications, review_leave_day, review_pending_days
from app.services.monthly_plan import (
    MonthlyPlanConflict,
    generate_monthly_plan,
    list_month_performances,
    replace_monthly_plan,
)
from app.services.sms_notifications import (
    AlibabaSmsProvider,
    get_sms_settings,
    read_sms_settings,
    update_sms_settings,
    reschedule_pending_tasks_for_theater,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/system-settings/actor-notifications",
    response_model=ActorNotificationSettingsRead,
)
def get_actor_notification_settings(
    _: AdminScope = Depends(require_super_admin), db: Session = Depends(get_db)
):
    return read_sms_settings(get_sms_settings(db))


@router.put(
    "/system-settings/actor-notifications",
    response_model=ActorNotificationSettingsRead,
)
def put_actor_notification_settings(
    payload: ActorNotificationSettingsUpdate,
    _: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        row = update_sms_settings(db, payload)
        db.commit()
        return read_sms_settings(row)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/system-settings/actor-notifications/test")
def test_actor_notification_sms(
    payload: SmsTestInput,
    _: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    row = get_sms_settings(db)
    if not row.encrypted_access_key_id or not row.encrypted_access_key_secret:
        raise HTTPException(status_code=409, detail="sms_credentials_not_configured")
    receipt = AlibabaSmsProvider(row).send(
        payload.phone_number,
        {"message": "您有新的演出通知，请登录演员工作台查看。"},
    )
    return {"ok": True, "request_id": receipt.request_id}


@router.get("/system-settings/actor-notifications/logs")
def get_actor_notification_sms_logs(
    limit: int = Query(default=50, ge=1, le=100),
    _: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(SmsDelivery).order_by(SmsDelivery.id.desc()).limit(limit)).all()
    return [
        {
            "id": row.id,
            "theater_id": row.theater_id,
            "actor_id": row.actor_id,
            "masked_phone": row.masked_phone,
            "status": row.status.value,
            "attempt_count": row.attempt_count,
            "provider_request_id": row.provider_request_id,
            "failure_reason": row.failure_reason,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get(
    "/theaters/{theater_id}/actor-notification-settings",
    response_model=TheaterActorNotificationSettings,
)
def get_theater_actor_notification_settings(
    theater_id: int,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise HTTPException(status_code=404, detail="theater_not_found")
    return TheaterActorNotificationSettings(
        reveal_days_before=theater.reveal_days_before,
        reveal_time=theater.reveal_time,
        sms_enabled=theater.actor_sms_enabled,
    )


@router.put(
    "/theaters/{theater_id}/actor-notification-settings",
    response_model=TheaterActorNotificationSettings,
)
def put_theater_actor_notification_settings(
    theater_id: int,
    payload: TheaterActorNotificationSettings,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    theater = db.get(Theater, theater_id)
    if theater is None:
        raise HTTPException(status_code=404, detail="theater_not_found")
    theater.reveal_days_before = payload.reveal_days_before
    theater.reveal_time = payload.reveal_time
    theater.actor_sms_enabled = payload.sms_enabled
    reschedule_pending_tasks_for_theater(db, theater_id, datetime.now())
    db.commit()
    return payload


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
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Theater]:
    rows = list_theaters(db, include_inactive)
    return (
        rows
        if scope.is_super_admin
        else [row for row in rows if row.id in scope.allowed_theater_ids]
    )


@router.post("/theaters", response_model=TheaterRead)
def post_theater(
    payload: TheaterCreate,
    _: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> Theater:
    return _write(lambda: create_theater(db, payload), db)


@router.patch("/theaters/{theater_id}", response_model=TheaterRead)
def patch_theater(
    theater_id: int,
    payload: TheaterUpdate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    return _write(lambda: update_theater(db, theater_id, payload), db)


@router.delete("/theaters/{theater_id}", status_code=204)
def remove_theater(
    theater_id: int, _: AdminScope = Depends(require_super_admin), db: Session = Depends(get_db)
):
    _write(lambda: delete_theater(db, theater_id), db)
    return Response(status_code=204)


@router.post("/theaters/{theater_id}/archive", response_model=TheaterRead)
def archive_theater(
    theater_id: int, scope: AdminScope = Depends(require_admin), db: Session = Depends(get_db)
):
    scope.require_theater(theater_id)
    return _write(lambda: set_theater_active(db, theater_id, False), db)


@router.post("/theaters/{theater_id}/restore", response_model=TheaterRead)
def restore_theater(
    theater_id: int, scope: AdminScope = Depends(require_admin), db: Session = Depends(get_db)
):
    scope.require_theater(theater_id)
    return _write(lambda: set_theater_active(db, theater_id, True), db)


@router.get("/theaters/{theater_id}/slots", response_model=list[TheaterSlotRead])
def get_slots(
    theater_id: int,
    include_inactive: bool = False,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    return _write(lambda: list_theater_slots(db, theater_id, include_inactive), db)


@router.post("/theaters/{theater_id}/slots", response_model=TheaterSlotRead)
def post_slot(
    theater_id: int,
    payload: TheaterSlotCreate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
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
    theater_id: int, scope: AdminScope = Depends(require_admin), db: Session = Depends(get_db)
):
    scope.require_theater(theater_id)
    return _write(lambda: get_weekly_template(db, theater_id), db)


@router.put("/theaters/{theater_id}/weekly-template")
def put_template(
    theater_id: int,
    payload: WeeklyTemplateUpdate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    scope.require_theater(theater_id)
    return _write(lambda: replace_weekly_template(db, theater_id, payload.template), db)


@router.get("/roles", response_model=list[RoleRead])
def get_roles(
    theater_id: int | None = None,
    include_inactive: bool = False,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Role]:
    if theater_id is not None:
        scope.require_theater(theater_id)
    rows = list_roles(db, theater_id, include_inactive)
    return (
        rows
        if scope.is_super_admin
        else [row for row in rows if row.theater_id in scope.allowed_theater_ids]
    )


@router.post("/roles", response_model=RoleRead)
def post_role(
    payload: RoleCreate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Role:
    scope.require_theater(payload.theater_id)
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
    scope: AdminScope = Depends(require_admin), db: Session = Depends(get_db)
) -> list[ActorRead]:
    rows = list_actors(db)
    if not scope.is_super_admin:
        rows = [
            actor
            for actor in rows
            if any(
                item.theater_id in scope.allowed_theater_ids for item in actor.theater_memberships
            )
        ]
    return [_actor_read(actor) for actor in rows]


@router.post("/actors", response_model=ActorRead | ActorCreateResult)
def post_actor(
    payload: ActorCreate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorRead | ActorCreateResult:
    for theater_id in payload.theater_ids:
        scope.require_theater(theater_id)
    if payload.entry_theater_id is not None:
        scope.require_theater(payload.entry_theater_id)
    if payload.phone_number is None:
        return _actor_read(create_actor(db, payload))
    try:
        actor, delivery = create_actor_account(db, payload)
        return ActorCreateResult(actor=_actor_read(actor), credential_delivery=delivery)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="duplicate_actor_account") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/actors/{actor_id}/reset-password", response_model=ActorCredentialDelivery)
def post_actor_password_reset(
    actor_id: int,
    payload: ActorPasswordResetInput,
    _: dict[str, object] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ActorCredentialDelivery:
    try:
        return reset_actor_password(db, actor_id, payload.entry_theater_id)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/actors/{actor_id}", response_model=ActorRead)
def patch_actor(
    actor_id: int,
    payload: ActorUpdate,
    scope: AdminScope = Depends(require_admin),
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
            )
            for day in row.days
        ],
    )


@router.get("/leave-applications", response_model=list[LeaveApplicationRead])
def get_leave_applications(
    theater_id: int | None = None,
    status: LeaveStatus | None = None,
    _: dict[str, object] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LeaveApplicationRead]:
    return [_leave_application_read(row) for row in list_leave_applications(db, theater_id, status)]


@router.post("/leave-application-days/{day_id}/review", response_model=LeaveApplicationDayRead)
def post_leave_day_review(
    day_id: int,
    payload: LeaveDayReviewInput,
    user: dict[str, object] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LeaveApplicationDayRead:
    try:
        status = LeaveStatus(payload.status)
        day = review_leave_day(db, day_id, status, payload.reason, int(user.get("user_id") or 1))
        db.commit()
        return LeaveApplicationDayRead(
            id=day.id,
            leave_date=day.leave_date,
            status=day.status.value,
            has_schedule_conflict=day.has_schedule_conflict,
            review_reason=day.review_reason,
            reviewed_at=day.reviewed_at,
            withdrawn_at=day.withdrawn_at,
        )
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/leave-applications/{application_id}/review-pending", response_model=LeaveApplicationRead
)
def post_leave_pending_review(
    application_id: int,
    payload: LeavePendingReviewInput,
    user: dict[str, object] = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LeaveApplicationRead:
    try:
        row = review_pending_days(
            db,
            application_id,
            LeaveStatus(payload.status),
            payload.reason,
            int(user.get("user_id") or 1),
        )
        db.commit()
        db.refresh(row)
        return _leave_application_read(row)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/monthly-plan/generate", response_model=list[PerformanceRead])
def post_monthly_plan_generate(
    payload: MonthlyPlanRequest,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    try:
        scope.require_theater(payload.theater_id)
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
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    try:
        scope.require_theater(payload.theater_id)
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
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Performance]:
    scope.require_theater(theater_id)
    return list_month_performances(db, theater_id, year, month)


@router.post("/performances", response_model=PerformanceRead)
def create_performance(
    payload: PerformanceCreate,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Performance:
    scope.require_theater(payload.theater_id)
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
    memberships = actor.theater_memberships
    return ActorRead(
        id=actor.id,
        display_name=actor.display_name,
        max_consecutive_performances=actor.max_consecutive_performances,
        rating_level=actor.rating_level,
        low_rating_monthly_cap=actor.low_rating_monthly_cap,
        notes=actor.notes,
        role_ids=[capability.role_id for capability in actor.role_capabilities],
        phone_number=actor.phone_number,
        theater_ids=[membership.theater_id for membership in memberships],
        entry_theater_id=next(
            (membership.theater_id for membership in memberships if membership.is_entry_theater),
            None,
        ),
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
