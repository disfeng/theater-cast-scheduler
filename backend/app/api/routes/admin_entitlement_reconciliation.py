from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.services.entitlement_reconciliation import (
    entitlement_reconciliation,
    reconciliation_drill,
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
