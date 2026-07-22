"""Focused entitlement service extracted from the legacy facade."""

from datetime import datetime, timedelta

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import Session


from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    Designation,
    Performance,
    PlayerProfile,
    User,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
    GrantBatchStatus,
)


from app.services import entitlements as _legacy

EntitlementError = _legacy.EntitlementError
EntitlementNotFound = _legacy.EntitlementNotFound
EntitlementConflict = _legacy.EntitlementConflict


def _expiry_predicate(expiry: str | None, now: datetime):
    if expiry == "expired":
        return EntitlementItem.expires_at <= now
    days = {"expires_within_7_days": 7, "expires_within_30_days": 30}.get(expiry)
    if days is not None:
        return and_(
            EntitlementItem.expires_at > now,
            EntitlementItem.expires_at <= now + timedelta(days=days),
        )
    return None


def _status_totals(db: Session, predicate=None) -> dict[str, int]:
    stmt = select(EntitlementItem.status, func.count(EntitlementItem.id)).group_by(
        EntitlementItem.status
    )
    if predicate is not None:
        stmt = stmt.where(predicate)
    found = {status.value: count for status, count in db.execute(stmt)}
    return {status.value: found.get(status.value, 0) for status in EntitlementItemStatus}


def _anomaly_statement(now: datetime):
    """Return lightweight anomaly projections; no ORM entities are materialized."""
    ledger = EntitlementLedgerEntry
    item = EntitlementItem
    designation = Designation

    def projection(code, item_id=None, ledger_id=None, designation_id=None, batch_id=None):
        return (
            literal(code).label("code"),
            (item_id if item_id is not None else literal(None)).label("item_id"),
            (ledger_id if ledger_id is not None else literal(None)).label("ledger_id"),
            (designation_id if designation_id is not None else literal(None)).label(
                "designation_id"
            ),
            (batch_id if batch_id is not None else literal(None)).label("batch_id"),
        )

    grant_counts = (
        select(
            item.id.label("item_id"),
            item.grant_batch_id.label("batch_id"),
            func.count(ledger.id).label("grant_count"),
        )
        .outerjoin(
            ledger,
            and_(ledger.item_id == item.id, ledger.event_type == EntitlementEventType.GRANTED),
        )
        .group_by(item.id, item.grant_batch_id)
        .subquery()
    )
    missing_grant = select(
        *projection(
            "missing_grant_ledger", grant_counts.c.item_id, batch_id=grant_counts.c.batch_id
        )
    ).where(grant_counts.c.grant_count == 0)
    duplicate_grant = select(
        *projection(
            "duplicate_grant_ledger", grant_counts.c.item_id, batch_id=grant_counts.c.batch_id
        )
    ).where(grant_counts.c.grant_count > 1)
    invalid_grant = select(
        *projection("invalid_grant_transition", ledger.item_id, ledger.id)
    ).where(
        ledger.event_type == EntitlementEventType.GRANTED,
        or_(ledger.from_status.is_not(None), ledger.to_status != EntitlementItemStatus.AVAILABLE),
    )
    missing_ledger = (
        select(*projection("missing_item_ledger", item.id))
        .outerjoin(ledger, ledger.item_id == item.id)
        .where(ledger.id.is_(None))
    )

    dangling_item = (
        select(
            *projection(
                "dangling_current_designation", item.id, designation_id=item.current_designation_id
            )
        )
        .outerjoin(designation, designation.id == item.current_designation_id)
        .where(item.current_designation_id.is_not(None), designation.id.is_(None))
    )
    stale_backlink = (
        select(
            *projection(
                "stale_current_designation_backlink", item.id, designation_id=designation.id
            )
        )
        .join(designation, designation.id == item.current_designation_id)
        .where(designation.entitlement_item_id != item.id)
    )
    reserved_mismatch = (
        select(
            *projection(
                "reserved_without_predesignated_designation",
                item.id,
                designation_id=item.current_designation_id,
            )
        )
        .outerjoin(designation, designation.id == item.current_designation_id)
        .where(
            item.status == EntitlementItemStatus.RESERVED,
            or_(
                designation.id.is_(None),
                designation.lifecycle_status != "predesignated",
                designation.entitlement_item_id != item.id,
            ),
        )
    )
    consumed_mismatch = (
        select(
            *projection(
                "consumed_without_fulfilled_designation",
                item.id,
                designation_id=item.current_designation_id,
            )
        )
        .outerjoin(designation, designation.id == item.current_designation_id)
        .where(
            item.status == EntitlementItemStatus.CONSUMED,
            or_(
                designation.id.is_(None),
                designation.lifecycle_status.not_in(("effective", "fulfilled")),
                designation.entitlement_item_id != item.id,
            ),
        )
    )
    active_designation_mismatch = (
        select(
            *projection("designation_item_state_mismatch", item.id, designation_id=designation.id)
        )
        .outerjoin(item, item.id == designation.entitlement_item_id)
        .where(
            or_(
                and_(
                    designation.lifecycle_status == "predesignated",
                    or_(
                        designation.entitlement_item_id.is_(None),
                        item.id.is_(None),
                        item.status != EntitlementItemStatus.RESERVED,
                        item.current_designation_id != designation.id,
                    ),
                ),
                and_(
                    designation.lifecycle_status.in_(("effective", "fulfilled")),
                    or_(
                        designation.entitlement_item_id.is_(None),
                        item.id.is_(None),
                        item.status != EntitlementItemStatus.CONSUMED,
                        item.current_designation_id != designation.id,
                    ),
                ),
            )
        )
    )
    inactive_designation = select(
        *projection(
            "inactive_designation_retains_item",
            designation.entitlement_item_id,
            designation_id=designation.id,
        )
    ).where(
        designation.entitlement_item_id.is_not(None),
        designation.lifecycle_status.not_in(("predesignated", "effective", "fulfilled")),
    )
    available_expired = select(*projection("available_item_expired", item.id)).where(
        item.status == EntitlementItemStatus.AVAILABLE, item.expires_at <= now
    )
    premature_expired = select(*projection("premature_expired_status", item.id)).where(
        item.status == EntitlementItemStatus.EXPIRED, item.expires_at > now
    )

    orphan_designation = (
        select(
            *projection(
                "orphan_ledger_designation", ledger.item_id, ledger.id, ledger.designation_id
            )
        )
        .outerjoin(designation, designation.id == ledger.designation_id)
        .where(ledger.designation_id.is_not(None), designation.id.is_(None))
    )
    orphan_performance = (
        select(*projection("orphan_ledger_performance", ledger.item_id, ledger.id))
        .outerjoin(Performance, Performance.id == ledger.performance_id)
        .where(ledger.performance_id.is_not(None), Performance.id.is_(None))
    )
    orphan_operator = (
        select(*projection("orphan_ledger_operator", ledger.item_id, ledger.id))
        .outerjoin(User, User.id == ledger.operator_user_id)
        .where(ledger.operator_user_id.is_not(None), User.id.is_(None))
    )
    ledger_scope = (
        select(
            *projection(
                "ledger_designation_scope_mismatch",
                ledger.item_id,
                ledger.id,
                ledger.designation_id,
            )
        )
        .outerjoin(designation, designation.id == ledger.designation_id)
        .where(
            ledger.event_type.in_((EntitlementEventType.RESERVED, EntitlementEventType.CONSUMED)),
            or_(
                designation.id.is_(None),
                designation.entitlement_item_id != ledger.item_id,
                and_(
                    ledger.performance_id.is_not(None),
                    designation.performance_id != ledger.performance_id,
                ),
            ),
        )
    )

    draft_counts = (
        select(EntitlementGrantDraftItem.batch_id, func.count().label("draft_count"))
        .group_by(EntitlementGrantDraftItem.batch_id)
        .subquery()
    )
    item_counts = (
        select(
            item.grant_batch_id.label("batch_id"),
            func.count().label("item_count"),
            func.min(item.id).label("item_id"),
        )
        .where(item.grant_batch_id.is_not(None))
        .group_by(item.grant_batch_id)
        .subquery()
    )
    batch_mismatch = (
        select(
            *projection(
                "grant_batch_total_mismatch",
                item_id=item_counts.c.item_id,
                batch_id=EntitlementGrantBatch.id,
            )
        )
        .outerjoin(draft_counts, draft_counts.c.batch_id == EntitlementGrantBatch.id)
        .outerjoin(item_counts, item_counts.c.batch_id == EntitlementGrantBatch.id)
        .where(
            EntitlementGrantBatch.status == GrantBatchStatus.GRANTED,
            func.coalesce(draft_counts.c.draft_count, 0)
            != func.coalesce(item_counts.c.item_count, 0),
        )
    )
    return union_all(
        missing_grant,
        duplicate_grant,
        invalid_grant,
        missing_ledger,
        dangling_item,
        stale_backlink,
        reserved_mismatch,
        consumed_mismatch,
        active_designation_mismatch,
        inactive_designation,
        available_expired,
        premature_expired,
        orphan_designation,
        orphan_performance,
        orphan_operator,
        ledger_scope,
        batch_mismatch,
    ).subquery("entitlement_anomalies")


