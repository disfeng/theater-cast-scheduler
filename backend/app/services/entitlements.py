import calendar
import json
import re
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now

from app.models.entities import (
    ActorRoleCapability,
    EntitlementItem,
    EntitlementItemType,
    EntitlementLedgerEntry,
    PlayerAlias,
    PlayerProfile,
    Role,
)
from app.models.enums import (
    EntitlementEventType,
    EntitlementGrantMode,
    PlayerStatus,
)
from app.services.entitlement_binding import EntitlementBindingError, validate_grant_mode
from app.schemas.entitlements import (
    PlayerMatchResult,
)


def utcnow() -> datetime:
    return utc_now()


class EntitlementError(RuntimeError):
    pass


class EntitlementNotFound(EntitlementError):
    pass


class EntitlementConflict(EntitlementError):
    pass


def validate_grant_binding(
    db: Session,
    theater_id: int | None,
    item_type: EntitlementItemType,
    bound_actor_id: int | None,
    grant_mode: EntitlementGrantMode | None = None,
) -> None:
    if grant_mode is not None:
        try:
            validate_grant_mode(item_type, grant_mode)
        except EntitlementBindingError as exc:
            raise EntitlementConflict(str(exc)) from exc
    requires_actor = item_type.binds_actor
    if requires_actor != (bound_actor_id is not None):
        code = (
            "entitlement_bound_actor_required"
            if requires_actor
            else "entitlement_actor_binding_invalid"
        )
        raise EntitlementConflict(code)
    if bound_actor_id is None:
        return
    capability = db.scalar(
        select(ActorRoleCapability.id)
        .join(Role, Role.id == ActorRoleCapability.role_id)
        .where(
            ActorRoleCapability.actor_id == bound_actor_id,
            Role.theater_id == theater_id,
        )
        .limit(1)
    )
    if capability is None:
        raise EntitlementConflict("entitlement_bound_actor_invalid")


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


# Compatibility facade: public imports remain stable while implementations live
# in focused modules. Import after shared helpers to avoid circular initialization.
from app.services.entitlement_grants import confirm_grant_batch  # noqa: E402
from app.services.entitlement_inventory import (  # noqa: E402
    inventory_for_player,
    list_entitlement_ledger,
    list_theater_inventory_summaries,
    manual_consume,
    preview_manual_consumption,
)
from app.services.entitlement_lifecycle import (  # noqa: E402
    adjust_item,
    consume_item,
    extend_item,
    release_item,
    reserve_item,
    restore_item,
    reverse_consumption,
    void_item,
)
from app.services.entitlement_reconciliation import (  # noqa: E402
    entitlement_reconciliation,
    reconciliation_drill,
)

__all__ = [
    "adjust_item",
    "confirm_grant_batch",
    "consume_item",
    "entitlement_reconciliation",
    "extend_item",
    "inventory_for_player",
    "list_entitlement_ledger",
    "list_theater_inventory_summaries",
    "manual_consume",
    "preview_manual_consumption",
    "reconciliation_drill",
    "release_item",
    "reserve_item",
    "restore_item",
    "reverse_consumption",
    "void_item",
]
