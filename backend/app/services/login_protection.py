from datetime import datetime, timedelta
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import LoginThrottle, User
from app.core.time import utc_now


def is_login_locked(user: User, *, now: datetime | None = None) -> bool:
    current = now or utc_now()
    return user.locked_until is not None and user.locked_until > current


def record_login_failure(user: User, *, max_failures: int, lock_minutes: int) -> bool:
    user.failed_login_count += 1
    user.last_failed_login_at = utc_now()
    if user.failed_login_count >= max_failures:
        user.locked_until = utc_now() + timedelta(minutes=lock_minutes)
        return True
    return False


def clear_login_failures(user: User) -> None:
    user.failed_login_count = 0
    user.last_failed_login_at = None
    user.locked_until = None


def throttle_for(db: Session, identifier: str, ip_address: str) -> LoginThrottle | None:
    digest = hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest()
    pending = next(
        (
            row
            for row in db.new
            if isinstance(row, LoginThrottle)
            and row.identifier_hash == digest
            and row.ip_address == ip_address
        ),
        None,
    )
    if pending is not None:
        return pending
    return db.scalar(
        select(LoginThrottle).where(
            LoginThrottle.identifier_hash == digest, LoginThrottle.ip_address == ip_address
        )
    )


def record_throttle_failure(
    db: Session, identifier: str, ip_address: str, *, max_failures: int, lock_minutes: int
) -> LoginThrottle:
    row = throttle_for(db, identifier, ip_address)
    now = utc_now()
    if row is not None and row.locked_until is not None and row.locked_until > now:
        return row
    if row is None:
        row = LoginThrottle(
            identifier_hash=hashlib.sha256(identifier.strip().lower().encode("utf-8")).hexdigest(),
            ip_address=ip_address,
            failed_count=0,
        )
        db.add(row)
    row.failed_count += 1
    row.last_failed_at = now
    if row.failed_count >= max_failures:
        row.locked_until = now + timedelta(minutes=lock_minutes)
    return row


def clear_throttle(db: Session, identifier: str, ip_address: str) -> None:
    row = throttle_for(db, identifier, ip_address)
    if row is not None:
        db.delete(row)
