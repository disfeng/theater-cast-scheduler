from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    ActorNotificationTask,
    EncryptedActorNotificationSettings,
    Performance,
    Theater,
)
from app.models.enums import ActorNotificationTaskStatus
from app.schemas.admin import ActorNotificationSettingsRead, ActorNotificationSettingsUpdate


@dataclass(frozen=True)
class ProviderReceipt:
    request_id: str
    provider_code: str = "OK"


class SmsProvider(Protocol):
    def send(self, phone: str, template_params: dict[str, str]) -> ProviderReceipt: ...


def _keyring() -> list[tuple[str, Fernet]]:
    values = [settings.settings_encryption_key] + [
        value.strip()
        for value in settings.settings_previous_encryption_keys.split(",")
        if value.strip()
    ]
    if not values[0]:
        raise ValueError("settings_encryption_key_required")
    return [
        (
            hashlib.sha256(value.encode()).hexdigest()[:12],
            Fernet(base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest())),
        )
        for value in values
        if value
    ]


def _encrypt(value: str) -> str:
    key_id, fernet = _keyring()[0]
    return f"v1:{key_id}:{fernet.encrypt(value.encode()).decode()}"


def _decrypt(value: str | None) -> str | None:
    if not value:
        return None
    token = value.rsplit(":", 1)[-1]
    for _, fernet in _keyring():
        try:
            return fernet.decrypt(token.encode()).decode()
        except InvalidToken:
            continue
    raise ValueError("stored_sms_credential_unreadable")


def get_sms_settings(db: Session) -> EncryptedActorNotificationSettings:
    row = db.get(EncryptedActorNotificationSettings, 1)
    if row is None:
        row = EncryptedActorNotificationSettings(id=1, actor_portal_url=settings.actor_portal_url)
        db.add(row)
        db.flush()
    return row


def read_sms_settings(row: EncryptedActorNotificationSettings) -> ActorNotificationSettingsRead:
    configured = bool(row.encrypted_access_key_id and row.encrypted_access_key_secret)
    return ActorNotificationSettingsRead(
        sms_enabled=row.sms_enabled,
        actor_portal_url=row.actor_portal_url,
        credentials_configured=configured,
        access_key_id_masked="••••••••" if row.encrypted_access_key_id else None,
        sign_name=row.sign_name,
        template_code=row.template_code,
        endpoint=row.endpoint,
    )


def update_sms_settings(
    db: Session, payload: ActorNotificationSettingsUpdate
) -> EncryptedActorNotificationSettings:
    row = get_sms_settings(db)
    if payload.access_key_id is not None:
        if not payload.access_key_id.strip():
            raise ValueError("access_key_id_must_not_be_blank")
        row.encrypted_access_key_id = _encrypt(payload.access_key_id.strip())
    if payload.access_key_secret is not None:
        if not payload.access_key_secret.strip():
            raise ValueError("access_key_secret_must_not_be_blank")
        row.encrypted_access_key_secret = _encrypt(payload.access_key_secret.strip())
    if payload.sms_enabled and not (
        row.encrypted_access_key_id and row.encrypted_access_key_secret
    ):
        raise ValueError("sms_credentials_required_when_enabled")
    row.sms_enabled = payload.sms_enabled
    row.actor_portal_url = payload.actor_portal_url
    row.sign_name = payload.sign_name
    row.template_code = payload.template_code
    row.endpoint = payload.endpoint
    db.flush()
    return row


class AlibabaSmsProvider:
    def __init__(self, row: EncryptedActorNotificationSettings):
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_dysmsapi20170525.client import Client

        config = open_api_models.Config(
            access_key_id=_decrypt(row.encrypted_access_key_id),
            access_key_secret=_decrypt(row.encrypted_access_key_secret),
        )
        config.endpoint = row.endpoint
        self._client = Client(config)
        self._sign_name = row.sign_name
        self._template_code = row.template_code

    def send(self, phone: str, template_params: dict[str, str]) -> ProviderReceipt:
        import json
        from alibabacloud_dysmsapi20170525 import models as sms_models

        response = self._client.send_sms(
            sms_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=self._sign_name,
                template_code=self._template_code,
                template_param=json.dumps(template_params, ensure_ascii=False),
            )
        )
        body = response.body
        if body.code != "OK":
            raise RuntimeError(body.message or body.code)
        return ProviderReceipt(request_id=body.request_id or "", provider_code=body.code)


def reschedule_pending_tasks_for_theater(db: Session, theater_id: int, now: datetime) -> int:
    """Recalculate only pending tasks; reveal processing is handled by the disclosure worker."""
    del now
    theater = db.get(Theater, theater_id)
    if theater is None:
        return 0
    rows = db.execute(
        select(ActorNotificationTask, Performance)
        .join(Performance, Performance.id == ActorNotificationTask.performance_id)
        .where(
            ActorNotificationTask.theater_id == theater_id,
            ActorNotificationTask.status == ActorNotificationTaskStatus.PENDING,
        )
    ).all()
    for task, performance in rows:
        task.reveal_at = datetime.combine(
            performance.performance_date - timedelta(days=theater.reveal_days_before),
            theater.reveal_time,
        )
    db.flush()
    return len(rows)