def entitlement_reconciliation(
    db: Session, *, expiry: str | None = None, now: datetime | None = None
) -> dict[str, object]:
    now = now or _legacy.utcnow()
    predicate = _expiry_predicate(expiry, now)
    columns = (
        EntitlementItemType.code,
        EntitlementItem.source_month,
        EntitlementItem.source_label,
        EntitlementItem.owner_id,
        PlayerProfile.display_name,
        EntitlementItem.status,
        func.count(EntitlementItem.id),
    )
    stmt = select(*columns).join(EntitlementItemType).join(PlayerProfile).group_by(*columns[:-1])
    if predicate is not None:
        stmt = stmt.where(predicate)
    rows = [
        {
            "item_type": code,
            "source_month": month.isoformat(),
            "source_label": label,
            "player_id": player_id,
            "player_name": player_name,
            "status": status.value,
            "item_count": count,
            "drill_down_filter": {
                "item_type": code,
                "source_month": month.isoformat(),
                "source_label": label,
                "player_id": player_id,
                "status": status.value,
            },
        }
        for code, month, label, player_id, player_name, status, count in db.execute(stmt)
    ]
    anomaly_rows = _anomaly_statement(now)
    anomaly_count_stmt = select(func.count()).select_from(anomaly_rows)
    if predicate is not None:
        anomaly_count_stmt = anomaly_count_stmt.where(
            anomaly_rows.c.item_id.in_(select(EntitlementItem.id).where(predicate))
        )
    return {
        "generated_at": now.isoformat(),
        "expiry_filter": expiry,
        "filtered_totals": _status_totals(db, predicate),
        "global_totals": _status_totals(db),
        "rows": rows,
        "anomaly_count": db.scalar(anomaly_count_stmt) or 0,
    }


