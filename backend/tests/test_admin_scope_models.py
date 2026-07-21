from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.entities import (
    AuditLog,
    AuditLogImmutableError,
    Theater,
    User,
    UserTheaterScope,
)
from app.models.enums import (
    AuditEventCategory,
    AuditResult,
    AuditRiskLevel,
    UserRole,
)


def _users_and_theater(db_session):
    grantor = User(
        email="root@example.com",
        display_name="超级管理员",
        password_hash="x",
        role=UserRole.SUPER_ADMIN,
    )
    manager = User(
        email="manager@example.com",
        display_name="剧场管理员",
        password_hash="x",
        role=UserRole.THEATER_ADMIN,
    )
    theater = Theater(name="测试剧场")
    db_session.add_all([grantor, manager, theater])
    db_session.flush()
    return grantor, manager, theater


def test_admin_roles_and_unique_theater_scope(db_session):
    assert UserRole.SUPER_ADMIN.value == "super_admin"
    assert UserRole.THEATER_ADMIN.value == "theater_admin"
    grantor, manager, theater = _users_and_theater(db_session)
    db_session.add(
        UserTheaterScope(
            user_id=manager.id,
            theater_id=theater.id,
            granted_by_user_id=grantor.id,
        )
    )
    db_session.flush()
    db_session.add(
        UserTheaterScope(
            user_id=manager.id,
            theater_id=theater.id,
            granted_by_user_id=grantor.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_audit_log_is_append_only(db_session):
    row = AuditLog(
        occurred_at=datetime.utcnow(),
        event_category=AuditEventCategory.BUSINESS,
        module="theater",
        action="update",
        result=AuditResult.SUCCESS,
        risk_level=AuditRiskLevel.NORMAL,
        summary="修改剧场",
    )
    db_session.add(row)
    db_session.commit()
    row.summary = "覆盖"
    with pytest.raises(AuditLogImmutableError):
        db_session.flush()
