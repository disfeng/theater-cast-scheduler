from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import User
from app.services.admin_scope import AdminScope, resolve_admin_scope


bearer = HTTPBearer(auto_error=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, object]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    return {
        "sub": str(payload["sub"]),
        "role": str(payload["role"]),
        "user_id": payload.get("user_id"),
        "actor_id": payload.get("actor_id"),
        "must_change_password": payload.get("must_change_password", False),
    }


def require_admin(
    user: dict[str, object] = Depends(require_user), db: Session = Depends(get_db)
) -> AdminScope:
    return resolve_admin_scope(db, user)


def require_super_admin(scope: AdminScope = Depends(require_admin)) -> AdminScope:
    if not scope.is_super_admin:
        raise HTTPException(status_code=403, detail="super_admin_required")
    return scope


def require_actor_ready(
    user: dict[str, object] = Depends(require_user), db: Session = Depends(get_db)
) -> dict[str, object]:
    if user["role"] != "actor":
        raise HTTPException(status_code=403, detail="Actor role required")
    if user.get("must_change_password") is True:
        raise HTTPException(status_code=428, detail="password_change_required")
    if user.get("actor_id") is None:
        account = db.query(User).filter(User.email == user["sub"]).one_or_none()
        if account is None or account.actor_id is None:
            raise HTTPException(status_code=403, detail="actor_account_not_linked")
        user["actor_id"] = account.actor_id
    return user
