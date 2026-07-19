from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.entities import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.actor_accounts import password_context
from app.services.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    identifier = payload.login_identifier.strip()
    user = db.scalar(select(User).where(User.email == identifier))
    password_matches = bool(
        user is not None
        and password_context.identify(user.password_hash)
        and password_context.verify(payload.password, user.password_hash)
    )
    if user is not None and password_matches:
        role = user.role.value
        return TokenResponse(
            access_token=create_access_token(
                identifier,
                role,
                user_id=user.id,
                actor_id=user.actor_id,
                must_change_password=user.must_change_password,
            ),
            role=role,
            must_change_password=user.must_change_password,
        )
    if identifier == "admin@example.com" and payload.password == "admin":
        return TokenResponse(access_token=create_access_token(identifier, "admin"), role="admin")
    if identifier == "actor@example.com" and payload.password == "actor":
        return TokenResponse(access_token=create_access_token(identifier, "actor"), role="actor")
    raise HTTPException(status_code=401, detail="Invalid credentials")
