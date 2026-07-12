from datetime import date

from app.models.entities import LeaveRequest
from app.models.enums import LeaveStatus, RatingLevel
from app.schemas.admin import ActorCreate, ActorUpdate, RoleCreate, TheaterCreate
from app.services.admin_data import (
    create_actor,
    create_role,
    create_theater,
    list_roles,
    list_theaters,
    replace_actor_capabilities,
    review_leave_request,
    update_actor,
)


def test_admin_data_services_create_theaters_roles_and_actor_capabilities(db_session):
    create_theater(
        db_session,
        TheaterCreate(
            name="西幽剧场",
            default_weekly_template={"monday": ["early", "late"], "tuesday": ["late"]},
        ),
    )
    role = create_role(db_session, RoleCreate(name="长离", group_name="女位"))
    actor = create_actor(
        db_session,
        ActorCreate(
            display_name="小展",
            max_consecutive_performances=2,
            rating_level=RatingLevel.NORMAL,
            low_rating_monthly_cap=None,
            notes="可跨卡",
        ),
    )
    replace_actor_capabilities(db_session, actor.id, [role.id])

    assert [item.name for item in list_theaters(db_session)] == ["西幽剧场"]
    assert [item.name for item in list_roles(db_session)] == ["长离"]
    assert actor.role_capabilities[0].role.name == "长离"


def test_update_actor_rating_and_leave_review(db_session):
    actor = create_actor(
        db_session,
        ActorCreate(
            display_name="浩泽",
            max_consecutive_performances=3,
            rating_level=RatingLevel.NORMAL,
            low_rating_monthly_cap=None,
            notes=None,
        ),
    )
    updated = update_actor(
        db_session,
        actor.id,
        ActorUpdate(
            max_consecutive_performances=1,
            rating_level=RatingLevel.LOW,
            low_rating_monthly_cap=4,
            notes="观察期",
        ),
    )
    leave = LeaveRequest(actor_id=actor.id, leave_date=date(2026, 6, 5), note="提前请假")
    db_session.add(leave)
    db_session.commit()

    reviewed = review_leave_request(db_session, leave.id, LeaveStatus.APPROVED)

    assert updated.max_consecutive_performances == 1
    assert updated.rating_level == RatingLevel.LOW
    assert updated.low_rating_monthly_cap == 4
    assert reviewed.status == LeaveStatus.APPROVED
