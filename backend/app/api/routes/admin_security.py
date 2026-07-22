from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, require_super_admin
from app.models.entities import AuditLog, Theater, User, UserTheaterScope
from app.models.enums import AuditEventCategory, AuditResult, AuditRiskLevel, UserRole
from app.schemas.admin_security import (
    AdminAccountCreate,
    AdminAccountRead,
    AdminAccountUpdate,
    AdminPasswordReset,
    AuditLogRead,
)
from app.services.actor_accounts import password_context
from app.services.admin_scope import AdminScope
from app.services.audit_logs import append_audit_log

router = APIRouter(prefix="/admin", tags=["admin-security"])


def _account_read(row: User) -> AdminAccountRead:
    return AdminAccountRead(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        role=row.role,
        is_active=row.is_active,
        theater_ids=sorted(scope.theater_id for scope in row.theater_scopes),
        last_login_at=row.last_login_at,
    )


def _validate_theaters(db: Session, theater_ids: list[int]) -> None:
    unique_ids = set(theater_ids)
    if not unique_ids:
        return
    existing = set(db.scalars(select(Theater.id).where(Theater.id.in_(unique_ids))).all())
    if existing != unique_ids:
        raise HTTPException(status_code=422, detail="invalid_theater_scope")


def _replace_scopes(db: Session, account: User, theater_ids: list[int], grantor_id: int) -> None:
    _validate_theaters(db, theater_ids)
    account.theater_scopes.clear()
    db.flush()
    account.theater_scopes.extend(
        UserTheaterScope(
            theater_id=theater_id,
            granted_by_user_id=grantor_id,
        )
        for theater_id in sorted(set(theater_ids))
    )


@router.get("/administrator-accounts", response_model=list[AdminAccountRead])
def list_administrator_accounts(
    _: AdminScope = Depends(require_super_admin), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(User)
        .where(User.role.in_([UserRole.SUPER_ADMIN, UserRole.THEATER_ADMIN]))
        .order_by(User.id)
    ).all()
    return [_account_read(row) for row in rows]


@router.post("/administrator-accounts", response_model=AdminAccountRead)
def create_administrator_account(
    payload: AdminAccountCreate,
    scope: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if payload.role == UserRole.ACTOR:
        raise HTTPException(status_code=422, detail="invalid_administrator_role")
    if payload.role == UserRole.THEATER_ADMIN and not payload.theater_ids:
        raise HTTPException(status_code=422, detail="theater_scope_required")
    if payload.role == UserRole.SUPER_ADMIN and payload.theater_ids:
        raise HTTPException(status_code=422, detail="super_admin_scope_must_be_empty")
    _validate_theaters(db, payload.theater_ids)
    account = User(
        email=payload.email.strip(),
        display_name=payload.display_name.strip(),
        password_hash=password_context.hash(payload.password),
        role=payload.role,
        is_active=True,
        must_change_password=False,
    )
    db.add(account)
    try:
        db.flush()
        _replace_scopes(db, account, payload.theater_ids, scope.user_id)
        append_audit_log(
            db,
            scope=scope,
            category=AuditEventCategory.SECURITY,
            module="administrator_accounts",
            action="create",
            risk_level=AuditRiskLevel.WARNING,
            summary=f"创建管理员 {account.display_name}",
            target_type="user",
            target_id=account.id,
            after_data={
                "email": account.email,
                "role": account.role.value,
                "theater_ids": payload.theater_ids,
            },
        )
        db.commit()
        db.refresh(account)
        return _account_read(account)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="administrator_email_exists") from exc


