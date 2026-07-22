"""Focused entitlement service extracted from the legacy facade."""

import json
from datetime import datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, selectinload
from pypinyin import lazy_pinyin


from app.models.entities import (
    Actor,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    Performance,
    PlayerProfile,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
    PlayerStatus,
)
from app.schemas.entitlements import (
    EntitlementLedgerPageRead,
    ManualConsumeRead,
    ManualConsumeRequest,
    PlayerInventoryRead,
    PlayerInventorySummaryRead,
)


from app.services import entitlements as _legacy

EntitlementError = _legacy.EntitlementError
EntitlementNotFound = _legacy.EntitlementNotFound
EntitlementConflict = _legacy.EntitlementConflict


def inventory_for_player(
    db: Session,
    player_id: int,
    theater_id: int | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> PlayerInventoryRead:
    player = db.get(PlayerProfile, player_id)
    if player is None:
        raise EntitlementNotFound("player_not_found")
    condition = EntitlementItem.owner_id == player_id
    if theater_id is not None:
        condition = and_(condition, EntitlementItem.theater_id == theater_id)
    items = list(
        db.scalars(
            select(EntitlementItem)
            .where(condition)
            .options(
                selectinload(EntitlementItem.ledger_entries),
                selectinload(EntitlementItem.bound_actor),
            )
            .order_by(EntitlementItem.id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return PlayerInventoryRead(player=player, items=items)


def list_theater_inventory_summaries(
    db: Session,
    theater_id: int,
    now: datetime | None = None,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[PlayerInventorySummaryRead]:
    current = now or _legacy.utcnow()
    present = EntitlementItem.status.in_(
        [EntitlementItemStatus.AVAILABLE, EntitlementItemStatus.EXPIRED]
    )
    expired = and_(
        present,
        or_(
            EntitlementItem.status == EntitlementItemStatus.EXPIRED,
            EntitlementItem.expires_at < current,
        ),
    )
    rows = db.execute(
        select(
            PlayerProfile.id,
            PlayerProfile.display_name,
            PlayerProfile.normalized_name,
            PlayerProfile.status,
            func.sum(case((present, 1), else_=0)).label("item_count"),
            func.sum(case((expired, 1), else_=0)).label("expired_count"),
        )
        .outerjoin(
            EntitlementItem,
            and_(
                EntitlementItem.owner_id == PlayerProfile.id,
                EntitlementItem.theater_id == theater_id,
            ),
        )
        .where(PlayerProfile.status == PlayerStatus.ACTIVE)
        .group_by(
            PlayerProfile.id,
            PlayerProfile.display_name,
            PlayerProfile.normalized_name,
            PlayerProfile.status,
        )
        .order_by(PlayerProfile.normalized_name, PlayerProfile.id)
        .offset(offset)
        .limit(limit)
    ).all()
    result = [
        PlayerInventorySummaryRead(
            player_id=row.id,
            display_name=row.display_name,
            normalized_name=row.normalized_name,
            sort_key="".join(lazy_pinyin(row.display_name)).casefold()
            or row.normalized_name.casefold(),
            status=row.status,
            item_count=int(row.item_count or 0),
            expired_count=int(row.expired_count or 0),
        )
        for row in rows
    ]
    return sorted(result, key=lambda row: (row.sort_key, row.normalized_name, row.player_id))


def _manual_consumption_items(
    db: Session,
    theater_id: int,
    player_id: int,
    payload: ManualConsumeRequest,
    *,
    lock: bool,
) -> list[EntitlementItem]:
    item_type = db.scalar(
        select(EntitlementItemType).where(
            EntitlementItemType.id == payload.item_type_id,
            EntitlementItemType.theater_id == theater_id,
        )
    )
    if item_type is None:
        raise EntitlementNotFound("entitlement_item_type_not_found")
    if payload.performance_id is not None:
        performance = db.get(Performance, payload.performance_id)
        if performance is None or performance.theater_id != theater_id:
            raise EntitlementConflict("manual_consumption_performance_invalid")
    stmt = (
        select(EntitlementItem)
        .where(
            EntitlementItem.theater_id == theater_id,
            EntitlementItem.owner_id == player_id,
            EntitlementItem.item_type_id == payload.item_type_id,
            EntitlementItem.status == EntitlementItemStatus.AVAILABLE,
            EntitlementItem.expires_at > _legacy.utcnow(),
        )
        .order_by(EntitlementItem.expires_at, EntitlementItem.id)
        .limit(payload.quantity)
    )
    if lock:
        stmt = stmt.with_for_update()
    items = list(db.scalars(stmt).all())
    if len(items) != payload.quantity:
        raise EntitlementConflict("entitlement_inventory_insufficient")
    return items


def preview_manual_consumption(
    db: Session, theater_id: int, player_id: int, payload: ManualConsumeRequest
) -> ManualConsumeRead:
    if db.get(PlayerProfile, player_id) is None:
        raise EntitlementNotFound("player_not_found")
    items = _manual_consumption_items(db, theater_id, player_id, payload, lock=False)
    return ManualConsumeRead(
        item_ids=[item.id for item in items],
        serial_numbers=[item.serial_number for item in items],
    )


def manual_consume(
    db: Session,
    theater_id: int,
    player_id: int,
    payload: ManualConsumeRequest,
    operator_user_id: int,
    idempotency_key: str,
) -> ManualConsumeRead:
    try:
        previous = db.scalar(
            select(EntitlementLedgerEntry).where(
                EntitlementLedgerEntry.idempotency_key == idempotency_key
            )
        )
        if previous is not None:
            detail = json.loads(previous.note or "{}")
            ids = detail.get("operation_item_ids", [previous.item_id])
            rows = list(
                db.scalars(select(EntitlementItem).where(EntitlementItem.id.in_(ids))).all()
            )
            by_id = {row.id: row for row in rows}
            return ManualConsumeRead(
                item_ids=ids,
                serial_numbers=[by_id[item_id].serial_number for item_id in ids],
            )
        items = _manual_consumption_items(db, theater_id, player_id, payload, lock=True)
        item_ids = [item.id for item in items]
        for index, item in enumerate(items):
            old = item.status
            item.status = EntitlementItemStatus.CONSUMED
            _legacy._ledger(
                db,
                item,
                EntitlementEventType.MANUALLY_CONSUMED,
                old=old,
                new=item.status,
                operator_user_id=operator_user_id,
                reason=payload.note,
                purpose=payload.purpose,
                performance_id=payload.performance_id,
                idempotency_key=idempotency_key if index == 0 else None,
                operation_item_ids=item_ids,
            )
        db.commit()
        return ManualConsumeRead(
            item_ids=item_ids,
            serial_numbers=[item.serial_number for item in items],
        )
    except Exception:
        db.rollback()
        raise


def list_entitlement_ledger(
    db: Session,
    theater_id: int,
    *,
    player_id: int | None = None,
    item_type_id: int | None = None,
    event_type: EntitlementEventType | None = None,
    item_id: int | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> EntitlementLedgerPageRead:
    stmt = (
        select(
            EntitlementLedgerEntry,
            EntitlementItem,
            EntitlementItemType,
            PlayerProfile,
            Actor,
        )
        .join(EntitlementItem, EntitlementItem.id == EntitlementLedgerEntry.item_id)
        .join(EntitlementItemType, EntitlementItemType.id == EntitlementItem.item_type_id)
        .join(PlayerProfile, PlayerProfile.id == EntitlementItem.owner_id)
        .outerjoin(Actor, Actor.id == EntitlementItem.bound_actor_id)
        .where(EntitlementLedgerEntry.theater_id == theater_id)
        .order_by(EntitlementLedgerEntry.id.desc())
        .limit(limit + 1)
    )
    if player_id is not None:
        stmt = stmt.where(EntitlementItem.owner_id == player_id)
    if item_type_id is not None:
        stmt = stmt.where(EntitlementItem.item_type_id == item_type_id)
    if event_type is not None:
        stmt = stmt.where(EntitlementLedgerEntry.event_type == event_type)
    if item_id is not None:
        stmt = stmt.where(EntitlementItem.id == item_id)
    if cursor is not None:
        stmt = stmt.where(EntitlementLedgerEntry.id < cursor)
    rows = list(db.execute(stmt).all())
    page = rows[:limit]
    return EntitlementLedgerPageRead(
        records=[
            {
                "id": ledger.id,
                "theater_id": ledger.theater_id,
                "item_id": item.id,
                "serial_number": item.serial_number,
                "player_id": player.id,
                "player_name": player.display_name,
                "item_type_id": item_type.id,
                "item_type_name": item_type.display_name,
                "bound_actor_id": item.bound_actor_id,
                "bound_actor_name": actor.display_name if actor is not None else None,
                "event_type": ledger.event_type,
                "occurred_at": ledger.occurred_at,
                "from_status": ledger.from_status,
                "to_status": ledger.to_status,
                "purpose": ledger.purpose,
                "reason": ledger.reason,
                "note": ledger.note,
                "performance_id": ledger.performance_id,
                "designation_id": ledger.designation_id,
                "operator_user_id": ledger.operator_user_id,
            }
            for ledger, item, item_type, player, actor in page
        ],
        next_cursor=page[-1][0].id if len(rows) > limit else None,
    )


__all__ = [
    "inventory_for_player",
    "list_theater_inventory_summaries",
    "preview_manual_consumption",
    "manual_consume",
    "list_entitlement_ledger",
]
