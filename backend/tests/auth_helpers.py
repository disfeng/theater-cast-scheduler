from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.models.enums import UserRole
from app.services.auth import create_access_token


def persisted_admin_headers(db: Session, *, email: str = "admin@example.com") -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash="test-only",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
    token = create_access_token(
        user.email,
        user.role.value,
        user_id=user.id,
        actor_id=user.actor_id,
        must_change_password=user.must_change_password,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


def persisted_admin_headers_from_override() -> dict[str, str]:
    from app.api.deps import get_db
    from app.main import app

    override = app.dependency_overrides[get_db]
    db = next(override())
    return persisted_admin_headers(db)
