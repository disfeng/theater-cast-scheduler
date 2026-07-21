from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, require_super_admin
from app.models.entities import (
    AiParserSettingsAudit,
    Actor,
    BoardDraftItem,
    Designation,
    DesignationLifecycleEvent,
    DesignationVersion,
    EntitlementItem,
    EntitlementItemType,
    Performance,
    PerformanceBoard,
    PerformanceBoardRevision,
    PerformancePlayer,
    PlayerProfile,
    Role,
    User,
    Wish,
    WishVersion,
)
from app.models.enums import EntitlementItemStatus, UserRole
from urllib.parse import urlsplit
from app.models.enums import BoardChangeType, BoardValidationStatus
from app.schemas.performance_boards import (
    AiParserSettingsRead,
    AiParserSettingsUpdate,
    AiParserTestRead,
    BoardDraftItemRead,
    BoardItemPatch,
    BoardRevisionCreate,
    BoardRevisionRead,
    PerformanceBoardRead,
    DesignationActivateRequest,
    DesignationCancelRequest,
    DesignationReplaceRequest,
    DesignationEqualChoiceRequest,
    DesignationReviewRead,
    DesignationCorrectionPatch,
    ProxyDesignationVerifyRequest,
    WishCreateRequest,
    WishCancelRequest,
    WishAcceptRequest,
    WishReviewRead,
    WishUpdateRequest,
    WishCorrectionPatch,
)
from app.services.business_corrections import (
    CorrectionConflict,
    correct_designation,
    correct_wish,
    preview_designation_correction,
    preview_wish_correction,
)
from app.services.ai_parser import AiParserError, BoardParseContext, OpenAICompatibleBoardParser
from app.services.ai_settings import (
    decrypt_api_key,
    get_ai_settings,
    read_ai_settings,
    update_ai_settings,
)
from app.services.performance_boards import (
    BoardConflict,
    activate_revision,
    confirm_board_item,
    create_board_revision,
    create_board_revision_with_ai,
    reopen_board_item,
    clone_revision_for_rollback,
)
from app.services.designations import (
    DesignationConflict,
    activate_predesignation,
    cancel_designation,
    replace_predesignation,
    resolve_equal_priority,
    verify_proxy_designation,
    verify_self_designation,
)
from app.services.wishes import WishConflict, accept_wish, cancel_wish, create_wish, update_wish

router = APIRouter(prefix="/admin", tags=["admin_performance_boards"])


def _correction_preview_payload(preview) -> dict[str, object]:
    return {
        "release_item_id": preview.release_item_id,
        "reserve_item_id": preview.reserve_item_id,
        "reverse_ledger_entry_id": preview.reverse_ledger_entry_id,
        "requires_reversal": preview.requires_reversal,
        "immutable_fields": list(preview.immutable_fields),
    }


def wish_review_read(db: Session, row: Wish) -> WishReviewRead:
    snapshot = getattr(row, "_wish_api_snapshot", None)
    if snapshot is not None:
        return WishReviewRead.model_validate(snapshot)
    actor, role = db.get(Actor, row.actor_id), db.get(Role, row.role_id)
    return WishReviewRead(
        id=row.id,
        performance_id=row.performance_id,
        performance_player_id=row.performance_player_id,
        player_name=row.player_name,
        actor_id=row.actor_id,
        actor_name=actor.display_name,
        role_id=row.role_id,
        role_name=role.name,
        note=row.note,
        status=row.status or "active",
        failure_reason=row.failure_reason,
        version=row.version,
    )


