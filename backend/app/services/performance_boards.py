from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.time import utc_now

from app.models.entities import (
    Actor,
    ActorRoleCapability,
    BoardDraftItem,
    Designation,
    EntitlementItem,
    Performance,
    PerformanceBoard,
    PerformanceBoardRevision,
    PerformancePlayer,
    PlayerProfile,
    Role,
    Wish,
)
from app.models.enums import (
    BoardChangeType,
    BoardItemKind,
    BoardParserType,
    BoardRevisionStatus,
    BoardValidationStatus,
    DesignationType,
    EntitlementItemStatus,
    PlayerStatus,
)
from app.schemas.performance_boards import BoardItemPatch
from app.services.entitlements import _exact_match_players, normalize_player_name
from app.services.import_parser import parse_group_board, parse_player_registration
from app.services.ai_parser import (
    AiParserError,
    BoardParseContext,
    OpenAICompatibleBoardParser,
    ParsedBoardPayload,
)
from app.services.ai_parser import MAX_RAW_TEXT
from app.services.ai_settings import decrypt_api_key, get_ai_settings
from app.services.wishes import create_wish, set_wish_status


class BoardConflict(ValueError):
    pass


def _candidate_descriptors(players: list[PlayerProfile]) -> list[dict] | None:
    return [
        {"field": "matched_player_id", "id": player.id, "label": player.display_name}
        for player in players
    ] or None


def _candidate_ids(candidates: list | None) -> list[int]:
    return [value["id"] if isinstance(value, dict) else value for value in (candidates or [])]


def _exact_actor_role_match(
    db: Session, performance_id: int, actor_name: str, role_name: str
) -> tuple[int | None, int | None, bool]:
    performance = db.get(Performance, performance_id)
    if performance is None:
        return None, None, False
    actor = db.scalar(select(Actor).where(Actor.display_name == actor_name.strip()))
    role = db.scalar(
        select(Role).where(
            Role.theater_id == performance.theater_id,
            Role.name == role_name.strip(),
            Role.is_active.is_(True),
        )
    )
    capable = bool(
        actor
        and role
        and db.scalar(
            select(ActorRoleCapability.id).where(
                ActorRoleCapability.actor_id == actor.id,
                ActorRoleCapability.role_id == role.id,
            )
        )
    )
    return actor.id if actor else None, role.id if role else None, capable


def _content(item: BoardDraftItem) -> tuple:
    return (
        item.item_kind,
        item.player_name,
        item.player_character_name,
        item.paired_role_name,
        item.relation_label,
        item.theater_visit_ordinal,
        item.character_visit_ordinal,
        item.actor_name_raw,
        item.role_name_raw,
        item.note,
        item.matched_player_id,
        item.actor_id,
        item.role_id,
    )


