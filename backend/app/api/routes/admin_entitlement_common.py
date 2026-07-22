from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.services.entitlements import EntitlementConflict, EntitlementNotFound


def _operator(user: dict[str, str], db: Session) -> int:
    operator = db.scalar(select(User).where(User.email == user["sub"]))
    if operator is None:
        raise HTTPException(401, detail="operator_user_not_found")
    return operator.id


def _raise(exc: Exception):
    if isinstance(exc, EntitlementNotFound):
        raise HTTPException(404, detail=str(exc)) from exc
    if isinstance(exc, EntitlementConflict):
        raise HTTPException(409, detail=str(exc)) from exc
    raise exc
