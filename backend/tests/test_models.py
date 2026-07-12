from app.models.entities import Actor, ActorRoleCapability, Role, Theater


def test_actor_can_have_multiple_role_capabilities(db_session):
    actor = Actor(display_name="小展", max_consecutive_performances=3)
    role_a = Role(name="长离", group_name="女位")
    role_b = Role(name="北恒", group_name="女位")
    db_session.add_all([actor, role_a, role_b])
    db_session.flush()

    db_session.add_all([
        ActorRoleCapability(actor_id=actor.id, role_id=role_a.id),
        ActorRoleCapability(actor_id=actor.id, role_id=role_b.id),
    ])
    db_session.commit()

    refreshed = db_session.get(Actor, actor.id)
    assert {cap.role.name for cap in refreshed.role_capabilities} == {"长离", "北恒"}


def test_theater_template_fields_are_persisted(db_session):
    theater = Theater(
        name="西幽剧场",
        default_weekly_template={
            "monday": ["early", "late"],
            "tuesday": ["late"],
        },
    )
    db_session.add(theater)
    db_session.commit()

    refreshed = db_session.get(Theater, theater.id)
    assert refreshed.name == "西幽剧场"
    assert refreshed.default_weekly_template["monday"] == ["early", "late"]