def _parse_items(db: Session, performance_id: int, raw_text: str) -> list[BoardDraftItem]:
    draft = parse_group_board(raw_text)
    items: list[BoardDraftItem] = []
    section = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if line.startswith("#玩家信息"):
            section = "players"
            continue
        if line.startswith("#"):
            section = None
            continue
        if section == "players":
            parsed = parse_player_registration(line)
            if parsed:
                matches = _exact_match_players(db, normalize_player_name(parsed.player_name))
                items.append(
                    BoardDraftItem(
                        item_kind=BoardItemKind.PLAYER,
                        change_type=BoardChangeType.ADDED,
                        stable_key=f"player:{parsed.player_character_name}",
                        raw_line=line,
                        player_name=parsed.player_name,
                        player_character_name=parsed.player_character_name,
                        paired_role_name=parsed.paired_role_name,
                        relation_label=parsed.relation_label,
                        theater_visit_ordinal=parsed.theater_visit_ordinal,
                        character_visit_ordinal=parsed.character_visit_ordinal,
                        matched_player_id=matches[0].id if len(matches) == 1 else None,
                        candidates=_candidate_descriptors(matches) if len(matches) > 1 else None,
                        confidence={"player_name": 1.0 if len(matches) == 1 else 0.5},
                        validation_status=(
                            BoardValidationStatus.AMBIGUOUS
                            if len(matches) > 1
                            else BoardValidationStatus.VALID
                        ),
                        failure_reason="player_match_ambiguous" if len(matches) > 1 else None,
                    )
                )
    for wish in draft.wishes:
        matches = _exact_match_players(db, normalize_player_name(wish.player_name))
        actor_id, role_id, capable = _exact_actor_role_match(
            db, performance_id, wish.actor_name, wish.role_name
        )
        valid = len(matches) == 1 and capable
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.WISH,
                change_type=BoardChangeType.ADDED,
                stable_key=f"wish:{wish.player_name}:{wish.actor_name}:{wish.role_name}",
                raw_line=wish.raw_line,
                player_name=wish.player_name,
                actor_name_raw=wish.actor_name,
                role_name_raw=wish.role_name,
                note=wish.raw_note,
                matched_player_id=matches[0].id if len(matches) == 1 else None,
                actor_id=actor_id,
                role_id=role_id,
                candidates=_candidate_descriptors(matches) if len(matches) > 1 else None,
                confidence={
                    "player_name": 1.0 if len(matches) == 1 else (0.5 if matches else 0.0),
                    "actor_id": 0.0,
                    "role_id": 0.0,
                },
                validation_status=BoardValidationStatus.VALID
                if valid
                else BoardValidationStatus.AMBIGUOUS
                if len(matches) > 1
                else BoardValidationStatus.INVALID,
                failure_reason="player_match_ambiguous"
                if len(matches) > 1
                else None
                if valid
                else "entity_matching_required",
            )
        )
    for designation in draft.designation_suggestions:
        matches = (
            _exact_match_players(db, normalize_player_name(designation.player_name))
            if designation.player_name
            else []
        )
        actor_id, role_id, capable = _exact_actor_role_match(
            db, performance_id, designation.actor_name, designation.role_name
        )
        valid = len(matches) == 1 and capable
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.DESIGNATION,
                change_type=BoardChangeType.ADDED,
                stable_key=f"designation:{designation.actor_name}:{designation.role_name}",
                raw_line=designation.raw_line,
                actor_name_raw=designation.actor_name,
                role_name_raw=designation.role_name,
                player_name=designation.player_name,
                matched_player_id=matches[0].id if len(matches) == 1 else None,
                actor_id=actor_id,
                role_id=role_id,
                candidates=_candidate_descriptors(matches) if len(matches) > 1 else None,
                confidence={
                    "player_name": 1.0 if len(matches) == 1 else (0.5 if matches else 0.0),
                    "actor_id": 0.0,
                    "role_id": 0.0,
                },
                validation_status=BoardValidationStatus.VALID
                if valid
                else BoardValidationStatus.AMBIGUOUS
                if len(matches) > 1
                else BoardValidationStatus.INVALID,
                failure_reason="player_match_ambiguous"
                if len(matches) > 1
                else None
                if valid
                else "entity_matching_required",
            )
        )
    for index, line in enumerate(draft.unresolved_lines):
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.UNRESOLVED,
                change_type=BoardChangeType.ADDED,
                stable_key=f"unresolved:{index}:{line}",
                raw_line=line,
                validation_status=BoardValidationStatus.INVALID,
                failure_reason="unrecognized_line",
            )
        )
    counts = Counter(item.stable_key for item in items)
    unique: list[BoardDraftItem] = []
    seen: set[str] = set()
    for item in items:
        if item.stable_key in seen:
            continue
        seen.add(item.stable_key)
        if counts[item.stable_key] > 1:
            item.validation_status = BoardValidationStatus.INVALID
            item.failure_reason = "duplicate_stable_key"
        unique.append(item)
    return unique


