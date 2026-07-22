import pytest

from app.models.entities import Wish, WishVersion
from app.schemas.performance_boards import DesignationCorrectionPatch, WishCorrectionPatch
from app.services.business_corrections import (
    CorrectionConflict,
    correct_designation,
    correct_wish,
    preview_designation_correction,
)
from app.services.designations import verify_self_designation
from app.models.enums import EntitlementItemStatus
from test_designation_lifecycle import _designation, _item, _world


def _reserved_world(db_session):
    perf, player, _, beneficiary, actor, role, operator, types = _world(db_session)
    old_item = _item(db_session, beneficiary, types[0], "OLD")
    new_item = _item(db_session, beneficiary, types[0], "NEW")
    designation = _designation(db_session, perf, player, beneficiary, actor, role, types[0])
    verify_self_designation(db_session, designation.id, old_item.id, operator.id)
    db_session.commit()
    return designation, old_item, new_item, operator


def test_predesignated_correction_previews_release_and_new_reservation(db_session):
    designation, old_item, new_item, _ = _reserved_world(db_session)
    preview = preview_designation_correction(
        db_session,
        designation.id,
        DesignationCorrectionPatch(
            entitlement_item_id=new_item.id,
            reason="微信登记权益有误",
            confirmed=False,
            expected_version=designation.version,
            idempotency_key="preview-1",
        ),
    )
    assert preview.release_item_id == old_item.id
    assert preview.reserve_item_id == new_item.id
    assert preview.requires_reversal is False


def test_confirmed_predesignated_correction_atomically_switches_reserved_item(db_session):
    designation, old_item, new_item, operator = _reserved_world(db_session)
    result = correct_designation(
        db_session,
        designation.id,
        DesignationCorrectionPatch(
            entitlement_item_id=new_item.id,
            reason="微信登记权益有误",
            confirmed=True,
            expected_version=designation.version,
            idempotency_key="correct-1",
        ),
        operator.id,
    )
    db_session.commit()
    assert result.entitlement_item_id == new_item.id
    assert old_item.status == EntitlementItemStatus.AVAILABLE
    assert new_item.status == EntitlementItemStatus.RESERVED
    assert result.current_version_id is not None


def test_effective_player_name_correction_does_not_rebind_consumed_item(db_session):
    designation, item, _, operator = _reserved_world(db_session)
    designation.lifecycle_status = "effective"
    item.status = EntitlementItemStatus.CONSUMED
    item.current_designation_id = designation.id
    db_session.commit()

    preview = preview_designation_correction(
        db_session,
        designation.id,
        DesignationCorrectionPatch(
            player_name="修正后的玩家",
            reason="微信群登记昵称有误",
            confirmed=False,
            expected_version=designation.version,
            idempotency_key="effective-preview",
        ),
    )
    assert preview.requires_reversal is False

    result = correct_designation(
        db_session,
        designation.id,
        DesignationCorrectionPatch(
            player_name="修正后的玩家",
            reason="微信群登记昵称有误",
            confirmed=True,
            expected_version=designation.version,
            idempotency_key="effective-correction",
        ),
        operator.id,
    )
    db_session.commit()

    assert result.player_name == "修正后的玩家"
    assert result.lifecycle_status == "effective"
    assert item.status == EntitlementItemStatus.CONSUMED
    assert item.current_designation_id == designation.id


def test_correction_requires_reason_confirmation_and_current_version(db_session):
    designation, _, new_item, operator = _reserved_world(db_session)
    for patch, code in (
        (
            DesignationCorrectionPatch(
                entitlement_item_id=new_item.id,
                reason=" ",
                confirmed=True,
                expected_version=designation.version,
                idempotency_key="blank",
            ),
            "correction_reason_required",
        ),
        (
            DesignationCorrectionPatch(
                entitlement_item_id=new_item.id,
                reason="修正",
                confirmed=False,
                expected_version=designation.version,
                idempotency_key="unconfirmed",
            ),
            "correction_confirmation_required",
        ),
        (
            DesignationCorrectionPatch(
                entitlement_item_id=new_item.id,
                reason="修正",
                confirmed=True,
                expected_version=designation.version - 1,
                idempotency_key="stale",
            ),
            "correction_version_conflict",
        ),
    ):
        with pytest.raises(CorrectionConflict, match=code):
            correct_designation(db_session, designation.id, patch, operator.id)


def test_effective_wish_correction_keeps_history_and_returns_to_review(db_session):
    perf, player, _, _, actor, role, operator, _ = _world(db_session)
    wish = Wish(
        player_name="错误昵称",
        performance_id=perf.id,
        performance_player_id=player.id,
        actor_id=actor.id,
        role_id=role.id,
        status="effective",
        version=2,
        active_scope_key="wish-correction",
    )
    db_session.add(wish)
    db_session.commit()

    result = correct_wish(
        db_session,
        wish.id,
        WishCorrectionPatch(
            player_name="正确昵称",
            reason="微信群登记昵称有误",
            confirmed=True,
            expected_version=2,
            idempotency_key="wish-correct-1",
        ),
        operator.id,
    )
    db_session.commit()

    assert result.player_name == "正确昵称"
    assert result.status == "effective"
    assert result.current_version_id is not None
    assert db_session.query(WishVersion).filter_by(wish_id=wish.id).count() == 2