def reconciliation_drill(
    db: Session,
    *,
    kind: str,
    expiry: str | None,
    limit: int,
    cursor: int,
    filters: dict[str, object],
    now: datetime | None = None,
) -> dict[str, object]:
    now = now or _legacy.utcnow()
    predicate = _expiry_predicate(expiry, now)
    stmt = select(EntitlementItem).join(EntitlementItemType)
    if predicate is not None:
        stmt = stmt.where(predicate)
    mapping = {
        "item_type": EntitlementItemType.code,
        "source_month": EntitlementItem.source_month,
        "source_label": EntitlementItem.source_label,
        "player_id": EntitlementItem.owner_id,
        "status": EntitlementItem.status,
    }
    for name, column in mapping.items():
        if filters.get(name) is not None:
            stmt = stmt.where(column == filters[name])
    item_ids = stmt.with_only_columns(EntitlementItem.id)
    if kind == "items":
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        records = list(
            db.scalars(
                stmt.where(EntitlementItem.id > cursor).order_by(EntitlementItem.id).limit(limit)
            ).all()
        )
        data = [
            {
                "id": row.id,
                "serial_number": row.serial_number,
                "status": row.status.value,
                "expires_at": row.expires_at.isoformat(),
            }
            for row in records
        ]
        next_cursor = records[-1].id if len(records) == limit else None
    elif kind == "ledgers":
        ledger_stmt = select(EntitlementLedgerEntry).where(
            EntitlementLedgerEntry.item_id.in_(item_ids)
        )
        total = db.scalar(select(func.count()).select_from(ledger_stmt.subquery())) or 0
        records = list(
            db.scalars(
                ledger_stmt.where(EntitlementLedgerEntry.id > cursor)
                .order_by(EntitlementLedgerEntry.id)
                .limit(limit)
            ).all()
        )
        data = [
            {
                "id": row.id,
                "item_id": row.item_id,
                "event_type": row.event_type.value,
                "from_status": row.from_status.value if row.from_status else None,
                "to_status": row.to_status.value if row.to_status else None,
            }
            for row in records
        ]
        next_cursor = records[-1].id if len(records) == limit else None
    else:
        anomaly_rows = _anomaly_statement(now)
        anomaly_stmt = select(anomaly_rows)
        if predicate is not None:
            anomaly_stmt = anomaly_stmt.where(
                anomaly_rows.c.item_id.in_(select(EntitlementItem.id).where(predicate))
            )
        total = db.scalar(select(func.count()).select_from(anomaly_stmt.subquery())) or 0
        fetched = (
            db.execute(
                anomaly_stmt.order_by(
                    anomaly_rows.c.code, anomaly_rows.c.item_id, anomaly_rows.c.ledger_id
                )
                .offset(cursor)
                .limit(limit + 1)
            )
            .mappings()
            .all()
        )
        data = [
            {
                "code": row["code"],
                "item_ids": [] if row["item_id"] is None else [row["item_id"]],
                "ledger_entry_ids": [] if row["ledger_id"] is None else [row["ledger_id"]],
                "designation_id": row["designation_id"],
                "batch_id": row["batch_id"],
            }
            for row in fetched[:limit]
        ]
        next_cursor = cursor + limit if len(fetched) > limit else None
    return {
        "kind": kind,
        "total": total,
        "limit": limit,
        "next_cursor": next_cursor,
        "records": data,
    }


__all__ = ["entitlement_reconciliation", "reconciliation_drill"]
