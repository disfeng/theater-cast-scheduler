from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.entities import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.actor_accounts import password_context
from app.services.auth import create_access_token
from app.models.enums import AuditEventCategory, AuditResult, AuditRiskLevel
from app.services.admin_scope import AdminScope
from app.services.audit_logs import append_audit_log
from app.services.login_protection import (
    clear_login_failures,
    clear_throttle,
    is_login_locked,
    record_login_failure,
    record_throttle_failure,
    throttle_for,
)
from app.core.config import settings
from app.core.time import utc_now

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    identifier = payload.login_identifier.strip()
    ip_address = request.client.host if request.client else "unknown"
    user = db.scalar(select(User).where(User.email == identifier))
    password_matches = bool(
        user is not None
        and password_context.identify(user.password_hash)
        and password_context.verify(payload.password, user.password_hash)
    )
    throttle = throttle_for(db, identifier, ip_address)
    locked = (user is not None and is_login_locked(user)) or (
        throttle is not None
        and throttle.locked_until is not None
        and throttle.locked_until > utc_now()
    )
    if user is not None and password_matches and user.is_active and not locked:
        role = user.role.value
        user.last_login_at = utc_now()
        clear_login_failures(user)
        clear_throttle(db, identifier, ip_address)
        scope = None
        if role in {"super_admin", "theater_admin"}:
            scope = AdminScope(
                user_id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role,
                allowed_theater_ids=frozenset(),
            )
        append_audit_log(
            db,
            scope=scope,
            category=AuditEventCategory.SECURITY,
            module="authentication",
            action="login",
            summary="管理员登录成功" if scope else "演员登录成功",
            result=AuditResult.SUCCESS,
            target_type="user",
            target_id=str(user.id),
            operator_user_id=user.id,
            operator_name=user.display_name,
            operator_role=user.role.value,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        return TokenResponse(
            access_token=create_access_token(
                identifier,
                role,
                user_id=user.id,
                actor_id=user.actor_id,
                must_change_password=user.must_change_password,
                token_version=user.token_version,
            ),
            role=role,
            must_change_password=user.must_change_password,
        )
    triggered_lock = False
    bucket = record_throttle_failure(
        db,
        identifier,
        ip_address,
        max_failures=settings.login_max_failures,
        lock_minutes=settings.login_lock_minutes,
    )
    if user is not None and not locked:
        triggered_lock = record_login_failure(
            user,
            max_failures=settings.login_max_failures,
            lock_minutes=settings.login_lock_minutes,
        )
    append_audit_log(
        db,
        scope=None,
        category=AuditEventCategory.SECURITY,
        module="authentication",
        action="login",
        summary=f"登录失败：{identifier[:120]}",
        result=AuditResult.FAILURE,
        risk_level=AuditRiskLevel.WARNING,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        failure_code="login_locked"
        if locked or triggered_lock or bucket.locked_until is not None
        else "invalid_credentials",
    )
    db.commit()
    raise HTTPException(status_code=401, detail="Invalid credentials")