def _allocate_revision(db: Session, performance_id: int) -> tuple[PerformanceBoard, int]:
    if db.get(Performance, performance_id) is None:
        raise LookupError("performance_not_found")
    board = db.scalar(
        select(PerformanceBoard)
        .where(PerformanceBoard.performance_id == performance_id)
        .with_for_update()
    )
    if board is None:
        board = PerformanceBoard(performance_id=performance_id, next_revision_number=2)
        db.add(board)
        db.flush()
        return board, 1
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        number = db.scalar(
            update(PerformanceBoard)
            .where(PerformanceBoard.id == board.id)
            .values(next_revision_number=PerformanceBoard.next_revision_number + 1)
            .returning(PerformanceBoard.next_revision_number - 1)
        )
        db.refresh(board)
        return board, number
    number = board.next_revision_number
    board.next_revision_number = number + 1
    db.flush()
    return board, number


def _retry_revision_creation(db: Session, operation) -> PerformanceBoardRevision:
    for attempt in range(3):
        try:
            revision = operation()
            db.add(revision)
            db.flush()
            diff_revision(db, revision.id)
            db.commit()
            db.refresh(revision)
            return revision
        except (IntegrityError, OperationalError) as exc:
            db.rollback()
            if attempt == 2:
                raise BoardConflict("board_revision_allocation_conflict") from exc
    raise BoardConflict("board_revision_allocation_conflict")


def create_board_revision(
    db: Session, performance_id: int, raw_text: str, operator_user_id: int | None
) -> PerformanceBoardRevision:
    if len(raw_text) > MAX_RAW_TEXT:
        raise ValueError("board_raw_text_too_large")

    def operation():
        board, number = _allocate_revision(db, performance_id)
        return PerformanceBoardRevision(
            board=board,
            revision_number=number,
            raw_text=raw_text,
            parser_type=BoardParserType.DETERMINISTIC,
            status=BoardRevisionStatus.REVIEW_REQUIRED,
            created_by=operator_user_id,
            parsed_payload={"parser": "deterministic"},
            draft_items=_parse_items(db, performance_id, raw_text),
        )

    return _retry_revision_creation(db, operation)


def _ai_draft_items(db: Session, payload: ParsedBoardPayload) -> list[BoardDraftItem]:
    items: list[BoardDraftItem] = []
    for player in payload.players:
        matches = _exact_match_players(db, normalize_player_name(player.player_name))
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.PLAYER,
                change_type=BoardChangeType.ADDED,
                stable_key=f"player:{player.player_character_name}",
                raw_line=player.evidence,
                player_name=player.player_name,
                player_character_name=player.player_character_name,
                paired_role_name=player.paired_role_name,
                relation_label=player.relation_label,
                theater_visit_ordinal=player.theater_visit_ordinal,
                character_visit_ordinal=player.character_visit_ordinal,
                matched_player_id=matches[0].id if len(matches) == 1 else None,
                candidates=_candidate_descriptors(matches) if len(matches) > 1 else None,
                confidence=player.confidence,
                validation_status=BoardValidationStatus.VALID
                if len(matches) <= 1
                else BoardValidationStatus.AMBIGUOUS,
            )
        )
    for wish in payload.wishes:
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.WISH,
                change_type=BoardChangeType.ADDED,
                stable_key=f"wish:{wish.player_name}:{wish.actor_name}:{wish.role_name}",
                raw_line=wish.evidence,
                player_name=wish.player_name,
                actor_name_raw=wish.actor_name,
                role_name_raw=wish.role_name,
                note=wish.note,
                confidence=wish.confidence,
                validation_status=BoardValidationStatus.INVALID,
                failure_reason="entity_matching_required",
            )
        )
    for designation in payload.designations:
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.DESIGNATION,
                change_type=BoardChangeType.ADDED,
                stable_key=f"designation:{designation.actor_name}:{designation.role_name}",
                raw_line=designation.evidence,
                player_name=designation.player_name,
                actor_name_raw=designation.actor_name,
                role_name_raw=designation.role_name,
                note=designation.source_note,
                confidence=designation.confidence,
                validation_status=BoardValidationStatus.INVALID,
                failure_reason="player_identity_required"
                if not designation.player_name
                else "entity_matching_required",
            )
        )
    for index, line in enumerate(payload.unresolved_lines):
        items.append(
            BoardDraftItem(
                item_kind=BoardItemKind.UNRESOLVED,
                change_type=BoardChangeType.ADDED,
                stable_key=f"unresolved:{index}:{line}",
                raw_line=line,
                validation_status=BoardValidationStatus.INVALID,
                failure_reason="unrecognized_line",
            )
        )
    return items


