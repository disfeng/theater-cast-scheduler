from datetime import date, datetime, time

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

from app.models.entities import (
    BoardDraftItem,
    Actor,
    ActorRoleCapability,
    Designation,
    Performance,
    PerformanceBoard,
    PerformancePlayer,
    PlayerAlias,
    PlayerProfile,
    Theater,
    TheaterSlot,
    Role,
    Wish,
)
from app.models.enums import BoardChangeType, BoardItemKind, BoardRevisionStatus, DesignationType
from app.schemas.performance_boards import BoardItemPatch
from app.services.performance_boards import (
    BoardConflict,
    activate_revision,
    confirm_board_item,
    create_board_revision,
    clone_revision_for_rollback,
    ensure_active_board_designations,
    reopen_board_item,
)
import app.services.performance_boards as performance_board_service
from app.services.wishes import active_scope_key


def _performance(db_session, day: int = 1) -> Performance:
    theater = Theater(name=f"剧场{day}")
    slot = TheaterSlot(theater=theater, name="19:30", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 8, day),
        slot_name_snapshot=slot.name,
        start_time_snapshot=slot.start_time,
    )
    db_session.add(performance)
    db_session.commit()
    return performance


def test_one_board_per_performance_and_revision_numbers_increase(db_session):
    performance = _performance(db_session)
    first = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离（恋）：Jennifer-14-3", 7
    )
    second = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离（恋）：Jennifer-15-4", 7
    )

    assert first.board_id == second.board_id
    assert (first.revision_number, second.revision_number) == (1, 2)
    assert db_session.scalar(
        select(PerformanceBoard).where(PerformanceBoard.performance_id == performance.id)
    )
    assert len(db_session.scalars(select(PerformanceBoard)).all()) == 1
    assert first.raw_text.endswith("Jennifer-14-3")


def test_revision_diff_has_added_modified_unchanged_and_removed_items(db_session):
    performance = _performance(db_session)
    first = create_board_revision(
        db_session,
        performance.id,
        """#玩家信息
【昭昭】长离（恋）：Jennifer-14-3
【观禾】轩辕重光：Sally
【初晴】长离：Sunny
""",
        7,
    )
    for item in first.draft_items:
        confirm_board_item(db_session, item.id, BoardItemPatch(), 7)
    activate_revision(db_session, first.id, 7)

    second = create_board_revision(
        db_session,
        performance.id,
        """#玩家信息
【昭昭】长离（恋）：Jennifer-15-4
【初晴】长离：Sunny
【新角色】长离：NewPlayer
""",
        7,
    )
    changes = {item.player_character_name: item.change_type for item in second.draft_items}
    assert changes == {
        "昭昭": BoardChangeType.MODIFIED,
        "初晴": BoardChangeType.UNCHANGED,
        "新角色": BoardChangeType.ADDED,
        "观禾": BoardChangeType.REMOVED,
    }


def test_confirming_player_item_is_idempotent_and_only_then_writes_performance_player(db_session):
    performance = _performance(db_session)
    revision = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离（恋）：Jennifer-14-3", 7
    )
    item = revision.draft_items[0]
    assert db_session.scalars(select(PerformancePlayer)).all() == []

    first = confirm_board_item(db_session, item.id, BoardItemPatch(), 7)
    second = confirm_board_item(db_session, item.id, BoardItemPatch(), 7)

    assert first.id == second.id
    assert db_session.scalars(select(PerformancePlayer)).all() == []
    activate_revision(db_session, revision.id, 7)
    players = db_session.scalars(select(PerformancePlayer)).all()
    assert len(players) == 1
    assert players[0].player_name_snapshot == "Jennifer"
    assert players[0].theater_visit_ordinal == 14


def test_confirmed_item_in_review_revision_can_be_reopened_and_confirmed_again(db_session):
    performance = _performance(db_session)
    revision = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离（恋）：Jennifer-14-3", 7
    )
    item = revision.draft_items[0]
    confirm_board_item(db_session, item.id, BoardItemPatch(), 7)

    reopened = reopen_board_item(db_session, item.id)

    assert reopened.confirmed_at is None
    assert reopened.confirmed_by is None
    confirmed = confirm_board_item(
        db_session, item.id, BoardItemPatch(player_name="Jennifer 修改"), 7
    )
    assert confirmed.player_name == "Jennifer 修改"
    assert confirmed.confirmed_at is not None


