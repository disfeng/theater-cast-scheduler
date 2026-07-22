from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.entities import User, UserTheaterScope
from app.models.enums import UserRole


@dataclass(frozen=True)
class AdminScope:
    user_id: int
    email: str
    display_name: str
    role: UserRole
    allowed_theater_ids: frozenset[int]

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    def require_theater(self, theater_id: int) -> None:
        if not self.is_super_admin and theater_id not in self.allowed_theater_ids:
            raise HTTPException(status_code=403, detail="theater_scope_forbidden")

    def filter_statement(self, statement: Select, theater_column: Any) -> Select:
        if self.is_super_admin:
            return statement
        return statement.where(theater_column.in_(self.allowed_theater_ids))

    def __getitem__(self, key: str) -> object:
        """Keep older route code working while dependencies migrate to attributes."""
        values: dict[str, object] = {
            "sub": self.email,
            "user_id": self.user_id,
            "role": self.role.value,
            "actor_id": None,
            "must_change_password": False,
        }
        if key not in values:
            raise KeyError(key)
        return values[key]

    def get(self, key: str, default: object = None) -> object:
        try:
            return self[key]
        except KeyError:
            return default


def resolve_admin_scope(db: Session, token_user: dict[str, object]) -> AdminScope:
    user_id = token_user.get("user_id")
    statement = select(User)
    if user_id is not None:
        statement = statement.where(User.id == int(user_id))
    else:
        statement = statement.where(User.email == str(token_user.get("sub", "")))
    account = db.scalar(statement)
    if account is None:
        raise HTTPException(status_code=401, detail="admin_account_not_found")
    if account.role not in {UserRole.SUPER_ADMIN, UserRole.THEATER_ADMIN}:
        raise HTTPException(status_code=403, detail="Admin role required")
    if not account.is_active:
        raise HTTPException(status_code=403, detail="admin_account_disabled")

    allowed: frozenset[int]
    if account.role == UserRole.SUPER_ADMIN:
        allowed = frozenset()
    else:
        allowed = frozenset(
            db.scalars(
                select(UserTheaterScope.theater_id).where(UserTheaterScope.user_id == account.id)
            ).all()
        )
    return AdminScope(
        user_id=account.id,
        email=account.email,
        display_name=account.display_name,
        role=account.role,
        allowed_theater_ids=allowed,
    )
