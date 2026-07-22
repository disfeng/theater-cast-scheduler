from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import (
    EntitlementItemType,
    Theater,
)
from app.models.enums import (
    DesignationType,
    EntitlementItemCategory,
)
from app.schemas.entitlements import (
    ItemTypeCreate,
    ItemTypeRead,
    ItemTypeUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin_entitlements"])


@router.get("/entitlement-item-types", response_model=list[ItemTypeRead])
def list_types(_: dict = Depends(require_admin), db: Session = Depends(get_db)):
    return list(
        db.scalars(select(EntitlementItemType).order_by(EntitlementItemType.priority)).all()
    )


@router.get("/theaters/{theater_id}/entitlement-item-types", response_model=list[ItemTypeRead])
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


@router.post("/theaters/{theater_id}/entitlement-item-types", response_model=ItemTypeRead)
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
        ("universal", "万能指定", DesignationType.UNIVERSAL, 300, False, False),
        ("top_three", "榜三指定", DesignationType.TOP_THREE, 200, False, True),
        ("paired", "对位指定", DesignationType.PAIRED, 100, True, False),
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
            color="#2f6fed",
            is_active=True,
            sort_order=index,
            binds_beneficiary=binds_beneficiary,
            binds_actor=binds_actor,
        )
        for index, (code, name, binding, priority, binds_beneficiary, binds_actor) in enumerate(
            specs
        )
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
    values = payload.model_dump(exclude_unset=True)
    binding_keys = {"binds_beneficiary", "binds_actor"}
    if item_type.binding_locked_at is not None and any(
        key in values and values[key] != getattr(item_type, key) for key in binding_keys
    ):
        raise HTTPException(409, detail="entitlement_binding_locked")
    resulting_category = values.get("category", item_type.category)
    resulting_binding = values.get("designation_type", item_type.designation_type)
    if (
        resulting_category == EntitlementItemCategory.DESIGNATION and resulting_binding is None
    ) or (resulting_category == EntitlementItemCategory.GENERAL and resulting_binding is not None):
        raise HTTPException(409, detail="entitlement_item_type_binding_invalid")
    for key, value in values.items():
        setattr(item_type, key, value)
    try:
        db.commit()
        db.refresh(item_type)
        return item_type
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="entitlement_item_type_conflict") from exc