def test_activation_creates_performance_scoped_wish_for_confirmed_player_case_insensitively(
    db_session,
):
    performance = _performance(db_session)
    profile = PlayerProfile(display_name="Sunny", normalized_name="sunny")
    actor = Actor(display_name="A")
    role = Role(theater_id=performance.theater_id, name="R")
    db_session.add_all([profile, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#玩家信息\n【sunny】R：Sunny\n#指定信息\n【虔诚许愿】-A/R-sunny",
        7,
    )
    player_item = next(row for row in revision.draft_items if row.item_kind == "player")
    wish_item = next(row for row in revision.draft_items if row.item_kind == "wish")
    confirm_board_item(db_session, player_item.id, BoardItemPatch(matched_player_id=profile.id), 7)
    confirm_board_item(
        db_session,
        wish_item.id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id, matched_player_id=profile.id),
        7,
    )
    activate_revision(db_session, revision.id, 7)
    wish = db_session.scalar(select(Wish))
    assert wish.performance_id == performance.id
    assert wish.performance_player_id == db_session.scalar(select(PerformancePlayer.id))
    assert wish.status == "active"
    assert wish_item.wish_id == wish.id
    assert activate_revision(db_session, revision.id, 7).id == revision.id
    assert db_session.query(Wish).count() == 1


def test_wish_without_global_profile_links_unique_player_from_same_board_revision(db_session):
    performance = _performance(db_session)
    actor = Actor(display_name="小A")
    role = Role(theater_id=performance.theater_id, name="林月棠")
    db_session.add_all([actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#玩家信息\n【柳余潮】林月棠（恋）：微醺未醒-31-13\n#指定信息\n【虔诚许愿】-小A/林月棠-微醺未醒",
        7,
    )
    player_item = next(row for row in revision.draft_items if row.item_kind == "player")
    wish_item = next(row for row in revision.draft_items if row.item_kind == "wish")

    confirm_board_item(db_session, player_item.id, BoardItemPatch(), 7)
    confirmed_wish = confirm_board_item(
        db_session,
        wish_item.id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id),
        7,
    )
    activate_revision(db_session, revision.id, 7)

    performance_player = db_session.scalar(select(PerformancePlayer))
    wish = db_session.scalar(select(Wish))
    assert confirmed_wish.matched_player_id is None
    assert performance_player.player_profile_id is None
    assert wish.performance_player_id == performance_player.id
    assert wish.player_name == "微醺未醒"


