from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models.entities import (
    EntitlementGrantDraftItem,
    EntitlementItem,
    PlayerAlias,
    PlayerProfile,
    Theater,
)
from app.models.enums import (
    PlayerStatus,
)
from app.schemas.entitlements import (
    AliasCreate,
    BulkPlayerMatchRead,
    BulkPlayerMatchRequest,
    PlayerCreate,
    PlayerMatchResult,
    PlayerMergeRequest,
    PlayerRead,
    PlayerUpdate,
)
from app.services.entitlements import (
    EntitlementConflict,
    create_or_match_player,
    normalize_player_name,
)
from app.api.routes.admin_entitlement_common import _raise

router = APIRouter(prefix="/admin", tags=["admin_entitlements"])


@router.get("/player-profiles", response_model=list[PlayerRead])
def search_players(
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized = normalize_player_name(q)
    stmt = select(PlayerProfile).outerjoin(PlayerAlias).distinct().order_by(PlayerProfile.id)
    if normalized:
        stmt = stmt.where(
            or_(
                PlayerProfile.normalized_name.contains(normalized),
                PlayerAlias.normalized_alias.contains(normalized),
            )
        )
    return list(db.scalars(stmt.offset(offset).limit(limit)).all())


@router.post(
    "/theaters/{theater_id}/entitlement-grant-player-matches",
    response_model=list[BulkPlayerMatchRead],
)
def match_grant_players(
    theater_id: int,
    payload: BulkPlayerMatchRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(Theater, theater_id) is None:
        raise HTTPException(404, detail="theater_not_found")
    rows: list[BulkPlayerMatchRead] = []
    for name in payload.names:
        match = create_or_match_player(db, name)
        rows.append(BulkPlayerMatchRead(raw_name=name, **match.model_dump()))
    return rows


@router.post("/player-profiles", response_model=PlayerMatchResult)
def create_player(
    payload: PlayerCreate, _: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    try:
        result = create_or_match_player(db, payload.display_name)
        if len(result.candidates) > 1:
            raise HTTPException(409, detail="player_match_ambiguous")
        return result
    except EntitlementConflict as exc:
        _raise(exc)


@router.patch("/player-profiles/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: int,
    payload: PlayerUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.scalar(select(PlayerProfile).where(PlayerProfile.id == player_id).with_for_update())
    if player is None:
        raise HTTPException(404, detail="player_not_found")
    if player.status == PlayerStatus.MERGED:
        raise HTTPException(409, detail="player_merged")
    values = payload.model_dump(exclude_unset=True)
    requested_status = values.get("status")
    if requested_status is not None:
        if requested_status != PlayerStatus.ACTIVE or player.status != PlayerStatus.PROVISIONAL:
            raise HTTPException(409, detail="player_status_transition_invalid")
    if "display_name" in values:
        values["normalized_name"] = normalize_player_name(values["display_name"])
        primary_claim = db.scalar(
            select(PlayerAlias)
            .where(PlayerAlias.player_id == player.id, PlayerAlias.is_primary.is_(True))
            .with_for_update()
        )
        if primary_claim is None:
            primary_claim = PlayerAlias(player_id=player.id, is_primary=True)
            db.add(primary_claim)
        primary_claim.alias = values["display_name"]
        primary_claim.normalized_alias = values["normalized_name"]
    for key, value in values.items():
        setattr(player, key, value)
    try:
        db.commit()
        db.refresh(player)
        return player
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_name_already_exists") from exc


@router.post("/player-profiles/{player_id}/aliases", response_model=PlayerRead)
def add_alias(
    player_id: int,
    payload: AliasCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.get(PlayerProfile, player_id)
    if player is None:
        raise HTTPException(404, detail="player_not_found")
    if player.status == PlayerStatus.MERGED:
        raise HTTPException(409, detail="player_merged")
    db.add(
        PlayerAlias(
            player_id=player_id,
            alias=payload.alias,
            normalized_alias=normalize_player_name(payload.alias),
            is_primary=False,
        )
    )
    try:
        db.commit()
        db.refresh(player)
        return player
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_alias_already_exists") from exc


@router.post("/player-profiles/{target_id}/merge", response_model=PlayerRead)
def merge_player(
    target_id: int,
    payload: PlayerMergeRequest,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        players = list(
            db.scalars(
                select(PlayerProfile)
                .where(PlayerProfile.id.in_([target_id, payload.source_player_id]))
                .with_for_update()
            ).all()
        )
        by_id = {player.id: player for player in players}
        target, source = by_id.get(target_id), by_id.get(payload.source_player_id)
        if not target or not source:
            raise HTTPException(404, detail="player_not_found")
        if target.id == source.id:
            raise HTTPException(409, detail="player_merge_same_profile")
        if target.status == PlayerStatus.MERGED or source.status not in {
            PlayerStatus.ACTIVE,
            PlayerStatus.PROVISIONAL,
        }:
            raise HTTPException(409, detail="player_merge_invalid_status")
        if target.status != PlayerStatus.ACTIVE:
            raise HTTPException(409, detail="player_not_confirmed")
        db.execute(
            update(EntitlementItem)
            .where(EntitlementItem.owner_id == source.id)
            .values(owner_id=target.id)
        )
        db.execute(
            update(EntitlementGrantDraftItem)
            .where(EntitlementGrantDraftItem.player_id == source.id)
            .values(player_id=target.id)
        )
        db.execute(
            update(PlayerAlias)
            .where(PlayerAlias.player_id == source.id)
            .values(player_id=target.id)
        )
        db.execute(
            update(PlayerAlias)
            .where(
                PlayerAlias.player_id == target.id,
                PlayerAlias.normalized_alias != target.normalized_name,
            )
            .values(is_primary=False)
        )
        source.status, source.merged_into_id = PlayerStatus.MERGED, target.id
        db.commit()
        db.refresh(target)
        return target
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="player_merge_conflict") from exc
