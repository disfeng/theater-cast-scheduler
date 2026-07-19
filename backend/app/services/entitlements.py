import calendar
import json
import re
from datetime import datetime, timedelta

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementGrantDraftItem,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    Designation,
    Performance,
    PlayerAlias,
    PlayerProfile,
    User,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemCategory,
    EntitlementItemStatus,
    GrantBatchStatus,
    PlayerStatus,
)
from app.schemas.entitlements import (
    EntitlementLedgerPageRead,
    ManualConsumeRead,
    ManualConsumeRequest,
    PlayerInventoryRead,
    PlayerMatchResult,
)


def utcnow() -> datetime:
    return datetime.utcnow()


class EntitlementError(RuntimeError):
    pass


class EntitlementNotFound(EntitlementError):
    pass


class EntitlementConflict(EntitlementError):
    pass


def normalize_player_name(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _canonical_player(db: Session, player: PlayerProfile) -> PlayerProfile | None:
    visited: set[int] = set()
    while player.status == PlayerStatus.MERGED:
        if player.id in visited or player.merged_into_id is None:
            return None
        visited.add(player.id)
        player = db.get(PlayerProfile, player.merged_into_id)
        if player is None:
            return None
    return player if player.status == PlayerStatus.ACTIVE else player


def _exact_match_players(db: Session, normalized: str) -> list[PlayerProfile]:
    claimed = list(
        db.scalars(
            select(PlayerProfile)
            .join(PlayerAlias)
            .where(PlayerAlias.normalized_alias == normalized)
        ).all()
    )
    legacy = list(
        db.scalars(
            select(PlayerProfile).where(
                PlayerProfile.normalized_name == normalized,
                PlayerProfile.status != PlayerStatus.MERGED,
            )
        ).all()
    )
    canonical = (_canonical_player(db, player) for player in claimed + legacy)
    return list({player.id: player for player in canonical if player is not None}.values())


def create_or_match_player(db: Session, display_name: str) -> PlayerMatchResult:
    normalized = normalize_player_name(display_name)
    if not normalized:
        raise EntitlementConflict("player_name_required")
    exact = _exact_match_players(db, normalized)
    if len(exact) == 1:
        return PlayerMatchResult(player=exact[0])
    if len(exact) > 1:
        return PlayerMatchResult(candidates=exact)
    raw_candidates = list(
        db.scalars(
            select(PlayerProfile)
            .outerjoin(PlayerAlias)
            .where(
                PlayerProfile.status != PlayerStatus.MERGED,
                or_(
                    PlayerProfile.normalized_name.contains(normalized),
                    PlayerAlias.normalized_alias.contains(normalized),
                ),
            )
            .distinct()
            .order_by(PlayerProfile.id)
        ).all()
    )
    candidates = list(
        {
            candidate.id: candidate
            for candidate in (_canonical_player(db, player) for player in raw_candidates)
            if candidate is not None
        }.values()
    )
    if candidates:
        return PlayerMatchResult(candidates=candidates)
    player = PlayerProfile(
        display_name=display_name.strip(),
        normalized_name=normalized,
        status=PlayerStatus.PROVISIONAL,
    )
    try:
        db.add(player)
        db.flush()
        db.add(
            PlayerAlias(
                player_id=player.id,
                alias=player.display_name,
                normalized_alias=normalized,
                is_primary=True,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        matches = _exact_match_players(db, normalized)
        if len(matches) == 1:
            return PlayerMatchResult(player=matches[0])
        return PlayerMatchResult(candidates=matches)
    db.refresh(player)
    return PlayerMatchResult(player=player, created=True)


def _add_months(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(total, 12)
    day = min(value.day, calendar.monthrange(year, month0 + 1)[1])
    return value.replace(year=year, month=month0 + 1, day=day)


def _note(**values: object) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True)


def _ledger(
    db: Session,
    item: EntitlementItem,
    event: EntitlementEventType,
    *,
    old=None,
    new=None,
    operator_user_id: int,
    reason: str | None = None,
    performance_id: int | None = None,
    designation_id: int | None = None,
    purpose: str | None = None,
    idempotency_key: str | None = None,
    **details: object,
) -> None:
    db.add(
        EntitlementLedgerEntry(
            theater_id=item.theater_id,
            item=item,
            event_type=event,
            from_status=old,
            to_status=new,
            performance_id=performance_id,
            designation_id=designation_id,
            reason=reason,
            purpose=purpose,
            idempotency_key=idempotency_key,
            operator_user_id=operator_user_id,
            note=_note(operator_user_id=operator_user_id, reason=reason, **details),
        )
    )


def _confirm_grant_batch_once(
    db: Session,
    batch_id: int,
    operator_user_id: int,
    theater_id: int | None = None,
    idempotency_key: str | None = None,
) -> EntitlementGrantBatch:
    try:
        batch = db.scalar(
            select(EntitlementGrantBatch)
            .where(EntitlementGrantBatch.id == batch_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if batch is None:
            raise EntitlementNotFound("entitlement_grant_batch_not_found")
        if theater_id is not None and batch.theater_id != theater_id:
            raise EntitlementNotFound("entitlement_grant_batch_not_found")
        if batch.status == GrantBatchStatus.GRANTED and idempotency_key:
            if batch.idempotency_key == idempotency_key:
                return batch
        if batch.status != GrantBatchStatus.DRAFT:
            raise EntitlementConflict("entitlement_grant_batch_not_draft")
        if not batch.draft_items:
            raise EntitlementConflict("entitlement_grant_batch_empty")
        now = utcnow()
        date_key = batch.source_month or batch.grant_date or now.date()
        prefix = (
            f"T{batch.theater_id}-{date_key:%Y%m}-"
            if batch.theater_id is not None
            else f"DT-{date_key:%Y%m}-"
        )
        existing = list(
            db.scalars(
                select(EntitlementItem.serial_number).where(
                    EntitlementItem.serial_number.like(f"{prefix}%")
                )
            ).all()
        )
        start = max((int(serial.rsplit("-", 1)[1]) for serial in existing), default=0)
        for sequence, draft in enumerate(batch.draft_items, start=start + 1):
            item_type = db.get(EntitlementItemType, draft.item_type_id)
            player = db.get(PlayerProfile, draft.player_id)
            if item_type is None or player is None or item_type.theater_id != batch.theater_id:
                raise EntitlementConflict("entitlement_grant_draft_reference_invalid")
            if not item_type.is_active:
                raise EntitlementConflict("entitlement_item_type_inactive")
            if player.status != PlayerStatus.ACTIVE:
                raise EntitlementConflict("player_not_confirmed")
            item = EntitlementItem(
                theater_id=batch.theater_id,
                serial_number=f"{prefix}{sequence:04d}",
                owner_id=draft.player_id,
                item_type_id=draft.item_type_id,
                grant_batch_id=batch.id,
                source_type=batch.source_type,
                source_month=draft.source_month or batch.source_month,
                source_label=draft.source_label or batch.source_label,
                granted_at=now,
                expires_at=draft.expires_at
                or batch.default_expires_at
                or now + timedelta(days=item_type.default_validity_days),
                notes=draft.notes,
            )
            db.add(item)
            _ledger(
                db,
                item,
                EntitlementEventType.GRANTED,
                new=EntitlementItemStatus.AVAILABLE,
                operator_user_id=operator_user_id,
            )
        batch.status = GrantBatchStatus.GRANTED
        batch.granted_at = batch.confirmed_at = now
        batch.confirmed_by = operator_user_id
        batch.idempotency_key = idempotency_key
        db.commit()
        db.refresh(batch)
        return batch
    except Exception:
        db.rollback()
        raise


def confirm_grant_batch(
    db: Session,
    batch_id: int,
    operator_user_id: int,
    theater_id: int | None = None,
    idempotency_key: str | None = None,
) -> EntitlementGrantBatch:
    for attempt in range(3):
        try:
            return _confirm_grant_batch_once(
                db, batch_id, operator_user_id, theater_id, idempotency_key
            )
        except IntegrityError as exc:
            db.rollback()
            if not _is_serial_unique_conflict(exc):
                raise EntitlementConflict("entitlement_integrity_error") from exc
            if attempt == 2:
                raise EntitlementConflict("entitlement_serial_conflict") from exc
    raise EntitlementConflict("entitlement_serial_conflict")


def _is_serial_unique_conflict(exc: IntegrityError) -> bool:
    message = str(exc.orig).casefold()
    return "serial_number" in message and any(
        marker in message for marker in ("unique", "duplicate", "1062")
    )


def _locked_item(db: Session, item_id: int) -> EntitlementItem:
    item = db.scalar(
        select(EntitlementItem)
        .where(EntitlementItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise EntitlementNotFound("entitlement_item_not_found")
    return item


def reserve_item(
    db: Session, item_id: int, designation_id: int, performance_id: int, operator_user_id: int
) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if item.status == EntitlementItemStatus.RESERVED:
            raise EntitlementConflict("entitlement_already_reserved")
        if item.status != EntitlementItemStatus.AVAILABLE:
            raise EntitlementConflict("entitlement_not_available")
        if item.expires_at <= utcnow():
            raise EntitlementConflict("entitlement_expired")
        old = item.status
        item.status, item.current_designation_id = EntitlementItemStatus.RESERVED, designation_id
        _ledger(
            db,
            item,
            EntitlementEventType.RESERVED,
            old=old,
            new=item.status,
            operator_user_id=operator_user_id,
            performance_id=performance_id,
            designation_id=designation_id,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def release_item(db: Session, item_id: int, reason: str, operator_user_id: int) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if item.status != EntitlementItemStatus.RESERVED:
            raise EntitlementConflict("entitlement_not_reserved")
        old, designation_id = item.status, item.current_designation_id
        item.status = (
            EntitlementItemStatus.EXPIRED
            if item.expires_at <= utcnow()
            else EntitlementItemStatus.AVAILABLE
        )
        item.current_designation_id = None
        event = (
            EntitlementEventType.EXPIRED
            if item.status == EntitlementItemStatus.EXPIRED
            else EntitlementEventType.RELEASED
        )
        _ledger(
            db,
            item,
            event,
            old=old,
            new=item.status,
            operator_user_id=operator_user_id,
            designation_id=designation_id,
            reason=reason,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def consume_item(db: Session, item_id: int, operator_user_id: int) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if item.status != EntitlementItemStatus.RESERVED:
            raise EntitlementConflict("entitlement_not_reserved")
        old = item.status
        item.status = EntitlementItemStatus.CONSUMED
        _ledger(
            db,
            item,
            EntitlementEventType.CONSUMED,
            old=old,
            new=item.status,
            operator_user_id=operator_user_id,
            designation_id=item.current_designation_id,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def extend_item(
    db: Session, item_id: int, expires_at: datetime, reason: str, operator_user_id: int
) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if expires_at <= item.expires_at:
            raise EntitlementConflict("entitlement_extension_must_increase_expiry")
        old_expiry, old_status = item.expires_at, item.status
        item.expires_at = expires_at
        if item.status == EntitlementItemStatus.EXPIRED and expires_at > utcnow():
            item.status = EntitlementItemStatus.AVAILABLE
        _ledger(
            db,
            item,
            EntitlementEventType.EXTENDED,
            old=old_status,
            new=item.status,
            operator_user_id=operator_user_id,
            reason=reason,
            old_expires_at=old_expiry.isoformat(),
            new_expires_at=expires_at.isoformat(),
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def inventory_for_player(
    db: Session, player_id: int, theater_id: int | None = None
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
            .options(selectinload(EntitlementItem.ledger_entries))
            .order_by(EntitlementItem.id)
        ).all()
    )
    return PlayerInventoryRead(player=player, items=items)


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
    if item_type.category != EntitlementItemCategory.GENERAL:
        raise EntitlementConflict("designation_item_manual_consumption_forbidden")
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
            EntitlementItem.expires_at > utcnow(),
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
            _ledger(
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
        select(EntitlementLedgerEntry, EntitlementItem, EntitlementItemType, PlayerProfile)
        .join(EntitlementItem, EntitlementItem.id == EntitlementLedgerEntry.item_id)
        .join(EntitlementItemType, EntitlementItemType.id == EntitlementItem.item_type_id)
        .join(PlayerProfile, PlayerProfile.id == EntitlementItem.owner_id)
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
            for ledger, item, item_type, player in page
        ],
        next_cursor=page[-1][0].id if len(rows) > limit else None,
    )


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
                designation.lifecycle_status != "fulfilled",
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
                    designation.lifecycle_status == "fulfilled",
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
        designation.lifecycle_status.not_in(("predesignated", "fulfilled")),
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
    now = now or utcnow()
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
    now = now or utcnow()
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


def void_item(db: Session, item_id: int, reason: str, operator_user_id: int) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if item.status == EntitlementItemStatus.REVOKED:
            raise EntitlementConflict("entitlement_already_revoked")
        if item.status == EntitlementItemStatus.CONSUMED:
            raise EntitlementConflict("entitlement_consumed_cannot_be_revoked")
        old = item.status
        item.status = EntitlementItemStatus.REVOKED
        item.current_designation_id = None
        _ledger(
            db,
            item,
            EntitlementEventType.REVOKED,
            old=old,
            new=item.status,
            operator_user_id=operator_user_id,
            reason=reason,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def restore_item(db: Session, item_id: int, reason: str, operator_user_id: int) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        if item.status != EntitlementItemStatus.REVOKED:
            raise EntitlementConflict("entitlement_not_revoked")
        old = item.status
        item.status = (
            EntitlementItemStatus.EXPIRED
            if item.expires_at <= utcnow()
            else EntitlementItemStatus.AVAILABLE
        )
        _ledger(
            db,
            item,
            EntitlementEventType.RESTORED,
            old=old,
            new=item.status,
            operator_user_id=operator_user_id,
            reason=reason,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise


def adjust_item(
    db: Session,
    item_id: int,
    *,
    expires_at: datetime | None,
    source_label: str | None,
    notes: str | None,
    reason: str,
    operator_user_id: int,
) -> EntitlementItem:
    try:
        item = _locked_item(db, item_id)
        changes = {}
        for field, value in (
            ("expires_at", expires_at),
            ("source_label", source_label),
            ("notes", notes),
        ):
            if value is not None and getattr(item, field) != value:
                changes[field] = {"old": str(getattr(item, field)), "new": str(value)}
                setattr(item, field, value)
        if not changes:
            raise EntitlementConflict("entitlement_adjustment_empty")
        _ledger(
            db,
            item,
            EntitlementEventType.ADJUSTED,
            old=item.status,
            new=item.status,
            operator_user_id=operator_user_id,
            reason=reason,
            changes=changes,
        )
        db.commit()
        db.refresh(item)
        return item
    except Exception:
        db.rollback()
        raise
