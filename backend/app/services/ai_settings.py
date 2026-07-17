import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import EncryptedAiParserSettings
from app.schemas.performance_boards import AiParserSettingsRead, AiParserSettingsUpdate
from app.services.ai_parser import validate_provider_endpoint


def _keyring() -> list[tuple[str, Fernet]]:
    values = [settings.settings_encryption_key] + [
        v.strip() for v in settings.settings_previous_encryption_keys.split(",") if v.strip()
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


def get_ai_settings(db: Session) -> EncryptedAiParserSettings:
    row = db.get(EncryptedAiParserSettings, 1)
    if row is None:
        row = EncryptedAiParserSettings(id=1)
        db.add(row)
        db.flush()
    return row


def decrypt_api_key(row: EncryptedAiParserSettings) -> str | None:
    if not row.encrypted_api_key:
        return None
    token = row.encrypted_api_key.rsplit(":", 1)[-1]
    ring = _keyring()
    for index, (_, fernet) in enumerate(ring):
        try:
            plaintext = fernet.decrypt(token.encode()).decode()
            if index:
                key_id, current = ring[0]
                row.encrypted_api_key = (
                    f"v1:{key_id}:{current.encrypt(plaintext.encode()).decode()}"
                )
            return plaintext
        except InvalidToken:
            continue
    raise ValueError("stored_api_key_unreadable")


def read_ai_settings(row: EncryptedAiParserSettings) -> AiParserSettingsRead:
    return AiParserSettingsRead(
        enabled=row.enabled,
        endpoint=row.endpoint,
        api_key_masked="••••••••" if row.encrypted_api_key else None,
        model_name=row.model_name,
        timeout_seconds=row.timeout_seconds,
        prompt_version=row.prompt_version,
        last_test_ok=row.last_test_ok,
        last_test_message=row.last_test_message,
        last_tested_at=row.last_tested_at,
    )


def update_ai_settings(
    db: Session, payload: AiParserSettingsUpdate, resolver=None
) -> EncryptedAiParserSettings:
    row = get_ai_settings(db)
    endpoint = (
        validate_provider_endpoint(payload.endpoint, resolver)
        if resolver
        else validate_provider_endpoint(payload.endpoint)
    )
    if payload.api_key is not None:
        if not payload.api_key.strip():
            raise ValueError("api_key_must_not_be_blank")
        key_id, fernet = _keyring()[0]
        row.encrypted_api_key = f"v1:{key_id}:{fernet.encrypt(payload.api_key.encode()).decode()}"
    if payload.enabled and not row.encrypted_api_key:
        raise ValueError("api_key_required_when_enabled")
    row.enabled = payload.enabled
    row.endpoint = endpoint
    row.model_name = payload.model_name
    row.timeout_seconds = payload.timeout_seconds
    db.flush()
    return row