def test_deterministic_parser_preserves_evidence_and_exactly_matches_wish_and_designation(db_session):
    performance = _performance(db_session)
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    actor = Actor(display_name="小展")
    role = Role(theater_id=performance.theater_id, name="长离")
    db_session.add_all([player, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()

    wish_line = "【虔诚许愿】-小展/长离-Jennifer（再续前缘）"
    designation_line = "热力榜三-小展/长离（四月热力榜-Jennifer）"
    revision = create_board_revision(
        db_session,
        performance.id,
        f"#指定信息\n{wish_line}\n{designation_line}",
        7,
    )

    wish = next(item for item in revision.draft_items if item.item_kind == BoardItemKind.WISH)
    designation = next(
        item for item in revision.draft_items if item.item_kind == BoardItemKind.DESIGNATION
    )
    for item, evidence in ((wish, wish_line), (designation, designation_line)):
        assert item.raw_line == evidence
        assert item.matched_player_id == player.id
        assert item.actor_id == actor.id
        assert item.role_id == role.id
        assert item.validation_status.value == "valid"
        assert item.failure_reason is None


def test_unresolved_item_can_be_manually_classified_as_wish_and_confirmed(db_session):
    performance = _performance(db_session)
    player = PlayerProfile(display_name="微醺未醒", normalized_name="微醺未醒")
    actor = Actor(display_name="小A")
    role = Role(theater_id=performance.theater_id, name="林月棠")
    db_session.add_all([player, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session, performance.id, "#指定信息\n无法自动识别的登记", 7
    )
    item = revision.draft_items[0]

    confirmed = confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(
            item_kind="wish",
            player_name="微醺未醒",
            matched_player_id=player.id,
            actor_id=actor.id,
            role_id=role.id,
        ),
        7,
    )

    assert confirmed.item_kind == BoardItemKind.WISH
    assert confirmed.validation_status.value == "valid"
    assert confirmed.failure_reason is None
    assert confirmed.confirmed_at is not None


def test_removed_wish_is_cancelled_and_rollback_reactivates_same_formal_wish(db_session):
    performance = _performance(db_session)
    profile = PlayerProfile(display_name="Sunny", normalized_name="sunny")
    actor = Actor(display_name="A")
    role = Role(theater_id=performance.theater_id, name="R")
    db_session.add_all([profile, actor, role])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    first = create_board_revision(
        db_session,
        performance.id,
        "#玩家信息\n【sunny】R：Sunny\n#指定信息\n【虔诚许愿】-A/R-sunny",
        7,
    )
    for item in first.draft_items:
        patch = (
            BoardItemPatch(matched_player_id=profile.id, actor_id=actor.id, role_id=role.id)
            if item.item_kind == "wish"
            else BoardItemPatch(matched_player_id=profile.id)
        )
        confirm_board_item(db_session, item.id, patch, 7)
    activate_revision(db_session, first.id, 7)
    original = db_session.scalar(select(Wish))
    original_id = original.id
    second = create_board_revision(db_session, performance.id, "#玩家信息\n【sunny】R：Sunny", 7)
    next(
        item for item in second.draft_items if item.item_kind == "wish"
    ).wish_id = None  # legacy projection: resolve by stable identity
    for item in second.draft_items:
        confirm_board_item(
            db_session,
            item.id,
            BoardItemPatch(
                matched_player_id=profile.id,
                removal_lifecycle_confirmed=item.change_type == BoardChangeType.REMOVED,
            ),
            7,
        )
    activate_revision(db_session, second.id, 7)
    db_session.refresh(original)
    assert original.status == "cancelled"
    assert original.failure_reason == "removed_from_active_board_revision"
    rolled = clone_revision_for_rollback(db_session, first.id, 7)
    competing = Wish(
        player_name="Sunny",
        role_id=role.id,
        actor_id=actor.id,
        performance_id=performance.id,
        performance_player_id=original.performance_player_id,
        status="active",
        active_scope_key=active_scope_key(
            performance.id, original.performance_player_id, actor.id, role.id
        ),
    )
    db_session.add(competing)
    db_session.commit()
    for item in rolled.draft_items:
        confirm_board_item(db_session, item.id, BoardItemPatch(), 7)
    db_session.commit()
    with pytest.raises(Exception, match="wish_active_duplicate"):
        activate_revision(db_session, rolled.id, 7)
    db_session.delete(competing)
    db_session.commit()
    activate_revision(db_session, rolled.id, 7)
    db_session.refresh(original)
    assert original.id == original_id
    assert original.status == "active"
    assert original.failure_reason is None


def test_activation_is_non_destructive_and_requires_removed_item_confirmation(db_session):
    performance = _performance(db_session)
    first = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离：Jennifer", 7
    )
    confirm_board_item(db_session, first.draft_items[0].id, BoardItemPatch(), 7)
    activate_revision(db_session, first.id, 7)
    second = create_board_revision(db_session, performance.id, "#玩家信息\n【观禾】长离：Sally", 7)
    for item in second.draft_items:
        if item.change_type != BoardChangeType.REMOVED:
            confirm_board_item(db_session, item.id, BoardItemPatch(), 7)
    db_session.commit()
    with pytest.raises(BoardConflict, match="removed_item_confirmation_required"):
        activate_revision(db_session, second.id, 7)
    removed = next(
        item for item in second.draft_items if item.change_type == BoardChangeType.REMOVED
    )
    confirm_board_item(db_session, removed.id, BoardItemPatch(removal_lifecycle_confirmed=True), 7)
    activate_revision(db_session, second.id, 7)

    db_session.refresh(first)
    assert first.status == BoardRevisionStatus.CONFIRMED
    assert second.board.current_revision_id == second.id
    assert db_session.get(BoardDraftItem, first.draft_items[0].id) is not None


def test_reviewing_losing_revision_never_changes_active_projection(db_session):
    performance = _performance(db_session)
    first = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离：Jennifer-1-1", 7
    )
    confirm_board_item(db_session, first.draft_items[0].id, BoardItemPatch(), 7)
    activate_revision(db_session, first.id, 7)
    second = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离：Sally-9-9", 7
    )
    confirm_board_item(db_session, second.draft_items[0].id, BoardItemPatch(), 7)

    projected = db_session.scalar(select(PerformancePlayer))
    assert projected.player_name_snapshot == "Jennifer"
    assert projected.theater_visit_ordinal == 1


