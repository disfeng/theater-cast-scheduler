"""Focused entitlement service extracted from the legacy facade."""

from sqlalchemy import select
from sqlalchemy.orm import Session


from app.models.entities import (
    ActorRoleCapability,
    EntitlementItemType,
    Role,
)
from app.models.enums import (
    EntitlementGrantMode,
)
from app.services.entitlement_binding import EntitlementBindingError, validate_grant_mode


from app.services import entitlements as _legacy

EntitlementError = _legacy.EntitlementError
EntitlementNotFound = _legacy.EntitlementNotFound
EntitlementConflict = _legacy.EntitlementConflict


def validate_grant_binding(
    db: Session,
    theater_id: int | None,
    item_type: EntitlementItemType,
    bound_actor_id: int | None,
    grant_mode: EntitlementGrantMode | None = None,
) -> None:
    if grant_mode is not None:
        try:
            validate_grant_mode(item_type, grant_mode)
        except EntitlementBindingError as exc:
            raise EntitlementConflict(str(exc)) from exc
    requires_actor = item_type.binds_actor
    if requires_actor != (bound_actor_id is not None):
        code = (
            "entitlement_bound_actor_required"
            if requires_actor
            else "entitlement_actor_binding_invalid"
        )
        raise EntitlementConflict(code)
    if bound_actor_id is None:
        return
    capability = db.scalar(
        select(ActorRoleCapability.id)
        .join(Role, Role.id == ActorRoleCapability.role_id)
        .where(
            ActorRoleCapability.actor_id == bound_actor_id,
            Role.theater_id == theater_id,
        )
        .limit(1)
    )
    if capability is None:
        raise EntitlementConflict("entitlement_bound_actor_invalid")


__all__ = ["validate_grant_binding"]