@router.patch("/administrator-accounts/{user_id}", response_model=AdminAccountRead)
def update_administrator_account(
    user_id: int,
    payload: AdminAccountUpdate,
    scope: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    account = db.get(User, user_id)
    if account is None or account.role == UserRole.ACTOR:
        raise HTTPException(status_code=404, detail="administrator_not_found")
    if account.id == scope.user_id and payload.is_active is False:
        raise HTTPException(status_code=409, detail="cannot_disable_current_account")
    before = {
        "display_name": account.display_name,
        "is_active": account.is_active,
        "theater_ids": sorted(item.theater_id for item in account.theater_scopes),
    }
    if payload.display_name is not None:
        account.display_name = payload.display_name.strip()
    if payload.is_active is not None:
        if account.is_active != payload.is_active:
            account.token_version += 1
        account.is_active = payload.is_active
    if payload.theater_ids is not None:
        if account.role == UserRole.SUPER_ADMIN and payload.theater_ids:
            raise HTTPException(status_code=422, detail="super_admin_scope_must_be_empty")
        if account.role == UserRole.THEATER_ADMIN and not payload.theater_ids:
            raise HTTPException(status_code=422, detail="theater_scope_required")
        _replace_scopes(db, account, payload.theater_ids, scope.user_id)
    after = {
        "display_name": account.display_name,
        "is_active": account.is_active,
        "theater_ids": sorted(item.theater_id for item in account.theater_scopes),
    }
    append_audit_log(
        db,
        scope=scope,
        category=AuditEventCategory.SECURITY,
        module="administrator_accounts",
        action="update",
        risk_level=AuditRiskLevel.WARNING,
        summary=f"修改管理员 {account.display_name}",
        target_type="user",
        target_id=account.id,
        before_data=before,
        after_data=after,
    )
    db.commit()
    db.refresh(account)
    return _account_read(account)


@router.post("/administrator-accounts/{user_id}/reset-password")
def reset_administrator_password(
    user_id: int,
    payload: AdminPasswordReset,
    scope: AdminScope = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    account = db.get(User, user_id)
    if account is None or account.role == UserRole.ACTOR:
        raise HTTPException(status_code=404, detail="administrator_not_found")
    account.password_hash = password_context.hash(payload.password)
    account.must_change_password = True
    account.token_version += 1
    append_audit_log(
        db,
        scope=scope,
        category=AuditEventCategory.SECURITY,
        module="administrator_accounts",
        action="reset_password",
        risk_level=AuditRiskLevel.CRITICAL,
        summary=f"重置管理员 {account.display_name} 的密码",
        target_type="user",
        target_id=account.id,
    )
    db.commit()
    return {"ok": True}


def _audit_statement(
    scope: AdminScope,
    theater_id: int | None,
    operator_user_id: int | None,
    category: AuditEventCategory | None,
    result: AuditResult | None,
    risk_level: AuditRiskLevel | None,
    module: str | None,
    keyword: str | None,
    start_at: datetime | None,
    end_at: datetime | None,
):
    statement = select(AuditLog)
    if not scope.is_super_admin:
        statement = statement.where(
            or_(
                AuditLog.theater_id.in_(scope.allowed_theater_ids),
                (AuditLog.event_category == AuditEventCategory.SECURITY)
                & (AuditLog.operator_user_id == scope.user_id),
            )
        )
    if theater_id is not None:
        scope.require_theater(theater_id)
        statement = statement.where(AuditLog.theater_id == theater_id)
    if operator_user_id is not None:
        statement = statement.where(AuditLog.operator_user_id == operator_user_id)
    if category is not None:
        statement = statement.where(AuditLog.event_category == category)
    if result is not None:
        statement = statement.where(AuditLog.result == result)
    if risk_level is not None:
        statement = statement.where(AuditLog.risk_level == risk_level)
    if module:
        statement = statement.where(AuditLog.module == module)
    if keyword:
        statement = statement.where(AuditLog.summary.like(f"%{keyword}%"))
    if start_at:
        statement = statement.where(AuditLog.occurred_at >= start_at)
    if end_at:
        statement = statement.where(AuditLog.occurred_at <= end_at)
    return statement.order_by(AuditLog.id.desc())


def _audit_read(row: AuditLog) -> AuditLogRead:
    return AuditLogRead(
        id=row.id,
        occurred_at=row.occurred_at,
        operator_user_id=row.operator_user_id,
        operator_name=row.operator_name_snapshot,
        operator_role=row.operator_role_snapshot,
        theater_id=row.theater_id,
        event_category=row.event_category,
        module=row.module,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        result=row.result,
        risk_level=row.risk_level,
        summary=row.summary,
        before_data=row.before_data,
        after_data=row.after_data,
        affected_objects=row.affected_objects,
        failure_code=row.failure_code,
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    theater_id: int | None = None,
    operator_user_id: int | None = None,
    category: AuditEventCategory | None = None,
    result: AuditResult | None = None,
    risk_level: AuditRiskLevel | None = None,
    module: str | None = None,
    keyword: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        _audit_statement(
            scope,
            theater_id,
            operator_user_id,
            category,
            result,
            risk_level,
            module,
            keyword,
            start_at,
            end_at,
        ).limit(limit)
    ).all()
    return [_audit_read(row) for row in rows]


@router.get("/audit-logs/export")
def export_audit_logs(
    theater_id: int | None = None,
    operator_user_id: int | None = None,
    category: AuditEventCategory | None = None,
    result: AuditResult | None = None,
    risk_level: AuditRiskLevel | None = None,
    module: str | None = None,
    keyword: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    scope: AdminScope = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        _audit_statement(
            scope,
            theater_id,
            operator_user_id,
            category,
            result,
            risk_level,
            module,
            keyword,
            start_at,
            end_at,
        ).limit(10000)
    ).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        ["时间", "操作者", "角色", "剧场ID", "分类", "模块", "动作", "结果", "风险", "摘要"]
    )
    for row in rows:
        writer.writerow(
            [
                row.occurred_at,
                row.operator_name_snapshot,
                row.operator_role_snapshot,
                row.theater_id,
                row.event_category.value,
                row.module,
                row.action,
                row.result.value,
                row.risk_level.value,
                row.summary,
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )
