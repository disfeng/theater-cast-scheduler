from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_admin
from app.models.entities import (
    EntitlementItem,
)
from app.models.enums import (
    EntitlementEventType,
)
from app.schemas.entitlements import (
    AdjustmentRequest,
    EntitlementItemRead,
    ExtensionRequest,
    ManualConsumeRead,
    ManualConsumeRequest,
    EntitlementLedgerPageRead,
    PlayerInventoryRead,
    PlayerInventorySummaryRead,
    ReasonRequest,
)
from app.services.entitlements import (
    EntitlementConflict,
    EntitlementNotFound,
)
from app.services.entitlement_inventory import (
    inventory_for_player,
    list_entitlement_ledger,
    list_theater_inventory_summaries,
    manual_consume,
    preview_manual_consumption,
)
from app.services.entitlement_lifecycle import adjust_item, extend_item, restore_item, void_item
from app.api.routes.admin_entitlement_common import _operator, _raise

router = APIRouter(prefix="/admin", tags=["admin_entitlements"])


@router.get(
    "/theaters/{theater_id}/player-inventory-summaries",
    response_model=list[PlayerInventorySummaryRead],
)
def theater_inventory_summaries(
    theater_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list_theater_inventory_summaries(db, theater_id, limit=limit, offset=offset)


@router.get(
    "/theaters/{theater_id}/players/{player_id}/inventory",
    response_model=PlayerInventoryRead,
)
def theater_inventory(
    theater_id: int,
    player_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return inventory_for_player(db, player_id, theater_id, limit=limit, offset=offset)
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


@router.get("/theaters/{theater_id}/entitlement-ledger", response_model=EntitlementLedgerPageRead)
def theater_ledger(
    theater_id: int,
    player_id: int | None = None,
    item_type_id: int | None = None,
    event_type: EntitlementEventType | None = None,
    item_id: int | None = None,
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
        item_id=item_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/players/{player_id}/inventory", response_model=PlayerInventoryRead)
def inventory(
    player_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return inventory_for_player(db, player_id, limit=limit, offset=offset)
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
