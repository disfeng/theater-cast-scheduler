from app.models.entities import EntitlementItem, EntitlementItemType
from app.models.enums import EntitlementGrantMode


class EntitlementBindingError(RuntimeError):
    pass


def validate_grant_mode(item_type: EntitlementItemType, grant_mode: EntitlementGrantMode) -> None:
    expected = (
        EntitlementGrantMode.BY_ACTOR if item_type.binds_actor else EntitlementGrantMode.BY_PLAYER
    )
    if grant_mode != expected:
        raise EntitlementBindingError("entitlement_grant_mode_mismatch")


def validate_designation_binding(
    item: EntitlementItem, beneficiary_player_id: int, actor_id: int
) -> None:
    if item.binds_beneficiary_snapshot and item.owner_id != beneficiary_player_id:
        raise EntitlementBindingError("entitlement_beneficiary_mismatch")
    if item.binds_actor_snapshot:
        if item.bound_actor_id is None:
            raise EntitlementBindingError("entitlement_bound_actor_required")
        if item.bound_actor_id != actor_id:
            raise EntitlementBindingError("entitlement_bound_actor_mismatch")
