"""Focused entitlement service extracted from the legacy facade."""

import calendar
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from app.models.entities import (
    EntitlementGrantBatch,
    EntitlementItem,
    EntitlementItemType,
    PlayerProfile,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementItemStatus,
    GrantBatchStatus,
    PlayerStatus,
)


from app.services import entitlements as _legacy

EntitlementError = _legacy.EntitlementError
EntitlementNotFound = _legacy.EntitlementNotFound
EntitlementConflict = _legacy.EntitlementConflict


def _add_months(value: datetime, months: int) -> datetime:
    total = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(total, 12)
    day = min(value.day, calendar.monthrange(year, month0 + 1)[1])
    return value.replace(year=year, month=month0 + 1, day=day)


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
        now = _legacy.utcnow()
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
            _legacy.validate_grant_binding(
                db, batch.theater_id, item_type, draft.bound_actor_id, batch.grant_mode
            )
            if draft.bound_actor_id != batch.bound_actor_id:
                raise EntitlementConflict("entitlement_actor_binding_invalid")
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
                bound_actor_id=draft.bound_actor_id,
                binds_beneficiary_snapshot=item_type.binds_beneficiary,
                binds_actor_snapshot=item_type.binds_actor,
            )
            db.add(item)
            if item_type.binding_locked_at is None:
                item_type.binding_locked_at = now
            _legacy._ledger(
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


__all__ = ["confirm_grant_batch"]