async def create_board_revision_with_ai(
    db: Session, performance_id: int, raw_text: str, operator_user_id: int | None
) -> PerformanceBoardRevision:
    config = get_ai_settings(db)
    if not config.enabled:
        return create_board_revision(db, performance_id, raw_text, operator_user_id)
    try:
        key = decrypt_api_key(config)
        if not key:
            raise ValueError("api_key_unavailable")
        parser = OpenAICompatibleBoardParser(
            endpoint=config.endpoint,
            api_key=key,
            model=config.model_name,
            timeout_seconds=config.timeout_seconds,
        )
        payload = await parser.parse(raw_text, BoardParseContext(performance_id=performance_id))
    except (AiParserError, ValueError):
        return create_board_revision(db, performance_id, raw_text, operator_user_id)

    def operation():
        board, number = _allocate_revision(db, performance_id)
        return PerformanceBoardRevision(
            board=board,
            revision_number=number,
            raw_text=raw_text,
            parser_type=BoardParserType.AI,
            status=BoardRevisionStatus.REVIEW_REQUIRED,
            created_by=operator_user_id,
            provider_name="openai-compatible",
            model_name=config.model_name,
            prompt_version=config.prompt_version,
            parsed_payload=payload.model_dump(),
            draft_items=_ai_draft_items(db, payload),
        )

    return _retry_revision_creation(db, operation)


def diff_revision(db: Session, revision_id: int) -> list[BoardDraftItem]:
    revision = db.get(PerformanceBoardRevision, revision_id)
    if revision is None:
        raise LookupError("board_revision_not_found")
    current = revision.board.current_revision
    if current is None or current.id == revision.id:
        return revision.draft_items
    prior = {
        item.stable_key: item
        for item in current.draft_items
        if item.change_type != BoardChangeType.REMOVED
    }
    present = {item.stable_key: item for item in revision.draft_items}
    for key, item in present.items():
        previous = prior.get(key)
        item.change_type = (
            BoardChangeType.ADDED
            if previous is None
            else (
                BoardChangeType.UNCHANGED
                if _content(item) == _content(previous)
                else BoardChangeType.MODIFIED
            )
        )
        if previous is not None:
            item.designation_id = previous.designation_id
            item.wish_id = previous.wish_id
    for key, previous in prior.items():
        if key not in present:
            revision.draft_items.append(
                BoardDraftItem(
                    item_kind=previous.item_kind,
                    change_type=BoardChangeType.REMOVED,
                    stable_key=key,
                    raw_line=previous.raw_line,
                    player_name=previous.player_name,
                    player_character_name=previous.player_character_name,
                    paired_role_name=previous.paired_role_name,
                    relation_label=previous.relation_label,
                    theater_visit_ordinal=previous.theater_visit_ordinal,
                    character_visit_ordinal=previous.character_visit_ordinal,
                    actor_name_raw=previous.actor_name_raw,
                    role_name_raw=previous.role_name_raw,
                    note=previous.note,
                    matched_player_id=previous.matched_player_id,
                    actor_id=previous.actor_id,
                    role_id=previous.role_id,
                    designation_id=previous.designation_id,
                    wish_id=previous.wish_id,
                    validation_status=BoardValidationStatus.VALID,
                )
            )
    db.flush()
    return revision.draft_items


def _canonical_active_player(db: Session, player_id: int) -> PlayerProfile:
    player = db.get(PlayerProfile, player_id)
    visited: set[int] = set()
    while player is not None and player.status == PlayerStatus.MERGED:
        if player.id in visited or player.merged_into_id is None:
            raise BoardConflict("player_not_confirmed")
        visited.add(player.id)
        player = db.get(PlayerProfile, player.merged_into_id)
    if player is None:
        raise BoardConflict("player_not_found")
    if player.status != PlayerStatus.ACTIVE:
        raise BoardConflict("player_not_confirmed")
    return player


