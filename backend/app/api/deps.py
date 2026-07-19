from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal


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


def require_admin(user: dict[str, object] = Depends(require_user)) -> dict[str, object]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def require_actor_ready(user: dict[str, object] = Depends(require_user)) -> dict[str, object]:
    if user["role"] != "actor":
        raise HTTPException(status_code=403, detail="Actor role required")
    if user.get("must_change_password") is True:
        raise HTTPException(status_code=428, detail="password_change_required")
    return user