def test_superseded_revision_cannot_activate_and_rollback_clones_reviewed_snapshot(db_session):
    performance = _performance(db_session)
    first = create_board_revision(db_session, performance.id, "#玩家信息\n【昭昭】长离：RawName", 7)
    confirm_board_item(
        db_session, first.draft_items[0].id, BoardItemPatch(player_name="Corrected"), 7
    )
    activate_revision(db_session, first.id, 7)
    second = create_board_revision(db_session, performance.id, "#玩家信息\n【昭昭】长离：Second", 7)
    confirm_board_item(db_session, second.draft_items[0].id, BoardItemPatch(), 7)
    activate_revision(db_session, second.id, 7)

    with pytest.raises(BoardConflict, match="board_revision_superseded"):
        activate_revision(db_session, first.id, 7)
    rolled = clone_revision_for_rollback(db_session, first.id, 7)
    assert rolled.revision_number == 3
    assert rolled.rollback_source_revision_id == first.id
    assert rolled.draft_items[0].player_name == "Corrected"
    assert rolled.draft_items[0].stable_key == first.draft_items[0].stable_key


def test_snacks_and_notes_are_retained_in_raw_text_but_not_draft_items(db_session):
    performance = _performance(db_session)
    raw = """#玩家信息
【昭昭】长离：Jennifer
#场内点心
昭昭：两瓶水
#其他备注
观禾：开观禾2.0
"""
    revision = create_board_revision(db_session, performance.id, raw, 7)
    assert revision.raw_text == raw
    assert [item.item_kind for item in revision.draft_items] == [BoardItemKind.PLAYER]


def test_removed_confirmed_designation_requires_lifecycle_cancellation(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    db_session.add_all([role, actor, player])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    first = create_board_revision(
        db_session, performance.id, "#指定信息\n热力榜三-文轩/轩辕重光", 7
    )
    item = first.draft_items[0]
    confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(
            actor_id=actor.id,
            role_id=role.id,
            player_name="Jennifer",
            matched_player_id=player.id,
        ),
        7,
    )
    designation = Designation(
        designation_type=DesignationType.TOP_THREE,
        player_name="p",
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=performance.id,
        submitted_at=datetime(2026, 8, 1),
        lifecycle_status="predesignated",
    )
    db_session.add(designation)
    db_session.flush()
    item.designation_id = designation.id
    db_session.commit()
    activate_revision(db_session, first.id, 7)
    second = create_board_revision(db_session, performance.id, "#玩家信息", 7)
    removed = second.draft_items[0]

    with pytest.raises(BoardConflict, match="removal_lifecycle_pending"):
        confirm_board_item(db_session, removed.id, BoardItemPatch(), 7)
    db_session.rollback()
    designation.lifecycle_status = "cancelled"
    db_session.commit()
    confirmed = confirm_board_item(
        db_session, removed.id, BoardItemPatch(removal_lifecycle_confirmed=True), 7
    )
    assert confirmed.confirmed_at is not None


def test_designation_corrections_recompute_validation_from_scoped_entities(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    db_session.add_all([role, actor, player])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session, performance.id, "#指定信息\n热力榜三-文轩/轩辕重光", 7
    )
    item = revision.draft_items[0]

    with pytest.raises(BoardConflict, match="player_identity_required"):
        confirm_board_item(
            db_session, item.id, BoardItemPatch(actor_id=actor.id, role_id=role.id), 7
        )
    db_session.rollback()
    confirmed = confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(
            actor_id=actor.id,
            role_id=role.id,
            player_name=" Jennifer ",
            matched_player_id=player.id,
        ),
        7,
    )
    assert confirmed.validation_status.value == "valid"
    assert confirmed.player_name == "Jennifer"
    assert confirmed.matched_player_id == player.id


def test_player_name_correction_rejects_blank_and_overlong_values():
    with pytest.raises(ValidationError):
        BoardItemPatch(player_name="   ")
    with pytest.raises(ValidationError):
        BoardItemPatch(player_name="x" * 121)


@pytest.mark.parametrize(
    "line",
    [
        "#指定信息\n热力榜三-文轩/轩辕重光（四月热力榜-Jennifer）",
        "#指定信息\n【虔诚许愿】-文轩/轩辕重光-Jennifer note",
    ],
)
def test_designation_and_wish_require_player_name_claim(db_session, line):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    player = PlayerProfile(display_name="Jennifer", normalized_name="jennifer")
    db_session.add_all([role, actor, player])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(db_session, performance.id, line, 7)
    item = revision.draft_items[0]

    confirmed = confirm_board_item(
        db_session, item.id, BoardItemPatch(actor_id=actor.id, role_id=role.id), 7
    )
    assert confirmed.matched_player_id == player.id
    assert confirmed.validation_status.value == "valid"


@pytest.mark.parametrize(
    "line",
    [
        "#指定信息\n热力榜三-文轩/轩辕重光（四月热力榜-shared）",
        "#指定信息\n【虔诚许愿】-文轩/轩辕重光-shared note",
    ],
)
def test_designation_and_wish_ambiguous_claim_requires_explicit_canonical_candidate(
    db_session, line
):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    one = PlayerProfile(display_name="shared", normalized_name="shared")
    two = PlayerProfile(display_name="Two", normalized_name="two")
    two.aliases.append(PlayerAlias(alias="shared", normalized_alias="shared"))
    db_session.add_all([role, actor, one, two])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(db_session, performance.id, line, 7)
    item = revision.draft_items[0]

    with pytest.raises(BoardConflict, match="player_match_ambiguous"):
        confirm_board_item(
            db_session, item.id, BoardItemPatch(actor_id=actor.id, role_id=role.id), 7
        )
    db_session.rollback()
    confirmed = confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id, matched_player_id=two.id),
        7,
    )
    assert confirmed.matched_player_id == two.id


def test_business_item_rejects_arbitrary_player_id_without_matching_claim(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    unrelated = PlayerProfile(display_name="Unrelated", normalized_name="unrelated")
    db_session.add_all([role, actor, unrelated])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#指定信息\n【虔诚许愿】-文轩/轩辕重光-Unknown note",
        7,
    )
    with pytest.raises(BoardConflict, match="player_claim_not_found"):
        confirm_board_item(
            db_session,
            revision.draft_items[0].id,
            BoardItemPatch(actor_id=actor.id, role_id=role.id, matched_player_id=unrelated.id),
            7,
        )


def test_designation_allows_player_name_without_player_or_same_board_claim(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    db_session.add_all([role, actor])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#指定信息\n热力榜三-文轩/轩辕重光（四月热力榜-兹）",
        7,
    )

    confirmed = confirm_board_item(
        db_session,
        revision.draft_items[0].id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id, player_name="兹"),
        7,
    )

    assert confirmed.item_kind == BoardItemKind.DESIGNATION
    assert confirmed.player_name == "兹"
    assert confirmed.matched_player_id is None
    assert confirmed.confirmed_at is not None
    designation = db_session.scalar(select(Designation))
    assert designation is not None
    assert designation.player_name == "兹"
    assert designation.lifecycle_status == "draft"
    assert confirmed.designation_id == designation.id


def test_activation_projects_confirmed_designation_into_performance_workspace(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    db_session.add_all([role, actor])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#指定信息\n热力榜三-文轩/轩辕重光（四月热力榜-兹）",
        7,
    )
    item = revision.draft_items[0]
    confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id, player_name="兹"),
        7,
    )

    activate_revision(db_session, revision.id, 7)

    designation = db_session.scalar(select(Designation))
    assert designation is not None
    assert designation.performance_id == performance.id
    assert designation.target_performance_id == performance.id
    assert designation.player_name == "兹"
    assert designation.designation_type.value == "top_three"
    assert designation.lifecycle_status == "draft"
    assert item.designation_id == designation.id


def test_active_board_designation_projection_repairs_legacy_missing_row(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    db_session.add_all([role, actor])
    db_session.flush()
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#指定信息\n热力榜三-文轩/轩辕重光（四月热力榜-兹）",
        7,
    )
    item = revision.draft_items[0]
    confirm_board_item(
        db_session,
        item.id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id, player_name="兹"),
        7,
    )
    activate_revision(db_session, revision.id, 7)
    db_session.delete(db_session.get(Designation, item.designation_id))
    item.designation_id = None
    db_session.commit()

    ensure_active_board_designations(db_session, performance.id)
    db_session.commit()

    repaired = db_session.scalar(select(Designation))
    assert repaired is not None
    assert repaired.player_name == "兹"
    assert item.designation_id == repaired.id