def _validate_item(db: Session, item: BoardDraftItem) -> None:
    if item.change_type == BoardChangeType.REMOVED:
        if not item.removal_lifecycle_confirmed:
            raise BoardConflict("removal_lifecycle_pending")
        if item.designation_id is not None:
            designation = db.get(Designation, item.designation_id)
            released = True
            if designation is not None and designation.entitlement_item_id is not None:
                entitlement = db.get(EntitlementItem, designation.entitlement_item_id)
                released = (
                    entitlement is not None
                    and entitlement.status
                    in {
                        EntitlementItemStatus.AVAILABLE,
                        EntitlementItemStatus.EXPIRED,
                        EntitlementItemStatus.REVOKED,
                    }
                    and entitlement.current_designation_id != designation.id
                )
            if designation is None or designation.lifecycle_status != "cancelled" or not released:
                raise BoardConflict("removal_lifecycle_pending")
        return
    if item.item_kind == BoardItemKind.PLAYER:
        if (
            item.validation_status == BoardValidationStatus.AMBIGUOUS
            and item.matched_player_id is None
        ):
            raise BoardConflict("player_match_ambiguous")
        if item.matched_player_id is not None:
            canonical = _canonical_active_player(db, item.matched_player_id)
            if item.candidates:
                candidate_ids = {
                    _canonical_active_player(db, value).id
                    for value in _candidate_ids(item.candidates)
                }
                if canonical.id not in candidate_ids:
                    raise BoardConflict("player_candidate_invalid")
            item.matched_player_id = canonical.id
        item.validation_status = BoardValidationStatus.VALID
        item.failure_reason = None
        return
    if item.item_kind in {BoardItemKind.DESIGNATION, BoardItemKind.WISH}:
        if not item.player_name or not item.player_name.strip():
            item.validation_status = BoardValidationStatus.INVALID
            item.failure_reason = "player_identity_required"
            raise BoardConflict("player_identity_required")
        item.player_name = item.player_name.strip()
        claim_matches = _exact_match_players(db, normalize_player_name(item.player_name))
        claim_ids = {player.id for player in claim_matches}
        item.candidates = _candidate_descriptors(claim_matches) if len(claim_ids) > 1 else None
        if not claim_ids:
            if item.item_kind == BoardItemKind.DESIGNATION:
                item.matched_player_id = None
                item.candidates = None
            else:
                local_matches = [
                    row
                    for row in item.revision.draft_items
                    if row.item_kind == BoardItemKind.PLAYER
                    and row.change_type != BoardChangeType.REMOVED
                    and row.confirmed_at is not None
                    and normalize_player_name(row.player_name or "")
                    == normalize_player_name(item.player_name)
                ]
                if not local_matches:
                    raise BoardConflict("player_claim_not_found")
                if len(local_matches) > 1:
                    raise BoardConflict("player_match_ambiguous")
                item.matched_player_id = None
                item.candidates = None
        else:
            if item.matched_player_id is None:
                if len(claim_ids) > 1:
                    raise BoardConflict("player_match_ambiguous")
                item.matched_player_id = next(iter(claim_ids))
            canonical = _canonical_active_player(db, item.matched_player_id)
            if canonical.id not in claim_ids:
                raise BoardConflict("player_candidate_invalid")
            item.matched_player_id = canonical.id
        actor = db.get(Actor, item.actor_id) if item.actor_id else None
        role = db.get(Role, item.role_id) if item.role_id else None
        performance = item.revision.board.performance
        capable = (
            actor is not None
            and role is not None
            and db.scalar(
                select(ActorRoleCapability.id).where(
                    ActorRoleCapability.actor_id == actor.id, ActorRoleCapability.role_id == role.id
                )
            )
            is not None
        )
        if actor is None:
            raise BoardConflict("actor_not_found")
        if role is None:
            raise BoardConflict("role_not_found")
        if role.theater_id != performance.theater_id:
            raise BoardConflict("role_out_of_performance_scope")
        if not capable:
            raise BoardConflict("actor_role_capability_missing")
        item.validation_status = BoardValidationStatus.VALID
        item.failure_reason = None
        return
    if item.validation_status != BoardValidationStatus.VALID:
        raise BoardConflict("board_item_invalid")


