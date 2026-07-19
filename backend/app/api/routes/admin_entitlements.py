from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_admin
from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItem,
    EntitlementItemType,
    PlayerAlias,
    PlayerProfile,
    Theater,
    User,
)
from app.models.enums import (
    DesignationType,
    EntitlementEventType,
    EntitlementItemCategory,
    GrantBatchStatus,
    PlayerStatus,
)
from app.schemas.entitlements import (
    AdjustmentRequest,
    AliasCreate,
    BulkPlayerMatchRead,
    BulkPlayerMatchRequest,
    EntitlementItemRead,
    ExtensionRequest,
    GrantBatchCreate,
    GrantBatchRead,
    ItemTypeCreate,
    ItemTypeRead,
    ItemTypeUpdate,
    ManualConsumeRead,
    ManualConsumeRequest,
    EntitlementLedgerPageRead,
    PlayerCreate,
    PlayerInventoryRead,
    PlayerMatchResult,
    PlayerMergeRequest,
    PlayerRead,
    PlayerUpdate,
    ReasonRequest,
)
from app.services.entitlements import (
    EntitlementConflict,
    EntitlementNotFound,
    adjust_item,
    confirm_grant_batch,
    create_or_match_player,
    entitlement_reconciliation,
    extend_item,
    inventory_for_player,
    list_entitlement_ledger,
    manual_consume,
    normalize_player_name,
    reconciliation_drill,
    preview_manual_consumption,
    restore_item,
    void_item,
)

router = APIRouter(prefix="/admin", tags=["admin_entitlements"])