def test_wish_player_claim_canonicalizes_merged_owner_to_active_target(db_session):
    performance = _performance(db_session)
    role = Role(theater_id=performance.theater_id, name="轩辕重光")
    actor = Actor(display_name="文轩")
    target = PlayerProfile(display_name="Target", normalized_name="target", status="ACTIVE")
    source = PlayerProfile(display_name="Old", normalized_name="old", status="MERGED")
    db_session.add_all([role, actor, target, source])
    db_session.flush()
    source.merged_into_id = target.id
    source.aliases.append(PlayerAlias(alias="legacy", normalized_alias="legacy"))
    db_session.add(ActorRoleCapability(actor_id=actor.id, role_id=role.id))
    db_session.commit()
    revision = create_board_revision(
        db_session,
        performance.id,
        "#指定信息\n【虔诚许愿】-文轩/轩辕重光-legacy note",
        7,
    )
    confirmed = confirm_board_item(
        db_session,
        revision.draft_items[0].id,
        BoardItemPatch(actor_id=actor.id, role_id=role.id),
        7,
    )
    assert confirmed.matched_player_id == target.id


def test_ambiguous_player_requires_explicit_active_candidate_selection(db_session):
    performance = _performance(db_session)
    one = PlayerProfile(display_name="One", normalized_name="one")
    two = PlayerProfile(display_name="Two", normalized_name="two")
    one.aliases.append(PlayerAlias(alias="shared", normalized_alias="shared-one"))
    two.aliases.append(PlayerAlias(alias="shared", normalized_alias="shared-two"))
    db_session.add_all([one, two])
    db_session.commit()
    revision = create_board_revision(
        db_session, performance.id, "#玩家信息\n【昭昭】长离：shared", 7
    )
    item = revision.draft_items[0]
    item.validation_status = "AMBIGUOUS"
    item.candidates = [one.id, two.id]
    db_session.commit()

    with pytest.raises(BoardConflict, match="player_match_ambiguous"):
        confirm_board_item(db_session, item.id, BoardItemPatch(), 7)
    confirmed = confirm_board_item(db_session, item.id, BoardItemPatch(matched_player_id=one.id), 7)
    assert confirmed.matched_player_id == one.id


def test_duplicate_stable_keys_are_review_errors(db_session):
    performance = _performance(db_session)
    revision = create_board_revision(
        db_session,
        performance.id,
        """#玩家信息
【昭昭】长离：Jennifer
【昭昭】长离：Sally
""",
        7,
    )
    assert {item.failure_reason for item in revision.draft_items} == {"duplicate_stable_key"}
    assert all(item.validation_status.value == "invalid" for item in revision.draft_items)


def test_revision_counter_allocates_monotonically_across_sessions(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'board-counter.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)
    with SessionLocal() as seed:
        performance = _performance(seed)
        performance_id = performance.id
    with SessionLocal() as first, SessionLocal() as second:
        one = create_board_revision(first, performance_id, "#玩家信息\n【A】长离：One", 7)
        two = create_board_revision(second, performance_id, "#玩家信息\n【B】长离：Two", 7)
        three = create_board_revision(first, performance_id, "#玩家信息\n【C】长离：Three", 7)
    assert [one.revision_number, two.revision_number, three.revision_number] == [1, 2, 3]


def test_injected_allocation_collisions_retry_paste_and_rollback(db_session, monkeypatch):
    performance = _performance(db_session)
    real_allocate = performance_board_service._allocate_revision
    attempts = 0

    def collide_twice(db, performance_id):
        nonlocal attempts
        attempts += 1
        if attempts % 3 != 0:
            raise IntegrityError("allocate", {}, Exception("collision"))
        return real_allocate(db, performance_id)

    monkeypatch.setattr(performance_board_service, "_allocate_revision", collide_twice)
    source = create_board_revision(db_session, performance.id, "#玩家信息\n【A】长离：One", 7)
    assert source.revision_number == 1
    clone = clone_revision_for_rollback(db_session, source.id, 7)
    assert clone.revision_number == 2
    assert attempts == 6


def test_revision_uses_unified_case_insensitive_player_claim_without_creating_profile(db_session):
    performance = _performance(db_session)
    player = PlayerProfile(display_name="Sunny", normalized_name="sunny")
    player.aliases.append(PlayerAlias(alias="SUN NY", normalized_alias="sun ny", is_primary=False))
    db_session.add(player)
    db_session.commit()

    revision = create_board_revision(
        db_session, performance.id, "#玩家信息\n【初晴】长离：sunny-2-3", 7
    )

    assert revision.draft_items[0].matched_player_id == player.id
    assert len(db_session.scalars(select(PlayerProfile)).all()) == 1
