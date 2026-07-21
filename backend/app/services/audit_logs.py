from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import AuditLog
from app.models.enums import AuditEventCategory, AuditResult, AuditRiskLevel
from app.services.admin_scope import AdminScope


SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "api_key",
    "access_key_id",
    "access_key_secret",
    "authorization",
    "token",
}


def redact_audit_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in SENSITIVE_KEYS else redact_audit_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_audit_data(item) for item in value]
    return value


def append_audit_log(
    db: Session,
    *,
    scope: AdminScope | None,
    category: AuditEventCategory,
    module: str,
    action: str,
    result: AuditResult = AuditResult.SUCCESS,
    risk_level: AuditRiskLevel = AuditRiskLevel.NORMAL,
    summary: str,
    theater_id: int | None = None,
    target_type: str | None = None,
    target_id: str | int | None = None,
    before_data: Any = None,
    after_data: Any = None,
    affected_objects: Any = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    failure_code: str | None = None,
) -> AuditLog:
    row = AuditLog(
        occurred_at=datetime.utcnow(),
        request_id=request_id,
        operator_user_id=scope.user_id if scope else None,
        operator_name_snapshot=scope.display_name if scope else None,
        operator_role_snapshot=scope.role.value if scope else None,
        theater_id=theater_id,
        event_category=category,
        module=module,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        result=result,
        risk_level=risk_level,
        summary=summary,
        before_data=redact_audit_data(before_data),
        after_data=redact_audit_data(after_data),
        affected_objects=redact_audit_data(affected_objects),
        ip_address=ip_address,
        user_agent=user_agent,
        failure_code=failure_code,
    )
    db.add(row)
    return row