def confirm_board_item(
    db: Session, item_id: int, corrections: BoardItemPatch, operator_user_id: int
) -> BoardDraftItem:
    item = db.get(BoardDraftItem, item_id)
    if item is None:
        raise LookupError("board_item_not_found")
    if item.confirmed_at is not None:
        return item
    for key, value in corrections.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    _validate_item(db, item)
    item.confirmed_at = utc_now()
    item.confirmed_by = operator_user_id
    db.flush()
    if item.item_kind == BoardItemKind.DESIGNATION:
        _apply_designation_projection(db, item.revision)
        db.flush()
    return item


def reopen_board_item(db: Session, item_id: int) -> BoardDraftItem:
    item = db.get(BoardDraftItem, item_id)
    if item is None:
        raise LookupError("board_item_not_found")
    if item.revision.status != BoardRevisionStatus.REVIEW_REQUIRED:
        raise BoardConflict("only_review_revision_can_reopen")
    item.confirmed_at = None
    item.confirmed_by = None
    db.flush()
    return item


def _apply_player_projection(db: Session, revision: PerformanceBoardRevision) -> None:
    existing = {
        player.player_character_name: player
        for player in db.scalars(
            select(PerformancePlayer)
            .where(PerformancePlayer.performance_id == revision.board.performance_id)
            .with_for_update()
        ).all()
    }
    selected = {
        item.player_character_name: item
        for item in revision.draft_items
        if item.item_kind == BoardItemKind.PLAYER and item.change_type != BoardChangeType.REMOVED
    }
    for player in existing.values():
        player.is_active = False
    for key, item in selected.items():
        player = existing.get(key)
        if player is None:
            player = PerformancePlayer(
                performance_id=revision.board.performance_id, player_character_name=key
            )
            db.add(player)
        player.player_profile_id = item.matched_player_id
        player.player_name_snapshot = item.player_name
        player.paired_role_name = item.paired_role_name
        player.relation_label = item.relation_label
        player.theater_visit_ordinal = item.theater_visit_ordinal
        player.character_visit_ordinal = item.character_visit_ordinal
        player.source_revision_id = revision.id
        player.is_active = True
        player.source_board_id = revision.board_id
        db.flush()
        item.performance_player_id = player.id


