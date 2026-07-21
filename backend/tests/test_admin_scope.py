import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.entities import Theater, User, UserTheaterScope
from app.models.enums import UserRole
from app.services.admin_scope import AdminScope, resolve_admin_scope


def _admin(db_session, role, email):
    user = User(email=email, password_hash="x", role=role, display_name=email)
    db_session.add(user)
    db_session.flush()
    return user


def test_theater_admin_scope_is_loaded_from_database(db_session):
    grantor = _admin(db_session, UserRole.SUPER_ADMIN, "root@example.com")
    manager = _admin(db_session, UserRole.THEATER_ADMIN, "manager@example.com")
    theaters = [Theater(name="一号剧场"), Theater(name="二号剧场")]
    db_session.add_all(theaters)
    db_session.flush()
    db_session.add_all(
        [
            UserTheaterScope(
                user_id=manager.id,
                theater_id=theater.id,
                granted_by_user_id=grantor.id,
            )
            for theater in theaters
        ]
    )
    db_session.commit()

    scope = resolve_admin_scope(
        db_session,
        {"user_id": manager.id, "sub": manager.email, "role": "theater_admin"},
    )

    assert scope.allowed_theater_ids == frozenset({row.id for row in theaters})
    scope.require_theater(theaters[0].id)
    with pytest.raises(HTTPException) as exc:
        scope.require_theater(999)
    assert exc.value.status_code == 403
    assert exc.value.detail == "theater_scope_forbidden"


def test_super_admin_scope_does_not_require_explicit_theater_rows(db_session):
    root = _admin(db_session, UserRole.SUPER_ADMIN, "root@example.com")
    db_session.commit()
    scope = resolve_admin_scope(
        db_session, {"user_id": root.id, "sub": root.email, "role": "super_admin"}
    )
    assert scope.is_super_admin is True
    scope.require_theater(999)


def test_disabled_admin_token_stops_working_immediately(db_session):
    manager = _admin(db_session, UserRole.THEATER_ADMIN, "disabled@example.com")
    db_session.commit()
    manager.is_active = False
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        resolve_admin_scope(
            db_session,
            {"user_id": manager.id, "sub": manager.email, "role": "theater_admin"},
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "admin_account_disabled"


def test_scope_filters_statement_in_sql(db_session):
    scope = AdminScope(
        user_id=4,
        email="manager@example.com",
        display_name="管理员",
        role=UserRole.THEATER_ADMIN,
        allowed_theater_ids=frozenset({2, 3}),
    )
    statement = scope.filter_statement(select(Theater), Theater.id)
    assert "theaters.id IN" in str(statement)
