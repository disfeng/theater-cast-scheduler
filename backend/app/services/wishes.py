import hashlib
import json
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    Performance,
    PerformancePlayer,
    Role,
    Wish,
    WishLifecycleEvent,
)


class WishConflict(ValueError):
    pass


def _hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def active_scope_key(
    performance_id: int, performance_player_id: int, actor_id: int, role_id: int
) -> str:
    return hashlib.sha256(
        f"{performance_id}:{performance_player_id}:{actor_id}:{role_id}".encode()
    ).hexdigest()


def _snapshot(db: Session, row: Wish) -> dict:
    actor, role = db.get(Actor, row.actor_id), db.get(Role, row.role_id)
    return {
        name: getattr(row, name)
        for name in (
            "id",
            "player_name",
            "performance_id",
            "performance_player_id",
            "actor_id",
            "role_id",
            "note",
            "status",
            "failure_reason",
            "version",
        )
    } | {
        "actor_name": actor.display_name,
        "role_name": role.name,
    }


def _replay(db: Session, action: str, key: str, operator: int, payload: dict):
    event = db.scalar(
        select(WishLifecycleEvent).where(
            WishLifecycleEvent.action == action, WishLifecycleEvent.idempotency_key == key
        )
    )
    if event is None:
        return None
    if event.operator_user_id != operator or event.request_hash != _hash(payload):
        raise WishConflict("wish_idempotency_conflict")
    replay = SimpleNamespace(**event.result_snapshot)
    replay._wish_api_snapshot = event.result_snapshot
    return replay


def _audit(
    db: Session,
    row: Wish,
    action: str,
    key: str,
    operator: int,
    payload: dict,
    old: str | None,
    note: str | None = None,
) -> None:
    db.add(
        WishLifecycleEvent(
            wish_id=row.id,
            operator_user_id=operator,
            action=action,
            idempotency_key=key,
            request_hash=_hash(payload),
            result_snapshot=_snapshot(db, row),
            from_status=old,
            to_status=row.status,
            note=note,
        )
    )