@router.get("/entitlements/reconciliation")
def reconciliation(
    expiry: str | None = None, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    allowed = {None, "expired", "expires_within_7_days", "expires_within_30_days"}
    if expiry not in allowed:
        raise HTTPException(422, detail="entitlement_expiry_filter_invalid")
    return entitlement_reconciliation(db, expiry=expiry)


@router.get("/entitlements/reconciliation/drill")
def reconciliation_details(
    kind: str = Query(pattern="^(items|ledgers|anomalies)$"),
    expiry: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    cursor: int = Query(0, ge=0),
    item_type: str | None = None,
    source_month: date | None = None,
    source_label: str | None = None,
    player_id: int | None = None,
    status: str | None = None,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    allowed = {None, "expired", "expires_within_7_days", "expires_within_30_days"}
    if expiry not in allowed:
        raise HTTPException(422, detail="entitlement_expiry_filter_invalid")
    return reconciliation_drill(
        db,
        kind=kind,
        expiry=expiry,
        limit=limit,
        cursor=cursor,
        filters={
            "item_type": item_type,
            "source_month": source_month,
            "source_label": source_label,
            "player_id": player_id,
            "status": status,
        },
    )


def _operator(user: dict[str, str], db: Session) -> int:
    operator = db.scalar(select(User).where(User.email == user["sub"]))
    if operator is None:
        raise HTTPException(401, detail="operator_user_not_found")
    return operator.id


def _raise(exc: Exception):
    if isinstance(exc, EntitlementNotFound):
        raise HTTPException(404, detail=str(exc)) from exc
    if isinstance(exc, EntitlementConflict):
        raise HTTPException(409, detail=str(exc)) from exc
    raise exc


@router.get("/player-profiles", response_model=list[PlayerRead])
def search_players(q: str = "", _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    normalized = normalize_player_name(q)
    stmt = select(PlayerProfile).outerjoin(PlayerAlias).distinct().order_by(PlayerProfile.id)
    if normalized:
        stmt = stmt.where(
            or_(
                PlayerProfile.normalized_name.contains(normalized),
                PlayerAlias.normalized_alias.contains(normalized),
            )
        )
    return list(db.scalars(stmt).all())


@router.post(
    "/theaters/{theater_id}/entitlement-grant-player-matches",
    response_model=list[BulkPlayerMatchRead],
)
def match_grant_players(
    theater_id: int,
    payload: BulkPlayerMatchRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    rows: list[BulkPlayerMatchRead] = []
    for name in payload.names:
        match = create_or_match_player(db, name)
        rows.append(BulkPlayerMatchRead(raw_name=name, **match.model_dump()))
    return rows


@router.post("/player-profiles", response_model=PlayerMatchResult)
def create_player(
    payload: PlayerCreate, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        result = create_or_match_player(db, payload.display_name)
        if len(result.candidates) > 1:
            raise HTTPException(409, detail="player_match_ambiguous")
        return result
    except EntitlementConflict as exc:
        _raise(exc)


@router.patch("/player-profiles/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: int,
    payload: PlayerUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.scalar(select(PlayerProfile).where(PlayerProfile.id == player_id).with_for_update())
    if player is None:
        raise HTTPException(404, detail="player_not_found")
    if player.status == PlayerStatus.MERGED:
        raise HTTPException(409, detail="player_merged")
    values = payload.model_dump(exclude_unset=True)
    requested_status = values.get("status")
    if requested_status is not None:
        if requested_status != PlayerStatus.ACTIVE or player.status != PlayerStatus.PROVISIONAL:
            raise HTTPException(409, detail="player_status_transition_invalid")
    if "display_name" in values:
        values["normalized_name"] = normalize_player_name(values["display_name"])
        primary_claim = db.scalar(
            select(PlayerAlias)
            .where(PlayerAlias.player_id == player.id, PlayerAlias.is_primary.is_(True))
            .with_for_update()
        )
        if primary_claim is None:
            primary_claim = PlayerAlias(player_id=player.id, is_primary=True)
            db.add(primary_claim)
        primary_claim.alias = values["display_name"]
        primary_claim.normalized_alias = values["normalized_name"]
    for key, value in values.items():
        setattr(player, key, value)
    try:
        db.commit()
        db.refresh(player)
        return player
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_name_already_exists") from exc


@router.post("/player-profiles/{player_id}/aliases", response_model=PlayerRead)
def add_alias(
    player_id: int,
    payload: AliasCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.get(PlayerProfile, player_id)
    if player is None:
        raise HTTPException(404, detail="player_not_found")
    if player.status == PlayerStatus.MERGED:
        raise HTTPException(409, detail="player_merged")
    db.add(
        PlayerAlias(
            player_id=player_id,
            alias=payload.alias,
            normalized_alias=normalize_player_name(payload.alias),
            is_primary=False,
        )
    )
    try:
        db.commit()
        db.refresh(player)
        return player
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_alias_already_exists") from exc


@router.post("/player-profiles/{target_id}/merge", response_model=PlayerRead)
def merge_player(
    target_id: int,
    payload: PlayerMergeRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        players = list(
            db.scalars(
                select(PlayerProfile)
                .where(PlayerProfile.id.in_([target_id, payload.source_player_id]))
                .with_for_update()
            ).all()
        )
        by_id = {player.id: player for player in players}
        target, source = by_id.get(target_id), by_id.get(payload.source_player_id)
        if not target or not source:
            raise HTTPException(404, detail="player_not_found")
        if target.id == source.id:
            raise HTTPException(409, detail="player_merge_same_profile")
        if target.status == PlayerStatus.MERGED or source.status not in {
            PlayerStatus.ACTIVE,
            PlayerStatus.PROVISIONAL,
        }:
            raise HTTPException(409, detail="player_merge_invalid_status")
        if target.status != PlayerStatus.ACTIVE:
            raise HTTPException(409, detail="player_not_confirmed")
        db.execute(
            update(EntitlementItem)
            .where(EntitlementItem.owner_id == source.id)
            .values(owner_id=target.id)
        )
        db.execute(
            update(EntitlementGrantDraftItem)
            .where(EntitlementGrantDraftItem.player_id == source.id)
            .values(player_id=target.id)
        )
        db.execute(
            update(PlayerAlias)
            .where(PlayerAlias.player_id == source.id)
            .values(player_id=target.id)
        )
        db.execute(
            update(PlayerAlias)
            .where(
                PlayerAlias.player_id == target.id,
                PlayerAlias.normalized_alias != target.normalized_name,
            )
            .values(is_primary=False)
        )
        source.status, source.merged_into_id = PlayerStatus.MERGED, target.id
        db.commit()
        db.refresh(target)
        return target
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_merge_conflict") from exc


@router.get("/entitlement-item-types", response_model=list[ItemTypeRead])
def list_types(_: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return list(
        db.scalars(select(EntitlementItemType).order_by(EntitlementItemType.priority)).all()
    )


@router.get(
    "/theaters/{theater_id}/entitlement-item-types", response_model=list[ItemTypeRead]
)
def list_theater_types(
    theater_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    return list(
        db.scalars(
            select(EntitlementItemType)
            .where(EntitlementItemType.theater_id == theater_id)
            .order_by(EntitlementItemType.sort_order, EntitlementItemType.id)
        ).all()
    )


@router.post(
    "/theaters/{theater_id}/entitlement-item-types", response_model=ItemTypeRead
)
def create_theater_type(
    theater_id: int,
    payload: ItemTypeCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    item_type = EntitlementItemType(theater_id=theater_id, **payload.model_dump())
    db.add(item_type)
    try:
        db.commit()
        db.refresh(item_type)
        return item_type
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="entitlement_item_type_conflict") from exc


@router.post(
    "/theaters/{theater_id}/entitlement-item-types/default-designations",
    response_model=list[ItemTypeRead],
)
def create_default_designation_types(
    theater_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    specs = (
        ("universal", "万能指定", DesignationType.UNIVERSAL, 300),
        ("top_three", "榜三指定", DesignationType.TOP_THREE, 200),
        ("paired", "对位指定", DesignationType.PAIRED, 100),
    )
    existing = set(
        db.scalars(
            select(EntitlementItemType.code).where(
                EntitlementItemType.theater_id == theater_id,
                EntitlementItemType.code.in_([spec[0] for spec in specs]),
            )
        ).all()
    )
    if existing:
        raise HTTPException(409, detail="entitlement_default_type_conflict")
    rows = [
        EntitlementItemType(
            theater_id=theater_id,
            code=code,
            display_name=name,
            category=EntitlementItemCategory.DESIGNATION,
            designation_type=binding,
            priority=priority,
            default_validity_days=90,
            color="#7c3aed",
            is_active=True,
            sort_order=index,
        )
        for index, (code, name, binding, priority) in enumerate(specs)
    ]
    db.add_all(rows)
    try:
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="entitlement_default_type_conflict") from exc


@router.patch("/entitlement-item-types/{type_id}", response_model=ItemTypeRead)
def update_type(
    type_id: int,
    payload: ItemTypeUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item_type = db.get(EntitlementItemType, type_id)
    if not item_type:
        raise HTTPException(404, detail="entitlement_item_type_not_found")
    if item_type.code not in {"universal", "top_three", "paired"}:
        raise HTTPException(409, detail="entitlement_item_type_not_configurable")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(item_type, key, value)
    try:
        db.commit()
        db.refresh(item_type)
        return item_type
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="entitlement_item_type_conflict") from exc


def _populate_batch(batch: EntitlementGrantBatch, payload: GrantBatchCreate, db: Session):
    for key, value in payload.model_dump(exclude={"items"}).items():
        setattr(batch, key, value)
    for spec in payload.items:
        player = db.get(PlayerProfile, spec.player_id)
        item_type = db.get(EntitlementItemType, spec.item_type_id)
        if (
            player is None
            or item_type is None
            or item_type.theater_id != batch.theater_id
            or not item_type.is_active
        ):
            db.rollback()
            raise HTTPException(409, detail="entitlement_grant_reference_invalid")
        if player.status != PlayerStatus.ACTIVE:
            db.rollback()
            raise HTTPException(409, detail="player_not_confirmed")
        values = spec.model_dump(exclude={"quantity"})
        for _ in range(spec.quantity):
            batch.draft_items.append(EntitlementGrantDraftItem(**values))
    db.add(batch)
    try:
        db.commit()
        db.refresh(batch)
        return batch
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="entitlement_grant_reference_invalid") from exc


@router.get("/entitlement-grant-batches", response_model=list[GrantBatchRead])
def list_batches(_: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(EntitlementGrantBatch)
            .options(selectinload(EntitlementGrantBatch.draft_items))
            .order_by(EntitlementGrantBatch.id)
        ).all()
    )


@router.post("/entitlement-grant-batches", response_model=GrantBatchRead)
def create_batch(
    payload: GrantBatchCreate, user: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    batch = EntitlementGrantBatch(created_by=_operator(user, db))
    return _populate_batch(batch, payload, db)


@router.get("/entitlement-grant-batches/{batch_id}", response_model=GrantBatchRead)
def get_batch(batch_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    batch = db.scalar(
        select(EntitlementGrantBatch)
        .where(EntitlementGrantBatch.id == batch_id)
        .options(selectinload(EntitlementGrantBatch.draft_items))
    )
    if not batch:
        raise HTTPException(404, detail="entitlement_grant_batch_not_found")
    return batch


@router.patch("/entitlement-grant-batches/{batch_id}", response_model=GrantBatchRead)
def update_batch(
    batch_id: int,
    payload: GrantBatchCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    batch = db.scalar(
        select(EntitlementGrantBatch).where(EntitlementGrantBatch.id == batch_id).with_for_update()
    )
    if not batch:
        raise HTTPException(404, detail="entitlement_grant_batch_not_found")
    if batch.status != GrantBatchStatus.DRAFT:
        raise HTTPException(409, detail="entitlement_grant_batch_not_draft")
    batch.draft_items.clear()
    return _populate_batch(batch, payload, db)


@router.delete("/entitlement-grant-batches/{batch_id}", status_code=204)
def delete_batch(batch_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    batch = db.scalar(
        select(EntitlementGrantBatch).where(EntitlementGrantBatch.id == batch_id).with_for_update()
    )
    if not batch:
        raise HTTPException(404, detail="entitlement_grant_batch_not_found")
    if batch.status != GrantBatchStatus.DRAFT:
        raise HTTPException(409, detail="entitlement_grant_batch_not_draft")
    db.delete(batch)
    db.commit()
    return Response(status_code=204)


@router.get(
    "/theaters/{theater_id}/entitlement-grant-batches", response_model=list[GrantBatchRead]
)
def list_theater_batches(
    theater_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    return list(
        db.scalars(
            select(EntitlementGrantBatch)
            .where(EntitlementGrantBatch.theater_id == theater_id)
            .options(selectinload(EntitlementGrantBatch.draft_items))
            .order_by(EntitlementGrantBatch.id.desc())
        ).all()
    )


@router.post(
    "/theaters/{theater_id}/entitlement-grant-batches", response_model=GrantBatchRead
)
def create_theater_batch(
    theater_id: int,
    payload: GrantBatchCreate,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    batch = EntitlementGrantBatch(theater_id=theater_id, created_by=_operator(user, db))
    return _populate_batch(batch, payload, db)


@router.post(
    "/theaters/{theater_id}/entitlement-grant-batches/{batch_id}/confirm",
    response_model=GrantBatchRead,
)
def confirm_theater_batch(
    theater_id: int,
    batch_id: int,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=120),
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return confirm_grant_batch(
            db, batch_id, _operator(user, db), theater_id, idempotency_key
        )
    except (EntitlementNotFound, EntitlementConflict) as exc:
        _raise(exc)


@router.get(
    "/theaters/{theater_id}/players/{player_id}/inventory",
    response_model=PlayerInventoryRead,
)
def theater_inventory(
    theater_id: int,
    player_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return inventory_for_player(db, player_id, theater_id)
    except EntitlementNotFound as exc:
        _raise(exc)


@router.post(
    "/theaters/{theater_id}/players/{player_id}/inventory/manual-consumption/preview",
    response_model=ManualConsumeRead,
)
def manual_consumption_preview(
    theater_id: int,
    player_id: int,
    payload: ManualConsumeRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(preview_manual_consumption, db, theater_id, player_id, payload)


@router.post(
    "/theaters/{theater_id}/players/{player_id}/inventory/manual-consumption",
    response_model=ManualConsumeRead,
)
def commit_manual_consumption(
    theater_id: int,
    player_id: int,
    payload: ManualConsumeRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=120),
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(
        manual_consume,
        db,
        theater_id,
        player_id,
        payload,
        _operator(user, db),
        idempotency_key,
    )


@router.get(
    "/theaters/{theater_id}/entitlement-ledger", response_model=EntitlementLedgerPageRead
)
def theater_ledger(
    theater_id: int,
    player_id: int | None = None,
    item_type_id: int | None = None,
    event_type: EntitlementEventType | None = None,
    cursor: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_entitlement_ledger(
        db,
        theater_id,
        player_id=player_id,
        item_type_id=item_type_id,
        event_type=event_type,
        cursor=cursor,
        limit=limit,
    )


@router.post("/entitlement-grant-batches/{batch_id}/confirm", response_model=GrantBatchRead)
def confirm_batch(
    batch_id: int, user: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        return confirm_grant_batch(db, batch_id, _operator(user, db))
    except (EntitlementNotFound, EntitlementConflict) as exc:
        _raise(exc)


@router.get("/players/{player_id}/inventory", response_model=PlayerInventoryRead)
def inventory(player_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return inventory_for_player(db, player_id)
    except EntitlementNotFound as exc:
        _raise(exc)


@router.get("/entitlement-items/{item_id}", response_model=EntitlementItemRead)
def get_item(item_id: int, _: dict = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.scalar(
        select(EntitlementItem)
        .where(EntitlementItem.id == item_id)
        .options(selectinload(EntitlementItem.ledger_entries))
    )
    if item is None:
        raise HTTPException(404, detail="entitlement_item_not_found")
    return item


def _mutation(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except (EntitlementNotFound, EntitlementConflict) as exc:
        _raise(exc)


@router.post("/entitlement-items/{item_id}/extend", response_model=EntitlementItemRead)
def extend(
    item_id: int,
    payload: ExtensionRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(
        extend_item, db, item_id, payload.expires_at, payload.reason, _operator(user, db)
    )


@router.post("/entitlement-items/{item_id}/void", response_model=EntitlementItemRead)
def void(
    item_id: int,
    payload: ReasonRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(void_item, db, item_id, payload.reason, _operator(user, db))


@router.post("/entitlement-items/{item_id}/restore", response_model=EntitlementItemRead)
def restore(
    item_id: int,
    payload: ReasonRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(restore_item, db, item_id, payload.reason, _operator(user, db))


@router.post("/entitlement-items/{item_id}/adjust", response_model=EntitlementItemRead)
def adjust(
    item_id: int,
    payload: AdjustmentRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _mutation(
        adjust_item,
        db,
        item_id,
        expires_at=payload.expires_at,
        source_label=payload.source_label,
        notes=payload.notes,
        reason=payload.reason,
        operator_user_id=_operator(user, db),
    )
