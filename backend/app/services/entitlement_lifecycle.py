"""Focused entitlement service extracted from the legacy facade."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session


from app.models.entities import (
    EntitlementItem,
    EntitlementLedgerEntry,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
)


from app.services import entitlements as _legacy

EntitlementError = _legacy.EntitlementError
EntitlementNotFound = _legacy.EntitlementNotFound
EntitlementConflict = _legacy.EntitlementConflict


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
        if item.expires_at <= _legacy.utcnow():
            raise EntitlementConflict("entitlement_expired")
        old = item.status
        item.status, item.current_designation_id = EntitlementItemStatus.RESERVED, designation_id
        _legacy._ledger(
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
            if item.expires_at <= _legacy.utcnow()
            else EntitlementItemStatus.AVAILABLE
        )
        item.current_designation_id = None
        event = (
            EntitlementEventType.EXPIRED
            if item.status == EntitlementItemStatus.EXPIRED
            else EntitlementEventType.RELEASED
        )
        _legacy._ledger(
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
        _legacy._ledger(
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


def reverse_consumption(
    db: Session,
    ledger_entry_id: int,
    designation_id: int,
    reason: str,
    operator_user_id: int,
    idempotency_key: str,
    *,
    commit: bool = True,
) -> EntitlementItem:
    try:
        existing = db.scalar(
            select(EntitlementLedgerEntry).where(
                EntitlementLedgerEntry.reverses_entry_id == ledger_entry_id
            )
        )
        if existing is not None:
            return _locked_item(db, existing.item_id)
        source = db.scalar(
            select(EntitlementLedgerEntry)
            .where(EntitlementLedgerEntry.id == ledger_entry_id)
            .with_for_update()
        )
        if source is None or source.event_type != EntitlementEventType.CONSUMED:
            raise EntitlementConflict("consumption_ledger_not_found")
        item = _locked_item(db, source.item_id)
        if item.status != EntitlementItemStatus.CONSUMED:
            raise EntitlementConflict("entitlement_not_consumed")
        old = item.status
        item.status = (
            EntitlementItemStatus.EXPIRED
            if item.expires_at <= _legacy.utcnow()
            else EntitlementItemStatus.AVAILABLE
        )
        item.current_designation_id = None
        db.add(
            EntitlementLedgerEntry(
                theater_id=item.theater_id,
                item_id=item.id,
                event_type=EntitlementEventType.REVERSED,
                from_status=old,
                to_status=item.status,
                performance_id=source.performance_id,
                designation_id=designation_id,
                reason=reason,
                idempotency_key=idempotency_key,
                operator_user_id=operator_user_id,
                reverses_entry_id=source.id,
                note=_legacy._note(operator_user_id=operator_user_id, reason=reason),
            )
        )
        if commit:
            db.commit()
            db.refresh(item)
        else:
            db.flush()
        return item
    except Exception:
        if commit:
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
        if item.status == EntitlementItemStatus.EXPIRED and expires_at > _legacy.utcnow():
            item.status = EntitlementItemStatus.AVAILABLE
        _legacy._ledger(
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
        _legacy._ledger(
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
            if item.expires_at <= _legacy.utcnow()
            else EntitlementItemStatus.AVAILABLE
        )
        _legacy._ledger(
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
        _legacy._ledger(
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


__all__ = [
    "reserve_item",
    "release_item",
    "consume_item",
    "reverse_consumption",
    "extend_item",
    "void_item",
    "restore_item",
    "adjust_item",
]
