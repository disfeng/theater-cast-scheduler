from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AuditEventCategory, AuditResult, AuditRiskLevel, UserRole


class AdminAccountCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.THEATER_ADMIN
    theater_ids: list[int] = Field(default_factory=list)


class AdminAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    theater_ids: list[int] | None = None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class AdminAccountRead(BaseModel):
    id: int
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    theater_ids: list[int]
    last_login_at: datetime | None


class AuditLogRead(BaseModel):
    id: int
    occurred_at: datetime
    operator_user_id: int | None
    operator_name: str | None
    operator_role: str | None
    theater_id: int | None
    event_category: AuditEventCategory
    module: str
    action: str
    target_type: str | None
    target_id: str | None
    result: AuditResult
    risk_level: AuditRiskLevel
    summary: str
    before_data: dict | list | None
    after_data: dict | list | None
    affected_objects: dict | list | None
    failure_code: str | None
