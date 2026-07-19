import base64
import re
import secrets
import string

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import Actor, ActorTheaterMembership, Theater, User
from app.models.enums import UserRole
from app.schemas.admin import ActorCreate, ActorCredentialDelivery
from app.services.credential_pdf import build_actor_credential_pdf

password_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s-]+", "", value)
    if not re.fullmatch(r"1\d{10}", phone):
        raise ValueError("invalid_phone_number")
    return phone


def create_actor_account(
    db: Session, payload: ActorCreate
) -> tuple[Actor, ActorCredentialDelivery]:
    if payload.phone_number is None or payload.entry_theater_id is None:
        raise ValueError("phone_and_entry_theater_required")
    phone = normalize_phone(payload.phone_number)
    theater_ids = set(payload.theater_ids)
    theater_ids.add(payload.entry_theater_id)
    theaters = list(db.scalars(select(Theater).where(Theater.id.in_(theater_ids))))
    if len(theaters) != len(theater_ids):
        raise LookupError("theater_not_found")
    entry_theater = next(item for item in theaters if item.id == payload.entry_theater_id)
    password = generate_initial_password()
    actor = Actor(
        display_name=payload.display_name,
        phone_number=phone,
        max_consecutive_performances=payload.max_consecutive_performances,
        rating_level=payload.rating_level,
        low_rating_monthly_cap=payload.low_rating_monthly_cap,
        notes=payload.notes,
    )
    db.add(actor)
    db.flush()
    db.add(
        User(
            email=phone,
            password_hash=password_context.hash(password),
            role=UserRole.ACTOR,
            actor_id=actor.id,
            must_change_password=True,
        )
    )
    for theater_id in sorted(theater_ids):
        db.add(
            ActorTheaterMembership(
                actor_id=actor.id,
                theater_id=theater_id,
                is_entry_theater=theater_id == payload.entry_theater_id,
            )
        )
    db.commit()
    db.refresh(actor)
    pdf = build_actor_credential_pdf(
        theater_name=entry_theater.name,
        actor_name=actor.display_name,
        portal_url=settings.actor_portal_url,
        username=phone,
        password=password,
    )
    return actor, ActorCredentialDelivery(
        username=phone,
        initial_password=password,
        filename=f"{entry_theater.name}-{actor.display_name}.pdf",
        pdf_base64=base64.b64encode(pdf).decode("ascii"),
    )


def reset_actor_password(
    db: Session, actor_id: int, entry_theater_id: int
) -> ActorCredentialDelivery:
    actor = db.get(Actor, actor_id)
    if actor is None or actor.user is None or actor.phone_number is None:
        raise LookupError("actor_account_not_found")
    membership = db.scalar(
        select(ActorTheaterMembership).where(
            ActorTheaterMembership.actor_id == actor_id,
            ActorTheaterMembership.theater_id == entry_theater_id,
        )
    )
    theater = db.get(Theater, entry_theater_id)
    if membership is None or theater is None:
        raise ValueError("entry_theater_not_assigned")
    password = generate_initial_password()
    actor.user.password_hash = password_context.hash(password)
    actor.user.must_change_password = True
    actor.user.password_changed_at = None
    db.commit()
    pdf = build_actor_credential_pdf(
        theater_name=theater.name,
        actor_name=actor.display_name,
        portal_url=settings.actor_portal_url,
        username=actor.phone_number,
        password=password,
    )
    return ActorCredentialDelivery(
        username=actor.phone_number,
        initial_password=password,
        filename=f"{theater.name}-{actor.display_name}.pdf",
        pdf_base64=base64.b64encode(pdf).decode("ascii"),
    )


def change_actor_password(
    db: Session, user_id: int, current_password: str, new_password: str
) -> None:
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.ACTOR:
        raise LookupError("actor_account_not_found")
    if not password_context.verify(current_password, user.password_hash):
        raise ValueError("current_password_invalid")
    if password_context.verify(new_password, user.password_hash):
        raise ValueError("new_password_must_differ")
    user.password_hash = password_context.hash(new_password)
    user.must_change_password = False
    from datetime import datetime

    user.password_changed_at = datetime.utcnow()
    db.commit()


def generate_initial_password() -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(char.isalpha() for char in password) and any(char.isdigit() for char in password):
            return password
