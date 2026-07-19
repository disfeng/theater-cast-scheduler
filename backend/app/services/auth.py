from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings


def create_access_token(
    subject: str,
    role: str,
    *,
    user_id: int | None = None,
    actor_id: int | None = None,
    must_change_password: bool | None = None,
) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    claims = {"sub": subject, "role": role, "exp": expires_at}
    if user_id is not None:
        claims["user_id"] = user_id
    if actor_id is not None:
        claims["actor_id"] = actor_id
    if must_change_password is not None:
        claims["must_change_password"] = must_change_password
    return jwt.encode(
        claims,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
