from datetime import date, datetime, time

from app.models.entities import (
    Actor,
    Designation,
    DesignationVersion,
    FulfillmentFailure,
    Performance,
    Role,
    Theater,
    TheaterSlot,
    User,
    Wish,
    WishVersion,
)
from app.models.enums import DesignationType, UserRole


def _seed_scope(db_session):
    theater = Theater(name="西安幽州剧场")
    slot = TheaterSlot(theater=theater, name="晚场", start_time=time(19, 30))
    performance = Performance(
        theater=theater,
        theater_slot=slot,
        performance_date=date(2026, 7, 20),
        slot_name_snapshot="晚场",
        start_time_snapshot=time(19, 30),
    )
    actor = Actor(display_name="小A", phone_number="13800000000")
    role = Role(theater=theater, name="林月棠")
    operator = User(
        email="admin@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
    )
    db_session.add_all([performance, actor, role, operator])
    db_session.flush()
    return performance, actor, role, operator


def test_designation_and_wish_keep_explicit_immutable_content_versions(db_session):
    performance, actor, role, operator = _seed_scope(db_session)
    designation = Designation(
        designation_type=DesignationType.UNIVERSAL,
        player_name="微醺",
        role_id=role.id,
        actor_id=actor.id,
        target_performance_id=performance.id,
        performance_id=performance.id,
        submitted_at=datetime(2026, 7, 19),
        lifecycle_status="draft",
    )
    wish = Wish(
        player_name="微醺",
        role_id=role.id,
        actor_id=actor.id,
        performance_id=performance.id,
        status="active",
    )
    db_session.add_all([designation, wish])
    db_session.flush()
    designation_version = DesignationVersion(
        designation_id=designation.id,
        version_number=1,
        player_name="微醺",
        actor_id=actor.id,
        role_id=role.id,
        usage_type="self",
        raw_text="【虔诚许愿】-小A/林月棠（微醺）",
        created_by=operator.id,
    )
    wish_version = WishVersion(
        wish_id=wish.id,
        version_number=1,
        player_name="微醺",
        actor_id=actor.id,
        role_id=role.id,
        raw_text="【虔诚许愿】-小A/林月棠（微醺）",
        created_by=operator.id,
    )
    db_session.add_all([designation_version, wish_version])
    db_session.flush()
    designation.current_version_id = designation_version.id
    wish.current_version_id = wish_version.id
    db_session.commit()

    assert designation.current_version_id == designation_version.id
    assert wish.current_version_id == wish_version.id
    assert designation_version.version_number == 1
    assert wish_version.version_number == 1


def test_fulfillment_failure_records_retryable_operation(db_session):
    performance, _, _, operator = _seed_scope(db_session)
    failure = FulfillmentFailure(
        operation="reverse_consumption",
        business_kind="designation",
        business_id=9,
        performance_id=performance.id,
        idempotency_key="reverse-designation-9",
        error_code="ledger_not_found",
        status="pending",
        attempt_count=1,
        operator_user_id=operator.id,
    )
    db_session.add(failure)
    db_session.commit()

    assert failure.id > 0
    assert failure.attempt_count == 1