def _apply_wish_projection(
    db: Session, revision: PerformanceBoardRevision, operator_user_id: int
) -> None:
    player_rows = db.scalars(
        select(PerformancePlayer).where(
            PerformancePlayer.performance_id == revision.board.performance_id,
            PerformancePlayer.is_active.is_(True),
        )
    ).all()
    players = {
        row.player_profile_id: row for row in player_rows if row.player_profile_id is not None
    }
    players_by_name: dict[str, list[PerformancePlayer]] = {}
    for row in player_rows:
        players_by_name.setdefault(normalize_player_name(row.player_name_snapshot), []).append(row)

    def resolve_player(item: BoardDraftItem) -> PerformancePlayer | None:
        if item.matched_player_id is not None:
            matched = players.get(item.matched_player_id)
            if matched is not None:
                return matched
        matches = players_by_name.get(normalize_player_name(item.player_name or ""), [])
        if len(matches) > 1:
            raise BoardConflict("player_match_ambiguous")
        return matches[0] if matches else None

    for item in revision.draft_items:
        if item.item_kind != BoardItemKind.WISH:
            continue
        if item.change_type == BoardChangeType.REMOVED:
            wish = db.get(Wish, item.wish_id) if item.wish_id else None
            if wish is None:
                player = resolve_player(item)
                if player:
                    wish = db.scalar(
                        select(Wish)
                        .where(
                            Wish.performance_id == revision.board.performance_id,
                            Wish.performance_player_id == player.id,
                            Wish.actor_id == item.actor_id,
                            Wish.role_id == item.role_id,
                            Wish.status.in_(["active", "accepted"]),
                        )
                        .order_by(Wish.id)
                    )
                    if wish:
                        item.wish_id = wish.id
            if wish and wish.status in {"active", "accepted"}:
                set_wish_status(
                    db,
                    wish.id,
                    "cancelled",
                    "removed_from_active_board_revision",
                    operator_user_id,
                    expected_version=wish.version,
                    idempotency_key=f"board:{revision.id}:remove:{item.stable_key}",
                    action="board_remove",
                )
            continue
        player = resolve_player(item)
        if player is None:
            raise BoardConflict("wish_performance_player_not_found")
        wish = db.get(Wish, item.wish_id) if item.wish_id else None
        if wish is None:
            wish = create_wish(
                db,
                revision.board.performance_id,
                player.id,
                item.actor_id,
                item.role_id,
                item.note,
                0,
                f"board:{revision.id}:create:{item.stable_key}",
                operator_user_id,
            )
            item.wish_id = wish.id
        else:
            wish.player_name = player.player_name_snapshot
            wish.performance_id = revision.board.performance_id
            wish.performance_player_id = player.id
            wish.actor_id = item.actor_id
            wish.role_id = item.role_id
            wish.note = item.note
            if wish.status != "active":
                wish = set_wish_status(
                    db,
                    wish.id,
                    "active",
                    None,
                    operator_user_id,
                    expected_version=wish.version,
                    idempotency_key=f"board:{revision.id}:restore:{item.stable_key}",
                    action="board_restore",
                )


def _designation_type(item: BoardDraftItem) -> DesignationType:
    evidence = f"{item.raw_line or ''} {item.note or ''}"
    if "对位" in evidence:
        return DesignationType.PAIRED
    if "热力" in evidence or "榜三" in evidence or "榜单前三" in evidence:
        return DesignationType.TOP_THREE
    return DesignationType.UNIVERSAL


def _apply_designation_projection(db: Session, revision: PerformanceBoardRevision) -> None:
    performance_id = revision.board.performance_id
    players_by_name: dict[str, list[PerformancePlayer]] = {}
    for player in db.scalars(
        select(PerformancePlayer).where(
            PerformancePlayer.performance_id == performance_id,
            PerformancePlayer.is_active.is_(True),
        )
    ):
        players_by_name.setdefault(normalize_player_name(player.player_name_snapshot), []).append(
            player
        )

    for item in revision.draft_items:
        if (
            item.item_kind != BoardItemKind.DESIGNATION
            or item.change_type == BoardChangeType.REMOVED
            or item.confirmed_at is None
        ):
            continue
        local_matches = players_by_name.get(normalize_player_name(item.player_name or ""), [])
        beneficiary = local_matches[0] if len(local_matches) == 1 else None
        designation = db.get(Designation, item.designation_id) if item.designation_id else None
        if designation is None:
            designation = Designation(
                designation_type=_designation_type(item),
                player_name=item.player_name or "",
                actor_id=item.actor_id,
                role_id=item.role_id,
                target_performance_id=performance_id,
                performance_id=performance_id,
                beneficiary_performance_player_id=beneficiary.id if beneficiary else None,
                owner_player_id=item.matched_player_id,
                submitted_at=utc_now(),
                included_in_batch=False,
                status="pending",
                usage_type="self",
                verification_status="pending",
                lifecycle_status="draft",
            )
            db.add(designation)
            db.flush()
            item.designation_id = designation.id
        else:
            designation.designation_type = _designation_type(item)
            designation.player_name = item.player_name or ""
            designation.actor_id = item.actor_id
            designation.role_id = item.role_id
            designation.target_performance_id = performance_id
            designation.performance_id = performance_id
            designation.beneficiary_performance_player_id = beneficiary.id if beneficiary else None
            designation.owner_player_id = item.matched_player_id


