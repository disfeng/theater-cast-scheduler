from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_admin
from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItemType,
    PlayerProfile,
    Theater,
)
from app.models.enums import (
    GrantBatchStatus,
    PlayerStatus,
)
from app.schemas.entitlements import (
    GrantBatchCreate,
    GrantBatchRead,
)
from app.services.entitlements import (
    EntitlementConflict,
    EntitlementNotFound,
)
from app.services.entitlement_catalog import validate_grant_binding
from app.services.entitlement_grants import confirm_grant_batch
from app.api.routes.admin_entitlement_common import _operator, _raise

router = APIRouter(prefix="/admin", tags=["admin_entitlements"])


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
        try:
            validate_grant_binding(
                db, batch.theater_id, item_type, spec.bound_actor_id, payload.grant_mode
            )
        except EntitlementConflict as exc:
            db.rollback()
            raise HTTPException(409, detail=str(exc)) from exc
        if spec.bound_actor_id != payload.bound_actor_id:
            db.rollback()
            raise HTTPException(409, detail="entitlement_actor_binding_invalid")
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
def list_batches(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(EntitlementGrantBatch)
            .options(selectinload(EntitlementGrantBatch.draft_items))
            .order_by(EntitlementGrantBatch.id)
            .offset(offset)
            .limit(limit)
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


@router.get("/theaters/{theater_id}/entitlement-grant-batches", response_model=list[GrantBatchRead])
def list_theater_batches(
    theater_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(EntitlementGrantBatch)
            .where(EntitlementGrantBatch.theater_id == theater_id)
            .options(selectinload(EntitlementGrantBatch.draft_items))
            .order_by(EntitlementGrantBatch.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


@router.post("/theaters/{theater_id}/entitlement-grant-batches", response_model=GrantBatchRead)
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
        return confirm_grant_batch(db, batch_id, _operator(user, db), theater_id, idempotency_key)
    except (EntitlementNotFound, EntitlementConflict) as exc:
        _raise(exc)


@router.post("/entitlement-grant-batches/{batch_id}/confirm", response_model=GrantBatchRead)
def confirm_batch(
    batch_id: int, user: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        return confirm_grant_batch(db, batch_id, _operator(user, db))
    except (EntitlementNotFound, EntitlementConflict) as exc:
        _raise(exc)