@router.get("/wishes", response_model=list[WishReviewRead])
def get_wishes(
    performance_id: int | None = None,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(Wish).where(Wish.performance_id.is_not(None))
    if performance_id is not None:
        query = query.where(Wish.performance_id == performance_id)
    return [wish_review_read(db, row) for row in db.scalars(query.order_by(Wish.id.desc())).all()]


@router.post("/wishes", response_model=WishReviewRead)
def post_wish(
    payload: WishCreateRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = create_wish(db, **payload.model_dump(), operator_user_id=_operator_id(db, user))
        result = wish_review_read(db, row)
        db.commit()
        return result
    except WishConflict as exc:
        db.rollback()
        raise HTTPException(
            409 if "conflict" in str(exc) or "duplicate" in str(exc) else 422, detail=str(exc)
        ) from exc


@router.post("/wishes/{wish_id}/cancel", response_model=WishReviewRead)
def post_cancel_wish(
    wish_id: int,
    payload: WishCancelRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = cancel_wish(
            db,
            wish_id,
            payload.reason,
            _operator_id(db, user),
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
        )
        result = wish_review_read(db, row)
        db.commit()
        return result
    except WishConflict as exc:
        db.rollback()
        raise HTTPException(404 if str(exc) == "wish_not_found" else 409, detail=str(exc)) from exc


@router.patch("/wishes/{wish_id}", response_model=WishReviewRead)
def patch_wish(
    wish_id: int,
    payload: WishUpdateRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = update_wish(
            db,
            wish_id,
            payload.actor_id,
            payload.role_id,
            payload.note,
            _operator_id(db, user),
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
        )
        result = wish_review_read(db, row)
        db.commit()
        return result
    except WishConflict as exc:
        db.rollback()
        raise HTTPException(404 if str(exc) == "wish_not_found" else 409, detail=str(exc)) from exc


@router.post("/wishes/{wish_id}/accept", response_model=WishReviewRead)
def post_accept_wish(
    wish_id: int,
    payload: WishAcceptRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = accept_wish(
            db,
            wish_id,
            payload.note,
            _operator_id(db, user),
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
        )
        result = wish_review_read(db, row)
        db.commit()
        return result
    except WishConflict as exc:
        db.rollback()
        raise HTTPException(404 if str(exc) == "wish_not_found" else 409, detail=str(exc)) from exc


def designation_review_read(db: Session, row: Designation) -> DesignationReviewRead:
    snapshot = getattr(row, "_idempotency_response_snapshot", None)
    if snapshot and "id" in snapshot:
        return DesignationReviewRead.model_validate(snapshot)
    pp = (
        db.get(PerformancePlayer, row.beneficiary_performance_player_id)
        if row.beneficiary_performance_player_id
        else None
    )
    owner = db.get(PlayerProfile, row.owner_player_id) if row.owner_player_id else None
    item = db.get(EntitlementItem, row.entitlement_item_id) if row.entitlement_item_id else None
    actor, role = db.get(Actor, row.actor_id), db.get(Role, row.role_id)
    perf = db.get(Performance, row.performance_id) if row.performance_id else None
    eligible_types = list(
        db.scalars(
            select(EntitlementItemType).where(
                EntitlementItemType.theater_id == (perf.theater_id if perf else None),
                EntitlementItemType.designation_type == row.designation_type,
                EntitlementItemType.is_active.is_(True),
            )
        )
    )
    typ = item.item_type if item else max(eligible_types, key=lambda value: value.priority, default=None)
    verifier = db.get(User, row.verified_by) if row.verified_by else None
    available = []
    if row.owner_player_id and eligible_types:
        available = [
            {
                "id": candidate.id,
                "serial_number": candidate.serial_number,
                "source_label": candidate.source_label,
                "expires_at": candidate.expires_at,
                "status": candidate.status.value,
            }
            for candidate in db.scalars(
                select(EntitlementItem)
                .where(
                    EntitlementItem.owner_id == row.owner_player_id,
                    EntitlementItem.theater_id == perf.theater_id,
                    EntitlementItem.item_type_id.in_([value.id for value in eligible_types]),
                    EntitlementItem.status == EntitlementItemStatus.AVAILABLE,
                )
                .order_by(EntitlementItem.expires_at, EntitlementItem.id)
            ).all()
        ]
    conflict_row = db.scalar(
        select(Designation)
        .where(
            Designation.id != row.id,
            Designation.performance_id == row.performance_id,
            Designation.lifecycle_status == "predesignated",
            ((Designation.role_id == row.role_id) | (Designation.actor_id == row.actor_id)),
        )
        .order_by(Designation.id)
    )
    history = [
        {
            "event": event.action,
            "at": event.created_at,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "item_id": event.entitlement_item_id,
            "conflict_designation_id": event.conflict_designation_id,
            "note": event.note,
            "operator_user_id": event.operator_user_id,
        }
        for event in db.scalars(
            select(DesignationLifecycleEvent)
            .where(DesignationLifecycleEvent.designation_id == row.id)
            .order_by(DesignationLifecycleEvent.created_at, DesignationLifecycleEvent.id)
        ).all()
    ]
    conflict_item = (
        db.get(EntitlementItem, conflict_row.entitlement_item_id)
        if conflict_row and conflict_row.entitlement_item_id
        else None
    )
    conflict_type = conflict_item.item_type if conflict_item else None
    comparison = None
    if conflict_type and typ:
        comparison = (
            "higher"
            if typ.priority > conflict_type.priority
            else "lower"
            if typ.priority < conflict_type.priority
            else "equal"
        )
    outcome = (
        "replacement_confirmation_required"
        if comparison == "higher"
        else "pending_lower_priority"
        if comparison == "lower"
        else "manual_choice_required"
        if comparison == "equal"
        else "active"
        if row.lifecycle_status == "predesignated"
        else row.lifecycle_status or "draft"
    )
    action = (
        "confirm_replace"
        if comparison == "higher"
        else "wait"
        if comparison == "lower"
        else "choose_manually"
        if comparison == "equal"
        else "none"
    )
    return DesignationReviewRead(
        id=row.id,
        version=row.version,
        usage_type=row.usage_type,
        lifecycle_status=row.lifecycle_status,
        verification_status=row.verification_status,
        failure_reason=row.failure_reason,
        verification_note=row.verification_note,
        verified_at=row.verified_at,
        verified_by=row.verified_by,
        verifier_name=verifier.email if verifier else None,
        performance_id=row.performance_id,
        performance_label=f"{perf.performance_date} {perf.slot_name_snapshot}" if perf else None,
        beneficiary_performance_player_id=row.beneficiary_performance_player_id,
        beneficiary_player_id=pp.player_profile_id if pp else None,
        beneficiary_name=pp.player_name_snapshot if pp else row.player_name,
        owner_player_id=row.owner_player_id,
        owner_name=owner.display_name if owner else None,
        designation_type=row.designation_type.value,
        priority=typ.priority if typ else 999,
        actor_id=row.actor_id,
        actor_name=actor.display_name if actor else str(row.actor_id),
        role_id=row.role_id,
        role_name=role.name if role else str(row.role_id),
        entitlement_item_id=row.entitlement_item_id,
        entitlement_serial=item.serial_number if item else None,
        entitlement_source=item.source_label if item else None,
        entitlement_expiry=item.expires_at if item else None,
        available_items=available,
        conflict={
            "id": conflict_row.id,
            "designation_type": conflict_row.designation_type.value,
            "version": conflict_row.version,
            "priority": conflict_type.priority,
        }
        if conflict_row and conflict_type
        else None,
        comparison=comparison,
        outcome=outcome,
        action=action,
        status_history=history,
    )


def _finalize_designation(
    db: Session, row: Designation, action: str, key: str
) -> DesignationReviewRead:
    response = designation_review_read(db, row)
    event = db.scalar(
        select(DesignationLifecycleEvent).where(
            DesignationLifecycleEvent.designation_id == row.id,
            DesignationLifecycleEvent.action == action,
            DesignationLifecycleEvent.idempotency_key == key,
        )
    )
    if event and not getattr(row, "_idempotency_response_snapshot", None):
        event.result_snapshot = response.model_dump(mode="json")
    db.commit()
    return response


def _designation_error(exc: DesignationConflict) -> HTTPException:
    return HTTPException(
        status_code=404 if str(exc).endswith("not_found") else 409, detail=str(exc)
    )


@router.get("/designations", response_model=list[DesignationReviewRead])
def get_designations(_: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)):
    return [
        designation_review_read(db, row)
        for row in db.scalars(
            select(Designation)
            .where(Designation.performance_id.is_not(None))
            .order_by(Designation.submitted_at.desc(), Designation.id.desc())
        ).all()
    ]


@router.post("/designations/{designation_id}/verify-proxy", response_model=DesignationReviewRead)
def post_verify_proxy(
    designation_id: int,
    payload: ProxyDesignationVerifyRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = verify_proxy_designation(
            db,
            designation_id,
            payload.owner_player_id,
            payload.item_id,
            payload.note,
            _operator_id(db, user),
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
        )
        return _finalize_designation(db, row, "verify_proxy", payload.idempotency_key)
    except DesignationConflict as exc:
        raise _designation_error(exc) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/designations/{designation_id}/activate", response_model=DesignationReviewRead)
def post_activate_designation(
    designation_id: int,
    payload: DesignationActivateRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = db.get(Designation, designation_id)
        if row is None:
            raise DesignationConflict("designation_not_found")
        result = (
            verify_self_designation(
                db,
                designation_id,
                payload.item_id,
                _operator_id(db, user),
                expected_version=payload.expected_version,
                idempotency_key=payload.idempotency_key,
            )
            if payload.item_id is not None and row.usage_type != "proxy"
            else activate_predesignation(
                db,
                designation_id,
                _operator_id(db, user),
                expected_version=payload.expected_version,
                idempotency_key=payload.idempotency_key,
            )
        )
        return _finalize_designation(
            db,
            result,
            "verify_self"
            if payload.item_id is not None and row.usage_type != "proxy"
            else "activate",
            payload.idempotency_key,
        )
    except DesignationConflict as exc:
        raise _designation_error(exc) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/designations/{designation_id}/replace", response_model=DesignationReviewRead)
def post_replace_designation(
    designation_id: int,
    payload: DesignationReplaceRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(status_code=409, detail="designation_replacement_confirmation_required")
    try:
        row = replace_predesignation(
            db,
            designation_id,
            payload.replaced_id,
            payload.expected_versions,
            _operator_id(db, user),
            idempotency_key=payload.idempotency_key,
        )
        return _finalize_designation(db, row, "replace", payload.idempotency_key)
    except DesignationConflict as exc:
        raise _designation_error(exc) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/designations/{designation_id}/cancel", response_model=DesignationReviewRead)
def post_cancel_designation(
    designation_id: int,
    payload: DesignationCancelRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = cancel_designation(
            db,
            designation_id,
            payload.reason,
            _operator_id(db, user),
            expected_version=payload.expected_version,
            idempotency_key=payload.idempotency_key,
        )
        return _finalize_designation(db, row, "cancel", payload.idempotency_key)
    except DesignationConflict as exc:
        raise _designation_error(exc) from exc
    except Exception:
        db.rollback()
        raise


@router.post("/designations/{designation_id}/resolve-equal", response_model=DesignationReviewRead)
def post_resolve_equal(
    designation_id: int,
    payload: DesignationEqualChoiceRequest,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(409, detail="designation_manual_confirmation_required")
    try:
        row = resolve_equal_priority(
            db,
            designation_id,
            payload.occupied_id,
            payload.decision,
            payload.expected_versions,
            _operator_id(db, user),
            idempotency_key=payload.idempotency_key,
        )
        return _finalize_designation(db, row, "resolve_equal", payload.idempotency_key)
    except DesignationConflict as exc:
        db.rollback()
        raise _designation_error(exc) from exc


@router.get("/system-settings/ai-parser", response_model=AiParserSettingsRead)
def get_ai_parser_settings(
    _: dict[str, str] = Depends(require_super_admin), db: Session = Depends(get_db)
):
    return read_ai_settings(get_ai_settings(db))


@router.put("/system-settings/ai-parser", response_model=AiParserSettingsRead)
def put_ai_parser_settings(
    payload: AiParserSettingsUpdate,
    user: dict[str, str] = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    try:
        before = read_ai_settings(get_ai_settings(db))
        row = update_ai_settings(db, payload)
        changed = [
            name
            for name in ("enabled", "endpoint", "model_name", "timeout_seconds")
            if getattr(before, name) != getattr(payload, name)
        ]
        db.add(
            AiParserSettingsAudit(
                actor_user_id=_operator_id(db, user),
                action="settings_update",
                changed_fields=changed,
                key_replaced=payload.api_key is not None,
                provider_host=urlsplit(row.endpoint).hostname,
                model_name=row.model_name,
                outcome="success",
            )
        )
        db.commit()
        return read_ai_settings(row)
    except ValueError as exc:
        db.rollback()
        db.add(
            AiParserSettingsAudit(
                actor_user_id=_operator_id(db, user),
                action="settings_update",
                changed_fields=None,
                key_replaced=payload.api_key is not None,
                provider_host=urlsplit(payload.endpoint).hostname,
                model_name=payload.model_name,
                outcome="rejected",
            )
        )
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/system-settings/ai-parser/test", response_model=AiParserTestRead)
async def test_ai_parser_connection(
    user: dict[str, str] = Depends(require_super_admin), db: Session = Depends(get_db)
):
    row = get_ai_settings(db)
    try:
        key = decrypt_api_key(row)
        if not key:
            raise ValueError("api_key_unavailable")
        parser = OpenAICompatibleBoardParser(
            endpoint=row.endpoint,
            api_key=key,
            model=row.model_name,
            timeout_seconds=min(row.timeout_seconds, 10),
        )
        await parser.parse(
            "Return an empty performance board.", BoardParseContext(performance_id=0)
        )
        row.last_test_ok, row.last_test_message = True, "connection_ok"
    except (AiParserError, ValueError):
        row.last_test_ok, row.last_test_message = False, "connection_failed"
    row.last_tested_at = datetime.utcnow()
    db.add(
        AiParserSettingsAudit(
            actor_user_id=_operator_id(db, user),
            action="connection_test",
            changed_fields=None,
            key_replaced=False,
            provider_host=urlsplit(row.endpoint).hostname,
            model_name=row.model_name,
            outcome="success" if row.last_test_ok else "failure",
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="ai_settings_audit_persistence_failed")
    return AiParserTestRead(ok=bool(row.last_test_ok), message=row.last_test_message)


def _operator_id(db: Session, user: dict[str, str]) -> int:
    operator = db.scalar(select(User).where(User.email == user["sub"]))
    if operator is None:
        operator = User(
            email=user["sub"],
            password_hash="external-demo-auth",
            role=UserRole.ADMIN,
        )
        db.add(operator)
        db.flush()
    return operator.id


def _optional_operator_id(db: Session, user: dict[str, str]) -> int | None:
    return _operator_id(db, user)


@router.get("/performances/{performance_id}/board", response_model=PerformanceBoardRead)
def get_board(
    performance_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    board = db.scalar(
        select(PerformanceBoard).where(PerformanceBoard.performance_id == performance_id)
    )
    if board is None:
        raise HTTPException(status_code=404, detail="board_not_found")
    return board


@router.post("/performances/{performance_id}/board/revisions", response_model=BoardRevisionRead)
async def post_revision(
    performance_id: int,
    payload: BoardRevisionCreate,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        operator_id = _optional_operator_id(db, user)
        if not payload.parse_with_ai:
            return create_board_revision(db, performance_id, payload.raw_text, operator_id)
        return await create_board_revision_with_ai(db, performance_id, payload.raw_text, operator_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BoardConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/board-revisions/{revision_id}", response_model=BoardRevisionRead)
def get_revision(
    revision_id: int, _: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    revision = db.get(PerformanceBoardRevision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="board_revision_not_found")
    return revision


@router.patch("/board-draft-items/{item_id}", response_model=BoardDraftItemRead)
def patch_item(
    item_id: int,
    payload: BoardItemPatch,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(BoardDraftItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="board_item_not_found")
    if item.confirmed_at is not None:
        raise HTTPException(status_code=409, detail="board_item_already_confirmed")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/board-draft-items/{item_id}/confirm", response_model=BoardDraftItemRead)
def post_confirm_item(
    item_id: int,
    payload: BoardItemPatch,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        item = confirm_board_item(db, item_id, payload, _operator_id(db, user))
        db.commit()
        db.refresh(item)
        return item
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BoardConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/board-draft-items/{item_id}/reopen", response_model=BoardDraftItemRead)
def post_reopen_item(
    item_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        item = reopen_board_item(db, item_id)
        db.commit()
        db.refresh(item)
        return item
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BoardConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/board-revisions/{revision_id}/confirm-valid", response_model=BoardRevisionRead)
def post_confirm_valid(
    revision_id: int, user: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    revision = db.get(PerformanceBoardRevision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="board_revision_not_found")
    operator_id = _operator_id(db, user)
    try:
        for item in list(revision.draft_items):
            if (
                item.validation_status == BoardValidationStatus.VALID
                and item.change_type != BoardChangeType.REMOVED
                and item.confirmed_at is None
            ):
                confirm_board_item(db, item.id, BoardItemPatch(), operator_id)
        db.commit()
        db.refresh(revision)
        return revision
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BoardConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/board-revisions/{revision_id}/activate", response_model=BoardRevisionRead)
def post_activate(
    revision_id: int, user: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        return activate_revision(db, revision_id, _operator_id(db, user))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BoardConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/board-revisions/{revision_id}/rollback", response_model=BoardRevisionRead)
def post_rollback(
    revision_id: int, user: dict[str, str] = Depends(require_admin), db: Session = Depends(get_db)
):
    revision = db.get(PerformanceBoardRevision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="board_revision_not_found")
    try:
        return clone_revision_for_rollback(db, revision_id, _operator_id(db, user))
    except BoardConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/designations/{designation_id}/correction-preview")
def post_designation_correction_preview(
    designation_id: int,
    payload: DesignationCorrectionPatch,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return _correction_preview_payload(
            preview_designation_correction(db, designation_id, payload)
        )
    except CorrectionConflict as exc:
        raise HTTPException(404 if str(exc) == "designation_not_found" else 409, detail=str(exc))


@router.post("/designations/{designation_id}/corrections", response_model=DesignationReviewRead)
def post_designation_correction(
    designation_id: int,
    payload: DesignationCorrectionPatch,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = correct_designation(db, designation_id, payload, _operator_id(db, user))
        result = designation_review_read(db, row)
        db.commit()
        return result
    except CorrectionConflict as exc:
        db.rollback()
        raise HTTPException(404 if str(exc) == "designation_not_found" else 409, detail=str(exc))


@router.get("/designations/{designation_id}/versions")
def get_designation_versions(
    designation_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Designation, designation_id) is None:
        raise HTTPException(404, detail="designation_not_found")
    return [
        {
            "id": row.id,
            "version_number": row.version_number,
            "player_name": row.player_name,
            "actor_id": row.actor_id,
            "role_id": row.role_id,
            "usage_type": row.usage_type,
            "entitlement_item_id": row.entitlement_item_id,
            "note": row.note,
            "correction_reason": row.correction_reason,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
        for row in db.scalars(
            select(DesignationVersion)
            .where(DesignationVersion.designation_id == designation_id)
            .order_by(DesignationVersion.version_number.desc())
        )
    ]


@router.post("/wishes/{wish_id}/correction-preview")
def post_wish_correction_preview(
    wish_id: int,
    payload: WishCorrectionPatch,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return _correction_preview_payload(preview_wish_correction(db, wish_id, payload))
    except CorrectionConflict as exc:
        raise HTTPException(404 if str(exc) == "wish_not_found" else 409, detail=str(exc))


@router.post("/wishes/{wish_id}/corrections", response_model=WishReviewRead)
def post_wish_correction(
    wish_id: int,
    payload: WishCorrectionPatch,
    user: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        row = correct_wish(db, wish_id, payload, _operator_id(db, user))
        result = wish_review_read(db, row)
        db.commit()
        return result
    except CorrectionConflict as exc:
        db.rollback()
        raise HTTPException(404 if str(exc) == "wish_not_found" else 409, detail=str(exc))


@router.get("/wishes/{wish_id}/versions")
def get_wish_versions(
    wish_id: int,
    _: dict[str, str] = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Wish, wish_id) is None:
        raise HTTPException(404, detail="wish_not_found")
    return [
        {
            "id": row.id,
            "version_number": row.version_number,
            "player_name": row.player_name,
            "actor_id": row.actor_id,
            "role_id": row.role_id,
            "note": row.note,
            "correction_reason": row.correction_reason,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
        for row in db.scalars(
            select(WishVersion)
            .where(WishVersion.wish_id == wish_id)
            .order_by(WishVersion.version_number.desc())
        )
    ]