def ensure_active_board_designations(db: Session, performance_id: int) -> None:
    board = db.scalar(
        select(PerformanceBoard).where(PerformanceBoard.performance_id == performance_id)
    )
    if board is None:
        return
    revision = db.scalar(
        select(PerformanceBoardRevision)
        .where(PerformanceBoardRevision.board_id == board.id)
        .order_by(PerformanceBoardRevision.revision_number.desc())
        .limit(1)
    )
    if revision is None:
        return
    _apply_designation_projection(db, revision)
    db.flush()


def activate_revision(
    db: Session, revision_id: int, operator_user_id: int
) -> PerformanceBoardRevision:
    try:
        revision = db.scalar(
            select(PerformanceBoardRevision)
            .where(PerformanceBoardRevision.id == revision_id)
            .with_for_update()
        )
        if revision is None:
            raise LookupError("board_revision_not_found")
        board = db.scalar(
            select(PerformanceBoard)
            .where(PerformanceBoard.id == revision.board_id)
            .with_for_update()
        )
        newest = db.scalar(
            select(PerformanceBoardRevision.id)
            .where(PerformanceBoardRevision.board_id == board.id)
            .order_by(PerformanceBoardRevision.revision_number.desc())
            .limit(1)
        )
        if (
            revision.status == BoardRevisionStatus.CONFIRMED
            and board.current_revision_id == revision.id
        ):
            return revision
        if revision.status == BoardRevisionStatus.CONFIRMED or newest != revision.id:
            raise BoardConflict("board_revision_superseded")
        if any(item.confirmed_at is None for item in revision.draft_items):
            code = (
                "removed_item_confirmation_required"
                if any(
                    item.change_type == BoardChangeType.REMOVED and item.confirmed_at is None
                    for item in revision.draft_items
                )
                else "board_items_confirmation_required"
            )
            raise BoardConflict(code)
        for item in revision.draft_items:
            _validate_item(db, item)
        _apply_player_projection(db, revision)
        _apply_designation_projection(db, revision)
        _apply_wish_projection(db, revision, operator_user_id)
        from app.services.actor_notifications import backfill_revealed_notification_players

        backfill_revealed_notification_players(db, board.performance_id)
        revision.status = BoardRevisionStatus.CONFIRMED
        revision.confirmed_at = utc_now()
        board.current_revision_id = revision.id
        db.commit()
        db.refresh(revision)
        return revision
    except Exception:
        db.rollback()
        raise


def clone_revision_for_rollback(
    db: Session, source_revision_id: int, operator_user_id: int
) -> PerformanceBoardRevision:
    fields = (
        "item_kind",
        "stable_key",
        "raw_line",
        "player_name",
        "player_character_name",
        "paired_role_name",
        "relation_label",
        "theater_visit_ordinal",
        "character_visit_ordinal",
        "actor_name_raw",
        "role_name_raw",
        "note",
        "matched_player_id",
        "actor_id",
        "role_id",
        "candidates",
        "confidence",
        "validation_status",
        "failure_reason",
        "designation_id",
        "wish_id",
    )

    def operation():
        current_source = db.scalar(
            select(PerformanceBoardRevision)
            .where(PerformanceBoardRevision.id == source_revision_id)
            .with_for_update()
        )
        if current_source is None:
            raise LookupError("board_revision_not_found")
        board, number = _allocate_revision(db, current_source.board.performance_id)
        clone = PerformanceBoardRevision(
            board=board,
            revision_number=number,
            raw_text=current_source.raw_text,
            parser_type=current_source.parser_type,
            provider_name=current_source.provider_name,
            model_name=current_source.model_name,
            prompt_version=current_source.prompt_version,
            raw_ai_response=current_source.raw_ai_response,
            parsed_payload=current_source.parsed_payload,
            created_by=operator_user_id,
            status=BoardRevisionStatus.REVIEW_REQUIRED,
            rollback_source_revision_id=current_source.id,
        )
        clone.draft_items = [
            BoardDraftItem(
                **{field: getattr(item, field) for field in fields},
                change_type=BoardChangeType.ADDED,
            )
            for item in current_source.draft_items
            if item.change_type != BoardChangeType.REMOVED
        ]
        return clone

    return _retry_revision_creation(db, operation)