def create_wish(
    db: Session,
    performance_id: int,
    performance_player_id: int,
    actor_id: int,
    role_id: int,
    note: str | None,
    expected_version: int,
    idempotency_key: str,
    operator_user_id: int,
) -> Wish:
    payload = {
        "performance_id": performance_id,
        "performance_player_id": performance_player_id,
        "actor_id": actor_id,
        "role_id": role_id,
        "note": note,
        "expected_version": expected_version,
    }
    replay = _replay(db, "create", idempotency_key, operator_user_id, payload)
    if replay:
        return replay
    if expected_version != 0:
        raise WishConflict("wish_version_conflict")
    performance = db.get(Performance, performance_id)
    if performance is None:
        raise WishConflict("performance_not_found")
    player = db.get(PerformancePlayer, performance_player_id)
    if player is None or player.performance_id != performance_id or not player.is_active:
        raise WishConflict("wish_performance_player_scope_mismatch")
    role = db.get(Role, role_id)
    if role is None or role.theater_id != performance.theater_id:
        raise WishConflict("wish_role_outside_performance_theater")
    if db.get(Actor, actor_id) is None:
        raise WishConflict("actor_not_found")
    if (
        db.scalar(
            select(ActorRoleCapability.id).where(
                ActorRoleCapability.actor_id == actor_id, ActorRoleCapability.role_id == role_id
            )
        )
        is None
    ):
        raise WishConflict("actor_role_capability_missing")
    scope_key = active_scope_key(performance_id, performance_player_id, actor_id, role_id)
    if db.scalar(select(Wish.id).where(Wish.active_scope_key == scope_key)) is not None:
        raise WishConflict("wish_active_duplicate")
    row = Wish(
        player_name=player.player_name_snapshot,
        performance_id=performance_id,
        performance_player_id=performance_player_id,
        actor_id=actor_id,
        role_id=role_id,
        note=note.strip() if note and note.strip() else None,
        status="active",
        version=1,
        active_scope_key=scope_key,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        raise WishConflict("wish_active_duplicate") from exc
    _audit(db, row, "create", idempotency_key, operator_user_id, payload, None)
    db.flush()
    return row


def set_wish_status(
    db: Session,
    wish_id: int,
    status: str,
    reason: str | None,
    operator_user_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
    action: str,
) -> Wish:
    payload = {
        "wish_id": wish_id,
        "status": status,
        "reason": reason,
        "expected_version": expected_version,
    }
    replay = _replay(db, action, idempotency_key, operator_user_id, payload)
    if replay:
        return replay
    row = db.scalar(select(Wish).where(Wish.id == wish_id).with_for_update())
    if row is None or row.performance_id is None:
        raise WishConflict("wish_not_found")
    if row.version != expected_version:
        raise WishConflict("wish_version_conflict")
    old = row.status
    row.status = status
    row.failure_reason = reason if status == "cancelled" else None
    row.version += 1
    row.active_scope_key = (
        active_scope_key(row.performance_id, row.performance_player_id, row.actor_id, row.role_id)
        if status in {"active", "accepted"}
        else None
    )
    try:
        db.flush()
    except IntegrityError as exc:
        raise WishConflict("wish_active_duplicate") from exc
    _audit(db, row, action, idempotency_key, operator_user_id, payload, old, reason)
    db.flush()
    return row


def cancel_wish(
    db: Session,
    wish_id: int,
    reason: str,
    operator_user_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> Wish:
    reason = reason.strip()
    if not reason:
        raise WishConflict("wish_cancel_reason_required")
    return set_wish_status(
        db,
        wish_id,
        "cancelled",
        reason.strip(),
        operator_user_id,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        action="cancel",
    )


def update_wish(
    db: Session,
    wish_id: int,
    actor_id: int,
    role_id: int,
    note: str | None,
    operator_user_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> Wish:
    payload = {
        "wish_id": wish_id,
        "actor_id": actor_id,
        "role_id": role_id,
        "note": note,
        "expected_version": expected_version,
    }
    replay = _replay(db, "update", idempotency_key, operator_user_id, payload)
    if replay:
        return replay
    row = db.scalar(select(Wish).where(Wish.id == wish_id).with_for_update())
    if row is None or row.performance_id is None:
        raise WishConflict("wish_not_found")
    if row.version != expected_version:
        raise WishConflict("wish_version_conflict")
    performance = db.get(Performance, row.performance_id)
    role = db.get(Role, role_id)
    if performance is None or role is None or role.theater_id != performance.theater_id:
        raise WishConflict("wish_role_outside_performance_theater")
    if db.get(Actor, actor_id) is None:
        raise WishConflict("actor_not_found")
    if db.scalar(
        select(ActorRoleCapability.id).where(
            ActorRoleCapability.actor_id == actor_id,
            ActorRoleCapability.role_id == role_id,
        )
    ) is None:
        raise WishConflict("actor_role_capability_missing")
    old = row.status
    row.actor_id = actor_id
    row.role_id = role_id
    row.note = note.strip() if note and note.strip() else None
    row.version += 1
    if row.status in {"active", "accepted"}:
        row.active_scope_key = active_scope_key(
            row.performance_id, row.performance_player_id, actor_id, role_id
        )
    try:
        db.flush()
    except IntegrityError as exc:
        raise WishConflict("wish_active_duplicate") from exc
    _audit(db, row, "update", idempotency_key, operator_user_id, payload, old, row.note)
    db.flush()
    return row


def accept_wish(
    db: Session,
    wish_id: int,
    note: str | None,
    operator_user_id: int,
    *,
    expected_version: int,
    idempotency_key: str,
) -> Wish:
    return set_wish_status(
        db,
        wish_id,
        "accepted",
        note.strip() if note and note.strip() else None,
        operator_user_id,
        expected_version=expected_version,
        idempotency_key=idempotency_key,
        action="accept",
    )
