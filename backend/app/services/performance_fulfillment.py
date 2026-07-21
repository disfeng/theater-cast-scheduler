import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Designation,
    DesignationLifecycleEvent,
    EntitlementLedgerEntry,
    Performance,
    Wish,
    WishLifecycleEvent,
)
from app.models.enums import EntitlementEventType, PerformanceStatus
from app.services.entitlements import reverse_consumption


def _hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def fulfill_ended_performance(
    db: Session,
    performance_id: int,
    operator_user_id: int,
    *,
    now: datetime,
    idempotency_key: str,
) -> dict[str, int]:
    """Close effective wishes/designations after the performance start time has passed."""
    performance = db.get(Performance, performance_id)
    if performance is None:
        raise ValueError("performance_not_found")
    starts_at = datetime.combine(
        performance.performance_date, performance.start_time_snapshot
    )
    if now < starts_at:
        raise ValueError("performance_not_ended")

    payload = {"performance_id": performance_id, "starts_at": starts_at.isoformat()}
    request_hash = _hash(payload)
    counts = {"designations": 0, "wishes": 0}

    designations = list(
        db.scalars(
            select(Designation)
            .where(
                Designation.performance_id == performance_id,
                Designation.lifecycle_status == "effective",
            )
            .order_by(Designation.id)
            .with_for_update()
        )
    )
    for row in designations:
        event_key = f"{idempotency_key}:designation:{row.id}"
        if db.scalar(
            select(DesignationLifecycleEvent.id).where(
                DesignationLifecycleEvent.action == "performance_fulfilled",
                DesignationLifecycleEvent.idempotency_key == event_key,
            )
        ):
            continue
        old = row.lifecycle_status
        row.lifecycle_status = "fulfilled"
        row.version += 1
        db.add(
            DesignationLifecycleEvent(
                designation_id=row.id,
                operator_user_id=operator_user_id,
                action="performance_fulfilled",
                idempotency_key=event_key,
                request_hash=request_hash,
                result_snapshot={
                    "id": row.id,
                    "performance_id": performance_id,
                    "lifecycle_status": row.lifecycle_status,
                    "version": row.version,
                },
                from_status=old,
                to_status=row.lifecycle_status,
                entitlement_item_id=row.entitlement_item_id,
            )
        )
        counts["designations"] += 1

    wishes = list(
        db.scalars(
            select(Wish)
            .where(Wish.performance_id == performance_id, Wish.status == "effective")
            .order_by(Wish.id)
            .with_for_update()
        )
    )
    for row in wishes:
        event_key = f"{idempotency_key}:wish:{row.id}"
        if db.scalar(
            select(WishLifecycleEvent.id).where(
                WishLifecycleEvent.action == "performance_fulfilled",
                WishLifecycleEvent.idempotency_key == event_key,
            )
        ):
            continue
        old = row.status
        row.status = "fulfilled"
        row.version += 1
        db.add(
            WishLifecycleEvent(
                wish_id=row.id,
                operator_user_id=operator_user_id,
                action="performance_fulfilled",
                idempotency_key=event_key,
                request_hash=request_hash,
                result_snapshot={
                    "id": row.id,
                    "performance_id": performance_id,
                    "status": row.status,
                    "version": row.version,
                },
                from_status=old,
                to_status=row.status,
            )
        )
        counts["wishes"] += 1

    db.flush()
    return counts


def reconcile_effective_business(
    db: Session,
    performance_ids: list[int],
    assigned: set[tuple[int, int, int]],
    operator_user_id: int,
    *,
    idempotency_key: str,
) -> dict[str, int]:
    """Rollback effective business records no longer backed by a published cast."""
    performances = {
        row.id: row
        for row in db.scalars(
            select(Performance).where(Performance.id.in_(performance_ids)).with_for_update()
        )
    }
    counts = {"designations": 0, "wishes": 0, "entitlements": 0}
    rows = list(
        db.scalars(
            select(Designation)
            .where(
                Designation.performance_id.in_(performance_ids),
                Designation.lifecycle_status == "effective",
            )
            .order_by(Designation.id)
            .with_for_update()
        )
    )
    for row in rows:
        if (row.performance_id, row.role_id, row.actor_id) in assigned:
            continue
        performance = performances[row.performance_id]
        cancelled = performance.status == PerformanceStatus.CANCELLED
        action = "performance_cancelled" if cancelled else "cast_changed"
        destination = "cancelled" if cancelled else "unsatisfied"
        source = db.scalar(
            select(EntitlementLedgerEntry)
            .where(
                EntitlementLedgerEntry.designation_id == row.id,
                EntitlementLedgerEntry.event_type == EntitlementEventType.CONSUMED,
            )
            .order_by(EntitlementLedgerEntry.id.desc())
            .with_for_update()
        )
        if source is not None:
            reverse_consumption(
                db,
                source.id,
                row.id,
                action,
                operator_user_id,
                f"{idempotency_key}:reverse:{row.id}",
                commit=False,
            )
            counts["entitlements"] += 1
        old = row.lifecycle_status
        row.lifecycle_status = destination
        row.failure_reason = action
        row.version += 1
        event_key = f"{idempotency_key}:designation:{row.id}:{action}"
        db.add(
            DesignationLifecycleEvent(
                designation_id=row.id,
                operator_user_id=operator_user_id,
                action=action,
                idempotency_key=event_key,
                request_hash=_hash({"performance_id": row.performance_id, "action": action}),
                result_snapshot={"id": row.id, "lifecycle_status": destination},
                from_status=old,
                to_status=destination,
                entitlement_item_id=row.entitlement_item_id,
                note=action,
            )
        )
        counts["designations"] += 1

    wishes = list(
        db.scalars(
            select(Wish)
            .where(Wish.performance_id.in_(performance_ids), Wish.status == "effective")
            .order_by(Wish.id)
            .with_for_update()
        )
    )
    for row in wishes:
        if (row.performance_id, row.role_id, row.actor_id) in assigned:
            continue
        performance = performances[row.performance_id]
        cancelled = performance.status == PerformanceStatus.CANCELLED
        action = "performance_cancelled" if cancelled else "cast_changed"
        destination = "cancelled" if cancelled else "unsatisfied"
        old = row.status
        row.status = destination
        row.failure_reason = action
        row.version += 1
        db.add(
            WishLifecycleEvent(
                wish_id=row.id,
                operator_user_id=operator_user_id,
                action=action,
                idempotency_key=f"{idempotency_key}:wish:{row.id}:{action}",
                request_hash=_hash({"performance_id": row.performance_id, "action": action}),
                result_snapshot={"id": row.id, "status": destination},
                from_status=old,
                to_status=destination,
                note=action,
            )
        )
        counts["wishes"] += 1
    db.flush()
    return counts
